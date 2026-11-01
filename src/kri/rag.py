"""M8 analysis-grounded evidence retrieval and fixed-dataset evaluation."""

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from kri.contracts import (
    AnalysisReport,
    EvidenceQueryKind,
    KnowledgeDocumentType,
    KnowledgeRetrievalHit,
    KnowledgeRetrievalResult,
    OperationalEvidenceBundle,
    OperationalEvidencePackage,
    RetrievalEvaluationCase,
    RetrievalEvaluationCaseResult,
    RetrievalEvaluationDataset,
    RetrievalEvaluationHit,
    RetrievalEvaluationReport,
)
from kri.knowledge_index import (
    EMBEDDING_MODEL,
    INDEX_SCHEMA_VERSION,
    KnowledgeIndexError,
    KnowledgeInspectionAPI,
)

RETRIEVER_VERSION = "1.0"
EVALUATOR_VERSION = "1.0"
QUERY_ID_PATTERN = re.compile(r"[^a-z0-9]+")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "can",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "or",
    "should",
    "the",
    "to",
    "used",
    "what",
    "when",
    "while",
    "why",
    "with",
}


class RAGError(RuntimeError):
    """M8 retrieval or evaluation could not be completed safely."""


def _slug(value: str) -> str:
    result = QUERY_ID_PATTERN.sub("-", value.lower()).strip("-")
    if not result:
        raise RAGError("retrieval source ID cannot form a stable query ID")
    return result


def _term(value: str) -> str:
    aliases = {
        "diagnose": "diagnos",
        "diagnosed": "diagnos",
        "diagnosis": "diagnos",
        "limits": "limit",
        "requests": "request",
        "verification": "verif",
        "verified": "verif",
        "verify": "verif",
    }
    if value in aliases:
        return aliases[value]
    if len(value) > 5 and value.endswith("ing"):
        return value[:-3]
    if len(value) > 4 and value.endswith("ed"):
        return value[:-2]
    if len(value) > 4 and value.endswith("s"):
        return value[:-1]
    return value


def _terms(value: str) -> set[str]:
    return {
        _term(token)
        for token in TOKEN_PATTERN.findall(value.lower())
        if token not in STOP_WORDS
    }


def _preferred_document_type(query: str) -> KnowledgeDocumentType:
    terms = _terms(query)
    if terms & {"cadence", "failure", "incident", "inflat", "mismatch", "precision"}:
        return KnowledgeDocumentType.HISTORICAL_INCIDENT
    if terms & {"difference", "meaning", "semantic"}:
        return KnowledgeDocumentType.KUBERNETES_DOCUMENTATION
    if terms & {
        "adjust",
        "diagnos",
        "guidance",
        "increase",
        "procedure",
        "troubleshoot",
    }:
        return KnowledgeDocumentType.DIAGNOSTIC_RUNBOOK
    return KnowledgeDocumentType.KUBERNETES_DOCUMENTATION


class OperationalKnowledgeRetriever:
    """Rerank semantic candidates with deterministic exact-text coverage."""

    def __init__(self, knowledge: KnowledgeInspectionAPI) -> None:
        self.knowledge = knowledge

    def retrieve(self, query: str, limit: int) -> KnowledgeRetrievalResult:
        candidate_limit = 20
        candidates = self.knowledge.retrieve(
            query,
            limit=candidate_limit,
            document_types=(_preferred_document_type(query),),
        )
        query_terms = _terms(query)
        reranked: list[KnowledgeRetrievalHit] = []
        for hit in candidates.hits:
            chunk = hit.chunk
            chunk_terms = _terms(
                " ".join(
                    (
                        chunk.document_title,
                        chunk.section,
                        " ".join(chunk.tags),
                        chunk.text,
                    )
                )
            )
            lexical = (
                len(query_terms & chunk_terms) / len(query_terms)
                if query_terms
                else 0.0
            )
            final_score = 0.85 * hit.score + 0.15 * lexical
            reranked.append(
                KnowledgeRetrievalHit(
                    score=final_score,
                    semantic_score=hit.score,
                    lexical_match_ratio=lexical,
                    chunk=chunk,
                )
            )
        ordered = tuple(
            sorted(
                reranked,
                key=lambda item: (item.score, str(item.chunk.point_id)),
                reverse=True,
            )[:limit]
        )
        return KnowledgeRetrievalResult(
            query=query,
            limit=limit,
            collection_name=candidates.collection_name,
            repository_version=candidates.repository_version,
            hits=ordered,
        )


class AnalysisEvidenceRetriever:
    """Retrieve verified operational knowledge for deterministic M5 findings."""

    def __init__(
        self,
        knowledge: KnowledgeInspectionAPI,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.knowledge = knowledge
        self.operational = OperationalKnowledgeRetriever(knowledge)
        self.clock = clock

    def retrieve(
        self, analysis: AnalysisReport, limit_per_query: int = 5
    ) -> OperationalEvidencePackage:
        if not 1 <= limit_per_query <= 20:
            raise RAGError("evidence retrieval limit must be between 1 and 20")
        try:
            validated = AnalysisReport.model_validate(analysis.model_dump(mode="json"))
        except ValidationError as error:
            raise RAGError(f"invalid deterministic analysis: {error}") from error
        created_at = self.clock()
        if created_at.tzinfo is None:
            raise RAGError("evidence retriever clock returned a naive timestamp")

        conditions = {item.condition_id: item for item in validated.conditions}
        bundles: list[OperationalEvidenceBundle] = []
        represented: set[str] = set()
        for recommendation in sorted(
            validated.recommendations, key=lambda item: item.recommendation_id
        ):
            linked = tuple(conditions[item] for item in recommendation.condition_ids)
            represented.update(recommendation.condition_ids)
            condition_text = "; ".join(
                sorted(
                    {
                        f"{item.condition_type.replace('_', ' ')}: {item.message}"
                        for item in linked
                    }
                )
            )
            query = (
                "Kubernetes operational guidance for "
                f"{recommendation.resource.replace('_', ' ')}. "
                f"{recommendation.rationale} Conditions: {condition_text}"
            )
            bundles.append(
                self._bundle(
                    validated,
                    EvidenceQueryKind.RECOMMENDATION,
                    recommendation.recommendation_id,
                    tuple(recommendation.condition_ids),
                    tuple(recommendation.statistic_ids),
                    tuple(recommendation.evidence_ids),
                    query,
                    limit_per_query,
                )
            )

        remaining: dict[str, list[str]] = defaultdict(list)
        for condition in validated.conditions:
            if condition.condition_id not in represented:
                remaining[condition.condition_type].append(condition.condition_id)
        for condition_type in sorted(remaining):
            linked = tuple(
                conditions[item] for item in sorted(remaining[condition_type])
            )
            messages = "; ".join(sorted({item.message for item in linked}))
            query = (
                "Kubernetes operational diagnosis for "
                f"{condition_type.replace('_', ' ')}. {messages}"
            )
            bundles.append(
                self._bundle(
                    validated,
                    EvidenceQueryKind.CONDITION,
                    condition_type,
                    tuple(item.condition_id for item in linked),
                    tuple(
                        sorted(
                            {
                                statistic_id
                                for item in linked
                                for statistic_id in item.statistic_ids
                            }
                        )
                    ),
                    tuple(
                        sorted(
                            {
                                evidence_id
                                for item in linked
                                for evidence_id in item.evidence_ids
                            }
                        )
                    ),
                    query,
                    limit_per_query,
                )
            )

        return OperationalEvidencePackage(
            analysis_id=validated.analysis_id,
            observation_id=validated.observation_id,
            analysis_source_digest_sha256=(
                validated.provenance.observation_source_digest_sha256
            ),
            analysis_sufficiency=validated.sufficiency,
            created_at=created_at,
            bundles=tuple(sorted(bundles, key=lambda item: item.query_id)),
        )

    def _bundle(
        self,
        analysis: AnalysisReport,
        kind: EvidenceQueryKind,
        source_id: str,
        condition_ids: tuple[str, ...],
        statistic_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        query: str,
        limit: int,
    ) -> OperationalEvidenceBundle:
        try:
            retrieval = self.operational.retrieve(query, limit=limit)
        except KnowledgeIndexError as error:
            raise RAGError(str(error)) from error
        return OperationalEvidenceBundle(
            query_id=f"{kind.value}-{_slug(source_id)}",
            query_kind=kind,
            source_id=source_id,
            analysis_id=analysis.analysis_id,
            observation_id=analysis.observation_id,
            condition_ids=tuple(sorted(condition_ids)),
            statistic_ids=tuple(sorted(statistic_ids)),
            analysis_evidence_ids=tuple(sorted(evidence_ids)),
            query=query,
            retrieval=retrieval,
        )


def load_evaluation_dataset(path: Path) -> RetrievalEvaluationDataset:
    """Load and strictly validate one fixed M8 evaluation dataset."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return RetrievalEvaluationDataset.model_validate(value)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        raise RAGError(f"invalid retrieval evaluation dataset: {error}") from error


def evaluation_dataset_digest(dataset: RetrievalEvaluationDataset) -> str:
    """Return a canonical digest independent of JSON whitespace and key order."""

    canonical = json.dumps(
        dataset.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class RetrievalEvaluator:
    """Evaluate M7 semantic retrieval against reviewed graded judgments."""

    def __init__(
        self,
        knowledge: KnowledgeInspectionAPI,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.knowledge = knowledge
        self.operational = OperationalKnowledgeRetriever(knowledge)
        self.clock = clock

    def evaluate(
        self, dataset: RetrievalEvaluationDataset
    ) -> RetrievalEvaluationReport:
        try:
            validated = RetrievalEvaluationDataset.model_validate(
                dataset.model_dump(mode="json")
            )
        except ValidationError as error:
            raise RAGError(f"invalid retrieval evaluation dataset: {error}") from error
        evaluated_at = self.clock()
        if evaluated_at.tzinfo is None:
            raise RAGError("retrieval evaluator clock returned a naive timestamp")

        try:
            indexed_chunks = self.knowledge.chunks(limit=1000)
        except KnowledgeIndexError as error:
            raise RAGError(str(error)) from error
        if not indexed_chunks:
            raise RAGError("cannot evaluate an empty knowledge index")
        if validated.repository_version != indexed_chunks[0].repository_version:
            raise RAGError("evaluation dataset repository version is incompatible")
        if validated.index_schema_version != INDEX_SCHEMA_VERSION:
            raise RAGError("evaluation dataset index schema is incompatible")
        if validated.embedding_model != EMBEDDING_MODEL:
            raise RAGError("evaluation dataset embedding model is incompatible")
        indexed_ids = {chunk.chunk_id for chunk in indexed_chunks}
        judged_ids = {
            judgment.chunk_id for case in validated.cases for judgment in case.judgments
        }
        missing_ids = sorted(judged_ids - indexed_ids)
        if missing_ids:
            raise RAGError(
                "evaluation judgments reference missing chunks: "
                + ", ".join(missing_ids)
            )

        results = tuple(self._evaluate_case(case) for case in validated.cases)
        count = len(results)
        mean_recall = math.fsum(item.recall_at_k for item in results) / count
        mean_rr = math.fsum(item.reciprocal_rank_at_k for item in results) / count
        mean_ndcg = math.fsum(item.ndcg_at_k for item in results) / count
        thresholds = validated.thresholds
        passed = (
            mean_recall >= thresholds.mean_recall_at_k
            and mean_rr >= thresholds.mean_reciprocal_rank_at_k
            and mean_ndcg >= thresholds.mean_ndcg_at_k
        )
        return RetrievalEvaluationReport(
            dataset_version=validated.dataset_version,
            dataset_sha256=evaluation_dataset_digest(validated),
            repository_version=validated.repository_version,
            evaluated_at=evaluated_at,
            thresholds=thresholds,
            cases=results,
            mean_recall_at_k=mean_recall,
            mean_reciprocal_rank_at_k=mean_rr,
            mean_ndcg_at_k=mean_ndcg,
            passed=passed,
        )

    def _evaluate_case(
        self, case: RetrievalEvaluationCase
    ) -> RetrievalEvaluationCaseResult:
        try:
            retrieval = self.operational.retrieve(case.query, limit=case.k)
        except KnowledgeIndexError as error:
            raise RAGError(str(error)) from error
        grades = {item.chunk_id: item.relevance for item in case.judgments}
        hits = tuple(
            RetrievalEvaluationHit(
                rank=rank,
                chunk_id=hit.chunk.chunk_id,
                point_id=hit.chunk.point_id,
                score=hit.score,
                semantic_score=(
                    hit.semantic_score if hit.semantic_score is not None else hit.score
                ),
                lexical_match_ratio=hit.lexical_match_ratio or 0.0,
                judged_relevance=grades.get(hit.chunk.chunk_id, 0),
            )
            for rank, hit in enumerate(retrieval.hits, start=1)
        )
        relevant = tuple(hit.chunk_id for hit in hits if hit.judged_relevance > 0)
        recall = len(relevant) / len(grades)
        reciprocal_rank = next(
            (1 / hit.rank for hit in hits if hit.judged_relevance > 0), 0.0
        )
        dcg = math.fsum(
            (2**hit.judged_relevance - 1) / math.log2(hit.rank + 1)
            for hit in hits
            if hit.judged_relevance > 0
        )
        ideal_grades = sorted(grades.values(), reverse=True)[: case.k]
        ideal_dcg = math.fsum(
            (2**grade - 1) / math.log2(rank + 1)
            for rank, grade in enumerate(ideal_grades, start=1)
        )
        return RetrievalEvaluationCaseResult(
            case_id=case.case_id,
            query=case.query,
            k=case.k,
            hits=hits,
            relevant_retrieved_chunk_ids=relevant,
            recall_at_k=recall,
            reciprocal_rank_at_k=reciprocal_rank,
            ndcg_at_k=dcg / ideal_dcg,
        )
