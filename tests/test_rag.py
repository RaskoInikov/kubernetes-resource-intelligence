"""Offline tests for M8 analysis-grounded retrieval and quality evaluation."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from kri.contracts import (
    AnalysisEvidence,
    AnalysisProvenance,
    AnalysisReport,
    AnalysisSufficiency,
    CalculatedStatistic,
    ConditionSeverity,
    DetectedCondition,
    KnowledgeDocumentType,
    KnowledgeRetrievalHit,
    KnowledgeRetrievalResult,
    OperationalEvidenceBundle,
    OperationalEvidencePackage,
    ResourceRecommendation,
    RetrievalEvaluationCaseResult,
    RetrievalEvaluationDataset,
    RetrievalEvaluationHit,
    RetrievalEvaluationReport,
    RetrievalMetricThresholds,
    WorkloadIdentity,
)
from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import (
    DeterministicKnowledgeChunker,
    KnowledgeIndexError,
    KnowledgeInspectionAPI,
)
from kri.rag import (
    AnalysisEvidenceRetriever,
    RAGError,
    RetrievalEvaluator,
    evaluation_dataset_digest,
    load_evaluation_dataset,
)

ROOT = Path(__file__).parents[1]
DATASET_PATH = ROOT / "evaluation" / "m8-retrieval-v1.json"
NOW = datetime(2026, 11, 1, 13, 0, tzinfo=UTC)


def canonical_chunks() -> tuple[Any, ...]:
    repository = KnowledgeRepository(ROOT / "knowledge")
    manifest = repository.load_manifest()
    return DeterministicKnowledgeChunker().chunk(
        repository.load_all(), manifest.repository_version
    )


class FakeKnowledge(KnowledgeInspectionAPI):
    def __init__(
        self,
        results: dict[str, tuple[str, ...]] | None = None,
        *,
        fail: bool = False,
        chunks: tuple[Any, ...] | None = None,
    ) -> None:
        self.results = results or {}
        self.fail = fail
        self.stored_chunks = canonical_chunks() if chunks is None else chunks
        self.calls: list[tuple[str, int]] = []

    def chunks(
        self, document_id: str | None = None, limit: int = 100
    ) -> tuple[Any, ...]:
        if self.fail:
            raise KnowledgeIndexError("offline")
        values = self.stored_chunks
        if document_id is not None:
            values = tuple(item for item in values if item.document_id == document_id)
        return values[:limit]

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        document_types: tuple[KnowledgeDocumentType, ...] = (),
    ) -> KnowledgeRetrievalResult:
        if self.fail:
            raise KnowledgeIndexError("offline")
        self.calls.append((query, limit))
        by_id = {chunk.chunk_id: chunk for chunk in self.stored_chunks}
        selected_ids = self.results.get(query, tuple(by_id)[:limit])[:limit]
        hits = tuple(
            KnowledgeRetrievalHit(score=max(-1, 1 - rank * 0.4), chunk=by_id[chunk_id])
            for rank, chunk_id in enumerate(selected_ids, start=1)
        )
        return KnowledgeRetrievalResult(
            query=query,
            limit=limit,
            collection_name="test",
            repository_version="1.0.0",
            hits=hits,
        )


def analysis() -> AnalysisReport:
    evidence = (
        AnalysisEvidence(
            evidence_id="e-cpu",
            source="workload_configuration",
            resource_field="cpu_limit",
            sample_count=1,
            description="CPU limit",
        ),
        AnalysisEvidence(
            evidence_id="e-memory",
            source="workload_configuration",
            resource_field="memory_request",
            sample_count=1,
            description="Memory request",
        ),
    )
    statistics = (
        CalculatedStatistic(
            statistic_id="s-cpu",
            name="CPU throttle ratio",
            value=0.8,
            unit="ratio",
            aggregation_scope="pod/container",
            labels={"pod": "a"},
            evidence_ids=("e-cpu",),
        ),
        CalculatedStatistic(
            statistic_id="s-memory",
            name="Memory request utilization",
            value=1.5,
            unit="ratio",
            aggregation_scope="pod/container",
            labels={"pod": "a"},
            evidence_ids=("e-memory",),
        ),
    )
    conditions = (
        DetectedCondition(
            condition_id="cpu-throttle-a",
            condition_type="cpu_throttling_high",
            severity=ConditionSeverity.CRITICAL,
            message="CPU CFS throttling is high",
            observed_value=0.8,
            threshold=0.2,
            statistic_ids=("s-cpu",),
            evidence_ids=("e-cpu",),
        ),
        DetectedCondition(
            condition_id="memory-request-a",
            condition_type="memory_request_low",
            severity=ConditionSeverity.WARNING,
            message="Memory p95 materially exceeds the request",
            observed_value=1.5,
            threshold=1.2,
            statistic_ids=("s-memory",),
            evidence_ids=("e-memory",),
        ),
    )
    recommendations = (
        ResourceRecommendation(
            recommendation_id="increase-cpu-limit",
            resource="cpu_limit",
            current_value="100m",
            recommended_value="160m",
            lower_bound="100m",
            upper_bound="200m",
            rationale="Increase after CPU throttling with bounded headroom.",
            condition_ids=("cpu-throttle-a",),
            statistic_ids=("s-cpu",),
            evidence_ids=("e-cpu",),
        ),
    )
    return AnalysisReport(
        analysis_id="analysis-test",
        observation_id="observation-test",
        created_at=NOW,
        identity=WorkloadIdentity(
            cluster="kind-test",
            namespace="payments",
            deployment_name="kri-workload",
            deployment_uid="uid",
        ),
        sufficiency=AnalysisSufficiency.SUFFICIENT,
        provenance=AnalysisProvenance(observation_source_digest_sha256="a" * 64),
        statistics=statistics,
        conditions=conditions,
        recommendations=recommendations,
        evidence=evidence,
        risks_and_uncertainties=(),
    )


def dataset() -> RetrievalEvaluationDataset:
    return load_evaluation_dataset(DATASET_PATH)


def ideal_results(value: RetrievalEvaluationDataset) -> dict[str, tuple[str, ...]]:
    return {
        case.query: tuple(
            item.chunk_id
            for item in sorted(
                case.judgments, key=lambda item: item.relevance, reverse=True
            )
        )
        for case in value.cases
    }


def test_analysis_retrieval_is_grouped_and_traceable() -> None:
    knowledge = FakeKnowledge()
    package = AnalysisEvidenceRetriever(knowledge, clock=lambda: NOW).retrieve(
        analysis(), limit_per_query=3
    )

    assert package.analysis_id == "analysis-test"
    assert package.created_at == NOW
    assert [item.query_id for item in package.bundles] == [
        "condition-memory-request-low",
        "recommendation-increase-cpu-limit",
    ]
    recommendation = package.bundles[1]
    assert recommendation.condition_ids == ("cpu-throttle-a",)
    assert recommendation.statistic_ids == ("s-cpu",)
    assert recommendation.analysis_evidence_ids == ("e-cpu",)
    assert recommendation.query == recommendation.retrieval.query
    assert all(limit == 20 for _, limit in knowledge.calls)


def test_analysis_retrieval_groups_duplicate_condition_types() -> None:
    report = analysis()
    duplicate = report.conditions[0].model_copy(
        update={"condition_id": "cpu-throttle-b"}
    )
    report = report.model_copy(
        update={"conditions": (*report.conditions, duplicate), "recommendations": ()}
    )

    package = AnalysisEvidenceRetriever(FakeKnowledge(), clock=lambda: NOW).retrieve(
        report
    )

    cpu = next(item for item in package.bundles if "cpu-throttling" in item.query_id)
    assert cpu.condition_ids == ("cpu-throttle-a", "cpu-throttle-b")
    assert len(package.bundles) == 2


def test_analysis_retrieval_handles_no_findings_and_failures() -> None:
    report = analysis().model_copy(
        update={
            "sufficiency": AnalysisSufficiency.INSUFFICIENT,
            "conditions": (),
            "recommendations": (),
        }
    )
    package = AnalysisEvidenceRetriever(FakeKnowledge(), clock=lambda: NOW).retrieve(
        report
    )
    assert package.bundles == ()

    with pytest.raises(RAGError, match="between 1 and 20"):
        AnalysisEvidenceRetriever(FakeKnowledge()).retrieve(report, 0)
    with pytest.raises(RAGError, match="naive"):
        AnalysisEvidenceRetriever(
            FakeKnowledge(), clock=lambda: datetime(2026, 1, 1)
        ).retrieve(report)
    with pytest.raises(RAGError, match="offline"):
        AnalysisEvidenceRetriever(FakeKnowledge(fail=True)).retrieve(analysis())

    invalid = analysis().model_copy(
        update={
            "recommendations": (
                analysis()
                .recommendations[0]
                .model_copy(update={"condition_ids": ("missing",)}),
            )
        }
    )
    with pytest.raises(RAGError, match="invalid deterministic analysis"):
        AnalysisEvidenceRetriever(FakeKnowledge()).retrieve(invalid)

    invalid_source = analysis().model_copy(
        update={
            "recommendations": (
                analysis()
                .recommendations[0]
                .model_copy(update={"recommendation_id": "!!!"}),
            )
        }
    )
    with pytest.raises(RAGError, match="stable query ID"):
        AnalysisEvidenceRetriever(FakeKnowledge()).retrieve(invalid_source)


def test_evaluation_dataset_load_and_digest_are_canonical(tmp_path: Path) -> None:
    value = dataset()
    reordered = tmp_path / "reordered.json"
    reordered.write_text(
        json.dumps(value.model_dump(mode="json"), sort_keys=True), encoding="utf-8"
    )

    assert load_evaluation_dataset(reordered) == value
    assert evaluation_dataset_digest(load_evaluation_dataset(reordered)) == (
        evaluation_dataset_digest(value)
    )
    assert len(value.cases) == 6
    assert value.authored_by != value.reviewed_by

    for content in ("{", "[]"):
        malformed = tmp_path / f"bad-{len(content)}.json"
        malformed.write_text(content, encoding="utf-8")
        with pytest.raises(RAGError, match="invalid retrieval evaluation dataset"):
            load_evaluation_dataset(malformed)
    with pytest.raises(RAGError, match="invalid retrieval evaluation dataset"):
        load_evaluation_dataset(tmp_path / "missing.json")


def test_evaluator_calculates_passing_ranked_metrics() -> None:
    value = dataset()
    report = RetrievalEvaluator(
        FakeKnowledge(ideal_results(value)), clock=lambda: NOW
    ).evaluate(value)

    assert report.passed is True
    assert report.mean_recall_at_k == 1
    assert report.mean_reciprocal_rank_at_k == 1
    assert report.mean_ndcg_at_k == 1
    assert len(report.cases) == 6
    assert all(case.hits[0].judged_relevance == 3 for case in report.cases)
    assert report.dataset_sha256 == evaluation_dataset_digest(value)


def test_evaluator_reports_failed_quality_without_raising() -> None:
    value = dataset()
    results: dict[str, tuple[str, ...]] = {case.query: () for case in value.cases}
    report = RetrievalEvaluator(FakeKnowledge(results), clock=lambda: NOW).evaluate(
        value
    )

    assert report.passed is False
    assert report.mean_recall_at_k == 0
    assert report.mean_reciprocal_rank_at_k == 0
    assert report.mean_ndcg_at_k == 0
    assert all(case.hits == () for case in report.cases)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"repository_version": "2.0.0"}, "repository version"),
        ({"index_schema_version": "1.0"}, "index schema"),
        ({"embedding_model": "other/model"}, "embedding model"),
    ],
)
def test_evaluator_rejects_incompatible_dataset(
    update: dict[str, str], message: str
) -> None:
    with pytest.raises(RAGError, match=message):
        RetrievalEvaluator(FakeKnowledge()).evaluate(
            dataset().model_copy(update=update)
        )


def test_evaluator_rejects_empty_missing_and_external_failures() -> None:
    value = dataset()
    with pytest.raises(RAGError, match="invalid retrieval evaluation dataset"):
        RetrievalEvaluator(FakeKnowledge()).evaluate(
            value.model_copy(update={"reviewed_by": value.authored_by})
        )
    with pytest.raises(RAGError, match="empty knowledge index"):
        RetrievalEvaluator(FakeKnowledge(chunks=())).evaluate(value)
    with pytest.raises(RAGError, match="missing chunks"):
        missing = (
            value.cases[0].judgments[0].model_copy(update={"chunk_id": "missing-chunk"})
        )
        case = value.cases[0].model_copy(update={"judgments": (missing,)})
        RetrievalEvaluator(FakeKnowledge()).evaluate(
            value.model_copy(update={"cases": (case, *value.cases[1:])})
        )
    with pytest.raises(RAGError, match="offline"):
        RetrievalEvaluator(FakeKnowledge(fail=True)).evaluate(value)
    with pytest.raises(RAGError, match="naive"):
        RetrievalEvaluator(
            FakeKnowledge(), clock=lambda: datetime(2026, 1, 1)
        ).evaluate(value)


def test_evaluator_wraps_retrieval_failure_after_index_validation() -> None:
    class SearchFailure(FakeKnowledge):
        def retrieve(
            self,
            query: str,
            limit: int = 5,
            document_types: tuple[KnowledgeDocumentType, ...] = (),
        ) -> KnowledgeRetrievalResult:
            raise KnowledgeIndexError("search failed")

    with pytest.raises(RAGError, match="search failed"):
        RetrievalEvaluator(SearchFailure(), clock=lambda: NOW).evaluate(dataset())


def test_m8_contracts_reject_inconsistent_content() -> None:
    value = dataset()
    with pytest.raises(ValidationError, match="independent"):
        RetrievalEvaluationDataset.model_validate(
            {**value.model_dump(), "reviewed_by": value.authored_by}
        )
    with pytest.raises(ValidationError, match="sorted by case"):
        RetrievalEvaluationDataset.model_validate(
            {**value.model_dump(), "cases": tuple(reversed(value.cases))}
        )
    duplicate_case = value.model_copy(update={"cases": (value.cases[0],) * 2})
    with pytest.raises(ValidationError, match="duplicate case"):
        RetrievalEvaluationDataset.model_validate(duplicate_case.model_dump())
    with pytest.raises(ValidationError, match="semantic"):
        RetrievalEvaluationDataset.model_validate(
            {**value.model_dump(), "dataset_version": "bad"}
        )
    with pytest.raises(ValidationError, match="timezone"):
        RetrievalEvaluationDataset.model_validate(
            {**value.model_dump(), "reviewed_at": "2026-01-01T00:00:00"}
        )

    case = value.cases[0]
    with pytest.raises(ValidationError, match="surrounding whitespace"):
        type(case).model_validate({**case.model_dump(), "query": " bad "})
    with pytest.raises(ValidationError, match="duplicate chunk"):
        type(case).model_validate(
            {**case.model_dump(), "judgments": (case.judgments[0],) * 2}
        )
    with pytest.raises(ValidationError, match="sorted by chunk"):
        type(case).model_validate(
            {**case.model_dump(), "judgments": tuple(reversed(case.judgments))}
        )

    package = AnalysisEvidenceRetriever(FakeKnowledge(), clock=lambda: NOW).retrieve(
        analysis()
    )
    bundle = package.bundles[0]
    chunk = canonical_chunks()[0]
    with pytest.raises(ValidationError, match="semantic and lexical"):
        KnowledgeRetrievalHit(
            score=0.5,
            semantic_score=0.5,
            chunk=chunk,
        )
    with pytest.raises(ValidationError, match="match its retrieval"):
        OperationalEvidenceBundle.model_validate(
            {**bundle.model_dump(), "query": "different"}
        )
    with pytest.raises(ValidationError, match="duplicate condition"):
        OperationalEvidenceBundle.model_validate(
            {**bundle.model_dump(), "condition_ids": (bundle.condition_ids[0],) * 2}
        )
    with pytest.raises(ValidationError, match="sorted by query"):
        OperationalEvidencePackage.model_validate(
            {**package.model_dump(), "bundles": tuple(reversed(package.bundles))}
        )
    with pytest.raises(ValidationError, match="duplicate query"):
        OperationalEvidencePackage.model_validate(
            {**package.model_dump(), "bundles": (bundle, bundle)}
        )
    with pytest.raises(ValidationError, match="timezone"):
        OperationalEvidencePackage.model_validate(
            {**package.model_dump(), "created_at": "2026-01-01T00:00:00"}
        )
    bad_identity = package.bundles[0].model_copy(update={"analysis_id": "other"})
    with pytest.raises(ValidationError, match="identity"):
        OperationalEvidencePackage.model_validate(
            {**package.model_dump(), "bundles": (bad_identity,)}
        )

    hit = RetrievalEvaluationHit(
        rank=1,
        chunk_id="one",
        point_id=canonical_chunks()[0].point_id,
        score=0.5,
        semantic_score=0.4,
        lexical_match_ratio=0.8,
    )
    result_data = {
        "case_id": "case",
        "query": "query",
        "k": 1,
        "hits": (hit,),
        "relevant_retrieved_chunk_ids": (),
        "recall_at_k": 0,
        "reciprocal_rank_at_k": 0,
        "ndcg_at_k": 0,
    }
    with pytest.raises(ValidationError, match="contiguous"):
        RetrievalEvaluationCaseResult.model_validate(
            {**result_data, "hits": (hit.model_copy(update={"rank": 2}),)}
        )
    with pytest.raises(ValidationError, match="unique chunk"):
        RetrievalEvaluationCaseResult.model_validate(
            {**result_data, "k": 2, "hits": (hit, hit.model_copy(update={"rank": 2}))}
        )
    with pytest.raises(ValidationError, match="cannot exceed"):
        RetrievalEvaluationCaseResult.model_validate(
            {**result_data, "hits": (hit, hit.model_copy(update={"rank": 2}))}
        )

    thresholds = RetrievalMetricThresholds(
        mean_recall_at_k=0.5,
        mean_reciprocal_rank_at_k=0.5,
        mean_ndcg_at_k=0.5,
    )
    case_result = RetrievalEvaluationCaseResult(**result_data)
    report_data = {
        "dataset_version": "1.0.0",
        "dataset_sha256": "a" * 64,
        "repository_version": "1.0.0",
        "evaluated_at": NOW,
        "thresholds": thresholds,
        "cases": (case_result,),
        "mean_recall_at_k": 0,
        "mean_reciprocal_rank_at_k": 0,
        "mean_ndcg_at_k": 0,
        "passed": True,
    }
    with pytest.raises(ValidationError, match="pass status"):
        RetrievalEvaluationReport.model_validate(report_data)
    with pytest.raises(ValidationError, match="duplicate cases"):
        RetrievalEvaluationReport.model_validate(
            {
                **report_data,
                "cases": (case_result, case_result),
                "passed": False,
            }
        )
    with pytest.raises(ValidationError, match="semantic"):
        RetrievalEvaluationReport.model_validate(
            {**report_data, "dataset_version": "bad", "passed": False}
        )
    with pytest.raises(ValidationError, match="timezone"):
        RetrievalEvaluationReport.model_validate(
            {**report_data, "evaluated_at": "2026-01-01T00:00:00", "passed": False}
        )
