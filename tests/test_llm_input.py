"""Offline M9 LLM input construction, integrity, and persistence tests."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

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
    EvidenceQueryKind,
    KnowledgeChunk,
    KnowledgeDocumentType,
    KnowledgeRetrievalHit,
    KnowledgeRetrievalResult,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeVerificationStatus,
    LLMInputArtifact,
    LLMInputPackage,
    LLMRetrievalQuery,
    LLMRetrievalStatus,
    OperationalEvidenceBundle,
    OperationalEvidencePackage,
    ResourceRecommendation,
    WorkloadIdentity,
)
from kri.llm_input import (
    MAX_EXCERPT_CHARS,
    LLMInputBuilder,
    LLMInputError,
    LLMInputStore,
    LLMInputStoreError,
    canonical_digest,
    package_digest,
)

NOW = datetime(2026, 11, 1, 16, 0, tzinfo=UTC)


def analysis() -> AnalysisReport:
    evidence = (
        AnalysisEvidence(
            evidence_id="e-config",
            source="workload_configuration",
            resource_field="cpu_limit",
            sample_count=1,
            description="exact configured CPU limit",
        ),
        AnalysisEvidence(
            evidence_id="e-series",
            source="normalized_series",
            signal_name="cpu_cfs_throttled_periods_total",
            labels={"pod": "app-a", "container": "app"},
            interval_start=NOW,
            interval_end=datetime(2026, 11, 1, 16, 1, tzinfo=UTC),
            sample_count=5,
            description="exact throttle counter series",
        ),
        AnalysisEvidence(
            evidence_id="e-unused",
            source="quality_report",
            sample_count=0,
            description="not referenced by a finding",
        ),
    )
    statistics = (
        CalculatedStatistic(
            statistic_id="s-throttle",
            name="CPU throttled-period ratio",
            value=0.3333333333333333,
            unit="ratio",
            aggregation_scope="pod/container",
            labels={"pod": "app-a", "container": "app"},
            evidence_ids=("e-series", "e-config"),
        ),
        CalculatedStatistic(
            statistic_id="s-unused",
            name="HTTP throughput",
            value=17.125,
            unit="requests/second",
            aggregation_scope="workload",
            labels={},
            evidence_ids=("e-unused",),
        ),
    )
    condition = DetectedCondition(
        condition_id="cpu-throttling-app-a",
        condition_type="cpu_throttling_high",
        severity=ConditionSeverity.WARNING,
        message="CPU throttling crosses the policy threshold",
        observed_value=0.3333333333333333,
        threshold=0.2,
        statistic_ids=("s-throttle",),
        evidence_ids=("e-series",),
    )
    recommendation = ResourceRecommendation(
        recommendation_id="increase-cpu-limit",
        resource="cpu_limit",
        current_value="100m",
        recommended_value="140m",
        lower_bound="100m",
        upper_bound="200m",
        rationale="Add bounded CPU headroom after measured throttling.",
        condition_ids=(condition.condition_id,),
        statistic_ids=("s-throttle",),
        evidence_ids=("e-config", "e-series"),
    )
    return AnalysisReport(
        analysis_id="analysis-m9",
        observation_id="observation-m9",
        created_at=NOW,
        identity=WorkloadIdentity(
            cluster="kind-kube-optimizer",
            namespace="payments",
            deployment_name="kri-workload",
            deployment_uid="uid-123",
        ),
        sufficiency=AnalysisSufficiency.PARTIAL,
        provenance=AnalysisProvenance(observation_source_digest_sha256="a" * 64),
        statistics=statistics,
        conditions=(condition,),
        recommendations=(recommendation,),
        evidence=evidence,
        risks_and_uncertainties=(
            "The 60-second interval may not represent sustained demand.",
            "The recommendation has not been validated by a post-change experiment.",
        ),
    )


def source() -> KnowledgeSource:
    return KnowledgeSource(
        source_id="official-source",
        source_type=KnowledgeSourceType.OFFICIAL_DOCUMENTATION,
        title="Resource management",
        publisher="Kubernetes",
        uri="https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/",
        version="v1.35",
        accessed_at=NOW,
        verification_notes="Verified against the official documentation.",
    )


def chunk(
    index: int = 1, text: str = "Inspect CPU throttling before adjustment."
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=f"cpu-runbook-section-{index}",
        point_id=UUID(int=index),
        repository_version="1.0.0",
        document_id="cpu-runbook",
        document_type=KnowledgeDocumentType.DIAGNOSTIC_RUNBOOK,
        document_title="CPU throttling runbook",
        document_version="1.0.0",
        verification_status=KnowledgeVerificationStatus.VERIFIED,
        tags=("cpu",),
        sources=(source(),),
        section="Procedure",
        ordinal=index,
        text=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def evidence(
    report: AnalysisReport | None = None,
    hits: tuple[KnowledgeRetrievalHit, ...] | None = None,
) -> OperationalEvidencePackage:
    report = report or analysis()
    if hits is None:
        hits = (
            KnowledgeRetrievalHit(
                score=0.8123456789012345,
                semantic_score=0.8,
                lexical_match_ratio=0.88230452600823,
                chunk=chunk(),
            ),
        )
    query = "Kubernetes operational guidance for cpu limit throttling"
    bundle = OperationalEvidenceBundle(
        query_id="recommendation-increase-cpu-limit",
        query_kind=EvidenceQueryKind.RECOMMENDATION,
        source_id="increase-cpu-limit",
        analysis_id=report.analysis_id,
        observation_id=report.observation_id,
        condition_ids=("cpu-throttling-app-a",),
        statistic_ids=("s-throttle",),
        analysis_evidence_ids=("e-config", "e-series"),
        query=query,
        retrieval=KnowledgeRetrievalResult(
            query=query,
            limit=max(1, len(hits)),
            collection_name="m9-test",
            repository_version="1.0.0",
            hits=hits,
        ),
    )
    return OperationalEvidencePackage(
        analysis_id=report.analysis_id,
        observation_id=report.observation_id,
        analysis_source_digest_sha256=(
            report.provenance.observation_source_digest_sha256
        ),
        analysis_sufficiency=report.sufficiency,
        created_at=NOW,
        bundles=(bundle,),
    )


def build() -> LLMInputPackage:
    return LLMInputBuilder(clock=lambda: NOW).build(analysis(), evidence())


def test_build_preserves_exact_findings_closure_trace_and_uncertainty() -> None:
    report = analysis()
    retrieved = evidence(report)
    package = LLMInputBuilder(clock=lambda: NOW).build(report, retrieved)

    assert package.package_id == "llm-analysis-m9"
    assert package.analysis_digest_sha256 == canonical_digest(report)
    assert package.operational_evidence_digest_sha256 == canonical_digest(retrieved)
    assert package.conditions == report.conditions
    assert package.recommendations == report.recommendations
    assert package.risks_and_uncertainties == report.risks_and_uncertainties
    assert [item.statistic_id for item in package.statistics] == ["s-throttle"]
    assert package.statistics[0].value == 0.3333333333333333
    assert [item.evidence_id for item in package.analysis_evidence] == [
        "e-config",
        "e-series",
    ]
    assert package.retrieval_status is LLMRetrievalStatus.RETRIEVED
    assert package.retrieval_queries[0].retrieved_hit_count == 1
    assert package.retrieval_hits[0].score == 0.8123456789012345
    assert package.retrieval_hits[0].semantic_score == 0.8
    assert package.evidence_excerpts[0].sources == (source(),)
    assert package.evidence_excerpts[0].content_sha256 == chunk().content_sha256


def test_build_bounds_hits_deduplicates_and_truncates_excerpts() -> None:
    long_text = "x" * (MAX_EXCERPT_CHARS + 1)
    hits = tuple(
        KnowledgeRetrievalHit(
            score=0.9 - index / 10,
            semantic_score=0.9 - index / 10,
            lexical_match_ratio=0.5,
            chunk=chunk(index, long_text if index == 1 else f"text {index}"),
        )
        for index in range(1, 5)
    )
    package = LLMInputBuilder(clock=lambda: NOW).build(analysis(), evidence(hits=hits))

    assert len(package.retrieval_hits) == 3
    assert package.retrieval_queries[0].retrieved_hit_count == 4
    assert package.retrieval_queries[0].included_hit_count == 3
    assert len(package.evidence_excerpts[0].excerpt) == MAX_EXCERPT_CHARS
    assert package.evidence_excerpts[0].excerpt_truncated is True

    duplicate_hits = (hits[0], hits[0].model_copy(update={"score": 0.8}))
    duplicate_retrieval = evidence(hits=(duplicate_hits[0],))
    query = duplicate_retrieval.bundles[0]
    second = query.model_copy(
        update={
            "query_id": "condition-cpu-throttling-high",
            "query_kind": EvidenceQueryKind.CONDITION,
            "source_id": "cpu_throttling_high",
            "analysis_evidence_ids": ("e-series",),
        }
    )
    raw = duplicate_retrieval.model_copy(update={"bundles": (second, query)})
    queries, references, excerpts = LLMInputBuilder._bounded_retrieval(raw)
    assert len(queries) == 2
    assert len(references) == 2
    assert len(excerpts) == 1
    assert excerpts[0].query_ids == (
        "condition-cpu-throttling-high",
        "recommendation-increase-cpu-limit",
    )


def test_build_handles_no_findings_and_no_hits() -> None:
    empty_analysis = analysis().model_copy(
        update={"conditions": (), "recommendations": ()}
    )
    empty_evidence = OperationalEvidencePackage(
        analysis_id=empty_analysis.analysis_id,
        observation_id=empty_analysis.observation_id,
        analysis_source_digest_sha256="a" * 64,
        analysis_sufficiency=empty_analysis.sufficiency,
        created_at=NOW,
        bundles=(),
    )
    empty = LLMInputBuilder(clock=lambda: NOW).build(empty_analysis, empty_evidence)
    assert empty.retrieval_status is LLMRetrievalStatus.NO_FINDINGS
    assert empty.statistics == ()
    assert empty.analysis_evidence == ()

    no_hits = LLMInputBuilder(clock=lambda: NOW).build(analysis(), evidence(hits=()))
    assert no_hits.retrieval_status is LLMRetrievalStatus.NO_HITS
    assert no_hits.retrieval_queries[0].included_hit_count == 0
    assert no_hits.evidence_excerpts == ()


@pytest.mark.parametrize(
    ("evidence_update", "message"),
    [
        ({"analysis_id": "other"}, "identities"),
        ({"observation_id": "other"}, "identities"),
        ({"analysis_source_digest_sha256": "b" * 64}, "digests"),
        ({"analysis_sufficiency": AnalysisSufficiency.SUFFICIENT}, "sufficiency"),
    ],
)
def test_build_rejects_mismatched_sources(
    evidence_update: dict[str, object], message: str
) -> None:
    original = evidence()
    bundle_update = {
        key: value
        for key, value in evidence_update.items()
        if key in {"analysis_id", "observation_id"}
    }
    bundles = tuple(item.model_copy(update=bundle_update) for item in original.bundles)
    value = original.model_copy(update={**evidence_update, "bundles": bundles})
    with pytest.raises(LLMInputError, match=message):
        LLMInputBuilder(clock=lambda: NOW).build(analysis(), value)


@pytest.mark.parametrize(
    ("bundle_update", "message"),
    [
        ({"condition_ids": ("unknown",)}, "unknown M5 condition"),
        ({"statistic_ids": ("unknown",)}, "unknown M5 statistic"),
        ({"analysis_evidence_ids": ("unknown",)}, "unknown M5 evidence"),
        ({"source_id": "unknown"}, "unknown source"),
    ],
)
def test_build_rejects_dangling_bundle_references(
    bundle_update: dict[str, object], message: str
) -> None:
    original = evidence()
    altered = original.bundles[0].model_copy(update=bundle_update)
    value = original.model_copy(update={"bundles": (altered,)})
    with pytest.raises(LLMInputError, match=message):
        LLMInputBuilder(clock=lambda: NOW).build(analysis(), value)


def test_build_rejects_missing_coverage_scores_ids_and_invalid_clock() -> None:
    with pytest.raises(LLMInputError, match="every M5 recommendation"):
        LLMInputBuilder(clock=lambda: NOW).build(
            analysis(), evidence().model_copy(update={"bundles": ()})
        )

    hit = (
        evidence()
        .bundles[0]
        .retrieval.hits[0]
        .model_copy(update={"semantic_score": None, "lexical_match_ratio": None})
    )
    with pytest.raises(LLMInputError, match="lacks rerank"):
        LLMInputBuilder(clock=lambda: NOW).build(analysis(), evidence(hits=(hit,)))

    with pytest.raises(LLMInputError, match="naive"):
        LLMInputBuilder(clock=lambda: NOW.replace(tzinfo=None)).build(
            analysis(), evidence()
        )
    with pytest.raises(LLMInputError, match="package ID"):
        LLMInputBuilder(clock=lambda: NOW).build(
            analysis(), evidence(), package_id="INVALID"
        )

    long_id = "a" * 63
    report = analysis().model_copy(update={"analysis_id": long_id})
    retrieved = evidence(report).model_copy(
        update={
            "bundles": tuple(
                item.model_copy(update={"analysis_id": long_id})
                for item in evidence(report).bundles
            )
        }
    )
    package_id = LLMInputBuilder(clock=lambda: NOW).build(report, retrieved).package_id
    assert package_id.startswith("llm-input-")

    malformed_analysis = analysis().model_copy(
        update={"statistics": analysis().statistics * 2}
    )
    with pytest.raises(LLMInputError, match="invalid M5 or M8"):
        LLMInputBuilder(clock=lambda: NOW).build(malformed_analysis, evidence())


def test_pair_validation_covers_condition_bundles_and_global_bounds() -> None:
    report = analysis().model_copy(update={"recommendations": ()})
    original = evidence().bundles[0]
    condition_bundle = original.model_copy(
        update={
            "query_id": "condition-cpu-throttling-high",
            "query_kind": EvidenceQueryKind.CONDITION,
            "source_id": "cpu_throttling_high",
            "analysis_evidence_ids": ("e-series",),
        }
    )
    value = evidence(report).model_copy(update={"bundles": (condition_bundle,)})
    LLMInputBuilder._validate_pair(report, value)

    bad_source = value.model_copy(
        update={
            "bundles": (condition_bundle.model_copy(update={"source_id": "wrong"}),)
        }
    )
    with pytest.raises(LLMInputError, match="invalid source type"):
        LLMInputBuilder._validate_pair(report, bad_source)

    wrong_condition_refs = value.model_copy(
        update={
            "bundles": (
                condition_bundle.model_copy(update={"statistic_ids": ("s-unused",)}),
            )
        }
    )
    with pytest.raises(LLMInputError, match="does not match its M5 sources"):
        LLMInputBuilder._validate_pair(report, wrong_condition_refs)

    wrong_recommendation_refs = evidence().model_copy(
        update={
            "bundles": (original.model_copy(update={"statistic_ids": ("s-unused",)}),)
        }
    )
    with pytest.raises(LLMInputError, match="does not match its M5 source"):
        LLMInputBuilder._validate_pair(analysis(), wrong_recommendation_refs)

    additional_condition = (
        analysis()
        .conditions[0]
        .model_copy(update={"condition_id": "cpu-throttling-app-b"})
    )
    report_with_uncovered = analysis().model_copy(
        update={"conditions": (*analysis().conditions, additional_condition)}
    )
    with pytest.raises(LLMInputError, match="every M5 condition"):
        LLMInputBuilder._validate_pair(report_with_uncovered, evidence())

    no_findings = analysis().model_copy(
        update={"conditions": (), "recommendations": ()}
    )
    empty_refs = condition_bundle.model_copy(
        update={
            "condition_ids": (),
            "statistic_ids": (),
            "analysis_evidence_ids": (),
        }
    )
    unexpected = evidence(no_findings).model_copy(update={"bundles": (empty_refs,)})
    with pytest.raises(LLMInputError, match="finding-free"):
        LLMInputBuilder._validate_pair(no_findings, unexpected)

    too_many = evidence().model_copy(update={"bundles": (original,) * 51})
    with pytest.raises(LLMInputError, match="50-query"):
        LLMInputBuilder._validate_pair(analysis(), too_many)


def test_retrieval_excerpt_global_bound() -> None:
    original = evidence().bundles[0]
    bundles = []
    for query_index in range(5):
        hits = tuple(
            KnowledgeRetrievalHit(
                score=0.9 - rank / 10,
                semantic_score=0.9 - rank / 10,
                lexical_match_ratio=0.5,
                chunk=chunk(query_index * 3 + rank + 1),
            )
            for rank in range(3)
        )
        query = f"query {query_index}"
        bundles.append(
            original.model_copy(
                update={
                    "query_id": f"condition-q{query_index}",
                    "query_kind": EvidenceQueryKind.CONDITION,
                    "source_id": "cpu_throttling_high",
                    "query": query,
                    "retrieval": original.retrieval.model_copy(
                        update={"query": query, "limit": 3, "hits": hits}
                    ),
                }
            )
        )
    raw = evidence().model_copy(update={"bundles": tuple(bundles)})
    _, references, excerpts = LLMInputBuilder._bounded_retrieval(raw)
    assert len(references) == 15
    assert len(excerpts) == 12
    assert sum(item.selected_as_excerpt for item in references) == 12


def test_store_round_trip_inspection_immutability_and_corruption(
    tmp_path: Path,
) -> None:
    package = build()
    store = LLMInputStore(tmp_path)
    path = store.save(package)
    assert store.load(package.package_id) == package
    summary = store.inspect(package.package_id)
    assert summary.package_sha256 == package_digest(package)
    assert summary.condition_count == summary.recommendation_count == 1
    assert summary.statistic_count == 1
    assert summary.uncertainty_count == 2
    assert (
        summary.query_count == summary.hit_reference_count == summary.excerpt_count == 1
    )

    with pytest.raises(LLMInputStoreError, match="already exists"):
        store.save(package)

    artifact = json.loads(path.read_text())
    artifact["package"]["statistics"][0]["value"] = 999.0
    path.write_text(json.dumps(artifact))
    with pytest.raises(LLMInputStoreError, match="digest does not match"):
        store.load(package.package_id)


def test_store_rejects_invalid_missing_malformed_and_io_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LLMInputStore(tmp_path)
    with pytest.raises(LLMInputStoreError, match=r"invalid.*ID"):
        store.load("INVALID")
    with pytest.raises(LLMInputStoreError, match="does not exist"):
        store.load("missing")

    malformed = tmp_path / "malformed.json"
    malformed.write_text("not json")
    with pytest.raises(LLMInputStoreError, match="invalid LLM input artifact"):
        store.load("malformed")

    bad = build().model_copy(update={"instructions": ("unsafe",)})
    with pytest.raises(LLMInputStoreError, match="invalid LLM input package"):
        store.save(bad)

    file_parent = tmp_path / "file"
    file_parent.write_text("x")
    with pytest.raises(LLMInputStoreError):
        LLMInputStore(file_parent).save(build())

    writable = tmp_path / "writable"

    def deny_link(*_: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr("kri.llm_input.os.link", deny_link)
    with pytest.raises(LLMInputStoreError, match="denied"):
        LLMInputStore(writable).save(build())


def test_artifact_and_package_contracts_reject_semantic_tampering() -> None:
    package = build()
    with pytest.raises(ValidationError, match="digest does not match"):
        LLMInputArtifact(package_sha256="0" * 64, package=package)

    malformed = package.model_dump(mode="json")
    malformed["retrieval_status"] = "no_hits"
    with pytest.raises(ValidationError, match="status"):
        LLMInputPackage.model_validate(malformed)

    malformed = package.model_dump(mode="json")
    malformed["statistics"] = []
    with pytest.raises(ValidationError, match="minimal finding closure"):
        LLMInputPackage.model_validate(malformed)

    malformed = package.model_dump(mode="json")
    malformed["analysis_evidence"] = malformed["analysis_evidence"][:1]
    with pytest.raises(ValidationError, match="complete finding closure"):
        LLMInputPackage.model_validate(malformed)


def test_llm_contracts_reject_malformed_identity_order_and_references() -> None:
    package = build()
    base = package.model_dump(mode="json")

    query = package.retrieval_queries[0]
    with pytest.raises(ValidationError, match="cannot exceed"):
        LLMRetrievalQuery.model_validate(
            {**query.model_dump(mode="json"), "retrieved_hit_count": 0}
        )

    for field, value, message in (
        ("document_id", "INVALID", "lowercase DNS"),
        ("document_version", "one", "semantic"),
    ):
        excerpt = package.evidence_excerpts[0].model_dump(mode="json")
        excerpt[field] = value
        malformed = {**base, "evidence_excerpts": [excerpt]}
        with pytest.raises(ValidationError, match=message):
            LLMInputPackage.model_validate(malformed)

    for field, value, message in (
        ("package_id", "INVALID", "lowercase DNS"),
        ("created_at", "2026-11-01T16:00:00", "timezone"),
    ):
        malformed = {**base, field: value}
        with pytest.raises(ValidationError, match=message):
            LLMInputPackage.model_validate(malformed)

    duplicate = {**base, "retrieval_queries": [base["retrieval_queries"][0]] * 2}
    with pytest.raises(ValidationError, match="duplicate retrieval query"):
        LLMInputPackage.model_validate(duplicate)

    second_hit = {
        **base["retrieval_hits"][0],
        "rank": 2,
        "chunk_id": "cpu-runbook-section-2",
        "point_id": str(UUID(int=2)),
        "selected_as_excerpt": False,
    }
    two_hits = json.loads(json.dumps(base))
    two_hits["retrieval_queries"][0]["included_hit_count"] = 2
    two_hits["retrieval_queries"][0]["retrieved_hit_count"] = 2
    two_hits["retrieval_hits"].append(second_hit)

    reversed_hits = {
        **two_hits,
        "retrieval_hits": list(reversed(two_hits["retrieval_hits"])),
    }
    with pytest.raises(ValidationError, match="must be sorted"):
        LLMInputPackage.model_validate(reversed_hits)

    two_excerpt_package = (
        LLMInputBuilder(clock=lambda: NOW)
        .build(
            analysis(),
            evidence(
                hits=(
                    evidence().bundles[0].retrieval.hits[0],
                    KnowledgeRetrievalHit(
                        score=0.7,
                        semantic_score=0.7,
                        lexical_match_ratio=0.5,
                        chunk=chunk(2),
                    ),
                )
            ),
        )
        .model_dump(mode="json")
    )
    two_excerpt_package["evidence_excerpts"].reverse()
    with pytest.raises(ValidationError, match="records must be sorted"):
        LLMInputPackage.model_validate(two_excerpt_package)

    for update, message in (
        ({"retrieval_hits": [base["retrieval_hits"][0]] * 2}, "duplicate ranked"),
        (
            {"retrieval_hits": [{**base["retrieval_hits"][0], "query_id": "unknown"}]},
            "unknown query",
        ),
        (
            {"retrieval_hits": [{**base["retrieval_hits"][0], "rank": 2}]},
            "ranks do not match",
        ),
        (
            {
                "retrieval_hits": [
                    {**base["retrieval_hits"][0], "selected_as_excerpt": False}
                ]
            },
            "do not match evidence excerpts",
        ),
        (
            {
                "evidence_excerpts": [
                    {**base["evidence_excerpts"][0], "query_ids": ["unknown"]}
                ]
            },
            "query trace",
        ),
    ):
        malformed = {**base, **update}
        with pytest.raises(ValidationError, match=message):
            LLMInputPackage.model_validate(malformed)

    no_trace = {
        **base,
        "retrieval_status": "no_hits",
        "retrieval_queries": [],
        "retrieval_hits": [],
        "evidence_excerpts": [],
    }
    with pytest.raises(ValidationError, match="findings require"):
        LLMInputPackage.model_validate(no_trace)

    empty = (
        LLMInputBuilder(clock=lambda: NOW)
        .build(
            analysis().model_copy(update={"conditions": (), "recommendations": ()}),
            OperationalEvidencePackage(
                analysis_id="analysis-m9",
                observation_id="observation-m9",
                analysis_source_digest_sha256="a" * 64,
                analysis_sufficiency=AnalysisSufficiency.PARTIAL,
                created_at=NOW,
                bundles=(),
            ),
        )
        .model_dump(mode="json")
    )
    empty["retrieval_queries"] = [base["retrieval_queries"][0]]
    empty["retrieval_queries"][0]["included_hit_count"] = 0
    with pytest.raises(ValidationError, match="finding-free"):
        LLMInputPackage.model_validate(empty)
