"""M9 validated, bounded, immutable LLM input construction and storage."""

import hashlib
import json
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from kri.contracts import (
    OBSERVATION_ID_PATTERN,
    AnalysisReport,
    EvidenceQueryKind,
    KnowledgeChunk,
    KnowledgeRetrievalHit,
    LLMEvidenceExcerpt,
    LLMInputArtifact,
    LLMInputPackage,
    LLMInputSummary,
    LLMRetrievalHitReference,
    LLMRetrievalQuery,
    LLMRetrievalStatus,
    OperationalEvidencePackage,
)

BUILDER_VERSION = "1.0"
MAX_HITS_PER_QUERY = 3
MAX_EXCERPTS = 12
MAX_EXCERPT_CHARS = 600
MAX_QUERIES = 50


class LLMInputError(RuntimeError):
    """M5 and M8 inputs cannot produce a trustworthy M9 package."""


class LLMInputStoreError(RuntimeError):
    """An immutable M9 artifact could not be stored or loaded."""


def canonical_digest(value: AnalysisReport | OperationalEvidencePackage) -> str:
    """Digest a complete validated source contract independent of JSON layout."""

    canonical = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def package_digest(package: LLMInputPackage) -> str:
    """Digest one complete LLM package for its persistence envelope."""

    canonical = json.dumps(
        package.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class LLMInputBuilder:
    """Copy exact deterministic findings into a bounded source-bound handoff."""

    def __init__(
        self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.clock = clock

    def build(
        self,
        analysis: AnalysisReport,
        evidence: OperationalEvidencePackage,
        package_id: str | None = None,
    ) -> LLMInputPackage:
        try:
            validated_analysis = AnalysisReport.model_validate(
                analysis.model_dump(mode="json")
            )
            validated_evidence = OperationalEvidencePackage.model_validate(
                evidence.model_dump(mode="json")
            )
        except ValidationError as error:
            raise LLMInputError(f"invalid M5 or M8 input: {error}") from error

        created_at = self.clock()
        if created_at.tzinfo is None:
            raise LLMInputError("LLM input builder clock returned a naive timestamp")
        self._validate_pair(validated_analysis, validated_evidence)

        identifier = package_id or self._default_id(validated_analysis.analysis_id)
        if OBSERVATION_ID_PATTERN.fullmatch(identifier) is None:
            raise LLMInputError("invalid LLM input package ID")

        statistic_ids = {
            statistic_id
            for condition in validated_analysis.conditions
            for statistic_id in condition.statistic_ids
        }
        statistic_ids.update(
            statistic_id
            for recommendation in validated_analysis.recommendations
            for statistic_id in recommendation.statistic_ids
        )
        statistics = tuple(
            sorted(
                (
                    item
                    for item in validated_analysis.statistics
                    if item.statistic_id in statistic_ids
                ),
                key=lambda item: item.statistic_id,
            )
        )
        evidence_ids = {
            evidence_id
            for condition in validated_analysis.conditions
            for evidence_id in condition.evidence_ids
        }
        evidence_ids.update(
            evidence_id
            for recommendation in validated_analysis.recommendations
            for evidence_id in recommendation.evidence_ids
        )
        evidence_ids.update(
            evidence_id
            for statistic in statistics
            for evidence_id in statistic.evidence_ids
        )
        analysis_evidence = tuple(
            sorted(
                (
                    item
                    for item in validated_analysis.evidence
                    if item.evidence_id in evidence_ids
                ),
                key=lambda item: item.evidence_id,
            )
        )

        queries, hits, excerpts = self._bounded_retrieval(validated_evidence)
        has_findings = bool(
            validated_analysis.conditions or validated_analysis.recommendations
        )
        status = (
            LLMRetrievalStatus.NO_FINDINGS
            if not has_findings
            else LLMRetrievalStatus.RETRIEVED
            if hits
            else LLMRetrievalStatus.NO_HITS
        )
        return LLMInputPackage(
            package_id=identifier,
            created_at=created_at,
            identity=validated_analysis.identity,
            analysis_id=validated_analysis.analysis_id,
            observation_id=validated_analysis.observation_id,
            analysis_created_at=validated_analysis.created_at,
            evidence_created_at=validated_evidence.created_at,
            analyzer_version=validated_analysis.provenance.analyzer_version,
            policy_version=validated_analysis.provenance.policy_version,
            retriever_version=validated_evidence.retriever_version,
            analysis_source_digest_sha256=(
                validated_analysis.provenance.observation_source_digest_sha256
            ),
            analysis_digest_sha256=canonical_digest(validated_analysis),
            operational_evidence_digest_sha256=canonical_digest(validated_evidence),
            sufficiency=validated_analysis.sufficiency,
            retrieval_status=status,
            statistics=statistics,
            conditions=tuple(
                sorted(
                    validated_analysis.conditions,
                    key=lambda item: item.condition_id,
                )
            ),
            recommendations=tuple(
                sorted(
                    validated_analysis.recommendations,
                    key=lambda item: item.recommendation_id,
                )
            ),
            analysis_evidence=analysis_evidence,
            risks_and_uncertainties=validated_analysis.risks_and_uncertainties,
            retrieval_queries=queries,
            retrieval_hits=hits,
            evidence_excerpts=excerpts,
        )

    @staticmethod
    def _default_id(analysis_id: str) -> str:
        candidate = f"llm-{analysis_id}"
        if len(candidate) <= 63:
            return candidate
        digest = hashlib.sha256(analysis_id.encode()).hexdigest()[:16]
        return f"llm-input-{digest}"

    @staticmethod
    def _validate_pair(
        analysis: AnalysisReport, evidence: OperationalEvidencePackage
    ) -> None:
        if (
            evidence.analysis_id != analysis.analysis_id
            or evidence.observation_id != analysis.observation_id
        ):
            raise LLMInputError("M5 and M8 identities do not match")
        if (
            evidence.analysis_source_digest_sha256
            != analysis.provenance.observation_source_digest_sha256
        ):
            raise LLMInputError("M5 and M8 observation-source digests do not match")
        if evidence.analysis_sufficiency is not analysis.sufficiency:
            raise LLMInputError("M5 and M8 sufficiency does not match")
        if len(evidence.bundles) > MAX_QUERIES:
            raise LLMInputError(f"M8 evidence exceeds the {MAX_QUERIES}-query bound")

        if (
            not analysis.conditions
            and not analysis.recommendations
            and evidence.bundles
        ):
            raise LLMInputError("finding-free analysis cannot contain M8 bundles")

        conditions = {item.condition_id: item for item in analysis.conditions}
        statistics = {item.statistic_id for item in analysis.statistics}
        analysis_evidence = {item.evidence_id for item in analysis.evidence}
        recommendations = {
            item.recommendation_id: item for item in analysis.recommendations
        }
        covered_conditions: set[str] = set()
        recommendation_sources: set[str] = set()
        for bundle in evidence.bundles:
            if not set(bundle.condition_ids).issubset(conditions):
                raise LLMInputError("M8 bundle references an unknown M5 condition")
            if not set(bundle.statistic_ids).issubset(statistics):
                raise LLMInputError("M8 bundle references an unknown M5 statistic")
            if not set(bundle.analysis_evidence_ids).issubset(analysis_evidence):
                raise LLMInputError("M8 bundle references unknown M5 evidence")
            covered_conditions.update(bundle.condition_ids)
            if bundle.query_kind is EvidenceQueryKind.RECOMMENDATION:
                if bundle.source_id not in recommendations:
                    raise LLMInputError(
                        "M8 recommendation bundle has an unknown source"
                    )
                recommendation = recommendations[bundle.source_id]
                if (
                    set(bundle.condition_ids) != set(recommendation.condition_ids)
                    or set(bundle.statistic_ids) != set(recommendation.statistic_ids)
                    or set(bundle.analysis_evidence_ids)
                    != set(recommendation.evidence_ids)
                ):
                    raise LLMInputError(
                        "M8 recommendation bundle does not match its M5 source"
                    )
                recommendation_sources.add(bundle.source_id)
            else:
                linked = tuple(conditions[item] for item in bundle.condition_ids)
                if {item.condition_type for item in linked} != {bundle.source_id}:
                    raise LLMInputError(
                        "M8 condition bundle has an invalid source type"
                    )
                expected_statistics = {
                    reference for item in linked for reference in item.statistic_ids
                }
                expected_evidence = {
                    reference for item in linked for reference in item.evidence_ids
                }
                if (
                    set(bundle.statistic_ids) != expected_statistics
                    or set(bundle.analysis_evidence_ids) != expected_evidence
                ):
                    raise LLMInputError(
                        "M8 condition bundle does not match its M5 sources"
                    )

        if recommendation_sources != set(recommendations):
            raise LLMInputError("M8 evidence does not cover every M5 recommendation")
        if covered_conditions != set(conditions):
            raise LLMInputError("M8 evidence does not cover every M5 condition")

    @staticmethod
    def _bounded_retrieval(
        evidence: OperationalEvidencePackage,
    ) -> tuple[
        tuple[LLMRetrievalQuery, ...],
        tuple[LLMRetrievalHitReference, ...],
        tuple[LLMEvidenceExcerpt, ...],
    ]:
        included: list[tuple[str, int, KnowledgeRetrievalHit]] = []
        queries: list[LLMRetrievalQuery] = []
        for bundle in evidence.bundles:
            hits = bundle.retrieval.hits[:MAX_HITS_PER_QUERY]
            queries.append(
                LLMRetrievalQuery(
                    query_id=bundle.query_id,
                    query_kind=bundle.query_kind,
                    source_id=bundle.source_id,
                    query=bundle.query,
                    condition_ids=bundle.condition_ids,
                    statistic_ids=bundle.statistic_ids,
                    analysis_evidence_ids=bundle.analysis_evidence_ids,
                    retrieved_hit_count=len(bundle.retrieval.hits),
                    included_hit_count=len(hits),
                )
            )
            included.extend(
                (bundle.query_id, rank, hit) for rank, hit in enumerate(hits, start=1)
            )

        selected_ids: set[str] = set()
        chunks: dict[str, KnowledgeChunk] = {}
        for _, _, hit in included:
            chunk_id = hit.chunk.chunk_id
            chunks.setdefault(chunk_id, hit.chunk)
            if len(selected_ids) < MAX_EXCERPTS:
                selected_ids.add(chunk_id)

        hit_references: list[LLMRetrievalHitReference] = []
        query_ids_by_chunk: dict[str, set[str]] = {}
        for query_id, rank, hit in included:
            if hit.semantic_score is None or hit.lexical_match_ratio is None:
                raise LLMInputError("M8 retrieval hit lacks rerank component scores")
            chunk = hit.chunk
            query_ids_by_chunk.setdefault(chunk.chunk_id, set()).add(query_id)
            hit_references.append(
                LLMRetrievalHitReference(
                    query_id=query_id,
                    rank=rank,
                    chunk_id=chunk.chunk_id,
                    point_id=chunk.point_id,
                    score=hit.score,
                    semantic_score=hit.semantic_score,
                    lexical_match_ratio=hit.lexical_match_ratio,
                    selected_as_excerpt=chunk.chunk_id in selected_ids,
                )
            )

        excerpts = []
        for chunk_id in sorted(selected_ids):
            chunk = chunks[chunk_id]
            text = chunk.text
            excerpts.append(
                LLMEvidenceExcerpt(
                    chunk_id=chunk_id,
                    point_id=chunk.point_id,
                    document_id=chunk.document_id,
                    document_type=chunk.document_type,
                    document_title=chunk.document_title,
                    document_version=chunk.document_version,
                    section=chunk.section,
                    excerpt=text[:MAX_EXCERPT_CHARS],
                    excerpt_truncated=len(text) > MAX_EXCERPT_CHARS,
                    content_sha256=chunk.content_sha256,
                    sources=chunk.sources,
                    query_ids=tuple(sorted(query_ids_by_chunk[chunk_id])),
                )
            )
        return (
            tuple(queries),
            tuple(hit_references),
            tuple(excerpts),
        )


class LLMInputStore:
    """Immutable atomic JSON storage with digest validation and inspection."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, package_id: str) -> Path:
        if OBSERVATION_ID_PATTERN.fullmatch(package_id) is None:
            raise LLMInputStoreError("invalid LLM input package ID")
        return self.directory / f"{package_id}.json"

    def save(self, package: LLMInputPackage) -> Path:
        try:
            validated = LLMInputPackage.model_validate(package.model_dump(mode="json"))
        except ValidationError as error:
            raise LLMInputStoreError(f"invalid LLM input package: {error}") from error
        path = self._path(validated.package_id)
        digest = package_digest(validated)
        artifact = LLMInputArtifact(package_sha256=digest, package=validated)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                artifact.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            os.link(temporary, path)
            temporary.unlink()
        except FileExistsError as error:
            self._discard_temporary(temporary)
            raise LLMInputStoreError(
                f"LLM input package already exists: {validated.package_id}"
            ) from error
        except OSError as error:
            self._discard_temporary(temporary)
            raise LLMInputStoreError(str(error)) from error
        return path

    @staticmethod
    def _discard_temporary(path: Path) -> None:
        with suppress(OSError):
            path.unlink(missing_ok=True)

    def _load_artifact(self, package_id: str) -> LLMInputArtifact:
        path = self._path(package_id)
        try:
            return LLMInputArtifact.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise LLMInputStoreError(
                f"LLM input package does not exist: {package_id}"
            ) from error
        except (OSError, ValidationError) as error:
            raise LLMInputStoreError(f"invalid LLM input artifact: {error}") from error

    def load_artifact(self, package_id: str) -> LLMInputArtifact:
        """Load and integrity-check the complete M9 persistence envelope."""

        return self._load_artifact(package_id)

    def load(self, package_id: str) -> LLMInputPackage:
        return self._load_artifact(package_id).package

    def inspect(self, package_id: str) -> LLMInputSummary:
        artifact = self._load_artifact(package_id)
        package = artifact.package
        return LLMInputSummary(
            package_id=package.package_id,
            created_at=package.created_at,
            analysis_id=package.analysis_id,
            observation_id=package.observation_id,
            identity=package.identity,
            sufficiency=package.sufficiency,
            retrieval_status=package.retrieval_status,
            statistic_count=len(package.statistics),
            condition_count=len(package.conditions),
            recommendation_count=len(package.recommendations),
            uncertainty_count=len(package.risks_and_uncertainties),
            query_count=len(package.retrieval_queries),
            hit_reference_count=len(package.retrieval_hits),
            excerpt_count=len(package.evidence_excerpts),
            package_sha256=artifact.package_sha256,
        )
