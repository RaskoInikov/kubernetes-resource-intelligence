"""M13 fixed-dataset paired RAG-on/off quality evaluation."""

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, stdev
from uuid import uuid4

from pydantic import ValidationError

from kri.contracts import (
    CitationSource,
    InferenceRunArtifact,
    LLMInputArtifact,
    LLMQualityCase,
    LLMQualityDataset,
    LLMQualityDatasetEnvelope,
    LLMQualityEvaluationEnvelope,
    LLMQualityEvaluationReport,
    LLMQualityTrial,
    QualityMetricComparison,
    QualityOutcome,
    QualityScores,
    RAGMode,
)
from kri.inference import canonical_digest

EVALUATOR_VERSION = "1.0"
SUPPORTED_PROMPT_VERSIONS = {"1.4"}
_METRICS: tuple[tuple[str, bool], ...] = (
    ("validation_success", True),
    ("supported_fact_rate", True),
    ("unsupported_claim_rate", False),
    ("citation_precision", True),
    ("citation_recall", True),
    ("finding_coverage", True),
    ("uncertainty_coverage", True),
    ("recommendation_consistency", True),
    ("latency_seconds", False),
)


class QualityEvaluationError(RuntimeError):
    """M13 inputs cannot produce a trustworthy paired report."""


class QualityEvaluationStoreError(RuntimeError):
    """An immutable M13 report could not be stored or loaded."""


def load_quality_dataset(path: Path) -> LLMQualityDatasetEnvelope:
    """Load and integrity-check one reviewed M13 dataset."""

    try:
        return LLMQualityDatasetEnvelope.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise QualityEvaluationError(f"invalid quality dataset: {error}") from error


def inference_run_id(
    evaluation_id: str, case_id: str, repetition: int, rag_mode: RAGMode
) -> str:
    """Return the deterministic immutable run ID for one planned trial."""

    return f"{evaluation_id}-{case_id}-r{repetition}-{rag_mode.value}"


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_candidate(
    case: LLMQualityCase, artifact: InferenceRunArtifact
) -> QualityScores | None:
    """Score one parseable candidate against fixed labels, without repair."""

    candidate = artifact.candidate
    if candidate is None:
        return None
    expected_facts = {
        item.statistic_id: (item.value, item.unit) for item in case.expected_facts
    }
    matched_facts: set[str] = set()
    unsupported_claims = 0
    generated_claims = 0
    for problem in candidate.problems:
        for claim in problem.numerical_claims:
            generated_claims += 1
            expected = expected_facts.get(claim.statistic_id)
            if (
                expected == (claim.value, claim.unit)
                and claim.statistic_id not in matched_facts
            ):
                matched_facts.add(claim.statistic_id)
            else:
                unsupported_claims += 1

    judgments = {item.target_id: item for item in case.citation_judgments}
    generated_citations = 0
    correct_citations = 0
    required: set[tuple[str, CitationSource, str]] = set()
    recalled: set[tuple[str, CitationSource, str]] = set()
    outputs = [(item.condition_id, item.citations) for item in candidate.problems] + [
        (item.recommendation_id, item.citations) for item in candidate.recommendations
    ]
    for target_id, citations in outputs:
        judgment = judgments.get(target_id)
        allowed: set[tuple[CitationSource, str]] = set()
        if judgment is not None:
            allowed.update(
                (CitationSource.ANALYSIS_EVIDENCE, value)
                for value in judgment.required_analysis_ids
            )
            if artifact.rag_mode is RAGMode.ON:
                allowed.update(
                    (CitationSource.KNOWLEDGE_CHUNK, value)
                    for value in judgment.allowed_knowledge_ids
                )
                required.update(
                    (target_id, CitationSource.KNOWLEDGE_CHUNK, value)
                    for value in judgment.required_knowledge_ids
                )
            required.update(
                (target_id, CitationSource.ANALYSIS_EVIDENCE, value)
                for value in judgment.required_analysis_ids
            )
        for citation in citations:
            generated_citations += 1
            key = (citation.source, citation.source_id)
            if key in allowed:
                correct_citations += 1
            full_key = (target_id, citation.source, citation.source_id)
            if full_key in required:
                recalled.add(full_key)

    condition_ids = {item.condition_id for item in candidate.problems}
    expected_condition_ids = set(case.expected_condition_ids)
    expected_uncertainties = {
        (f"uncertainty-{index}", text)
        for index, text in enumerate(case.expected_uncertainties, start=1)
    }
    actual_uncertainties = {
        (item.uncertainty_id, item.source_text) for item in candidate.uncertainties
    }
    expected_recommendations = {
        item.recommendation_id: (
            item.resource,
            item.current_value,
            item.recommended_value,
        )
        for item in case.expected_recommendations
    }
    consistent_recommendations = sum(
        expected_recommendations.get(item.recommendation_id)
        == (item.resource, item.current_value, item.recommended_value)
        for item in candidate.recommendations
    )
    validation_success = bool(
        artifact.validation is not None and artifact.validation.passed
    )
    return QualityScores(
        validation_success=validation_success,
        supported_fact_count=len(matched_facts),
        expected_fact_count=len(expected_facts),
        unsupported_claim_count=unsupported_claims,
        generated_claim_count=generated_claims,
        supported_fact_rate=_ratio(len(matched_facts), len(expected_facts)),
        unsupported_claim_rate=_ratio(unsupported_claims, generated_claims),
        correct_citation_count=correct_citations,
        generated_citation_count=generated_citations,
        required_citation_count=len(required),
        recalled_citation_count=len(recalled),
        citation_precision=_ratio(correct_citations, generated_citations),
        citation_recall=_ratio(len(recalled), len(required)),
        finding_coverage=len(condition_ids & expected_condition_ids)
        / len(expected_condition_ids),
        uncertainty_coverage=len(actual_uncertainties & expected_uncertainties)
        / len(expected_uncertainties),
        recommendation_consistency=_ratio(
            consistent_recommendations, len(expected_recommendations)
        ),
    )


def _trial_metric(trial: LLMQualityTrial, metric: str) -> float | None:
    if metric == "latency_seconds":
        return trial.latency_seconds
    if metric == "validation_success":
        return float(trial.scores is not None and trial.scores.validation_success)
    if trial.scores is None:
        return None
    value = getattr(trial.scores, metric)
    return float(value) if value is not None else None


def _compare_metric(
    trials: Sequence[LLMQualityTrial], metric: str, higher_is_better: bool
) -> QualityMetricComparison:
    pairs: dict[str, dict[RAGMode, LLMQualityTrial]] = {}
    for trial in trials:
        pairs.setdefault(trial.pair_id, {})[trial.rag_mode] = trial
    off_values: list[float] = []
    on_values: list[float] = []
    differences: list[float] = []
    for pair in pairs.values():
        off = _trial_metric(pair[RAGMode.OFF], metric)
        on = _trial_metric(pair[RAGMode.ON], metric)
        if off is None or on is None:
            continue
        off_values.append(off)
        on_values.append(on)
        differences.append(on - off)
    mean_difference = fmean(differences) if differences else None
    if mean_difference is None or mean_difference == 0:
        outcome = QualityOutcome.INCONCLUSIVE
    elif (mean_difference > 0) == higher_is_better:
        outcome = QualityOutcome.IMPROVED
    else:
        outcome = QualityOutcome.REGRESSED
    return QualityMetricComparison(
        metric=metric,
        higher_is_better=higher_is_better,
        total_pair_count=len(pairs),
        comparable_pair_count=len(differences),
        missing_pair_count=len(pairs) - len(differences),
        rag_off_mean=fmean(off_values) if off_values else None,
        rag_on_mean=fmean(on_values) if on_values else None,
        mean_paired_difference=mean_difference,
        paired_difference_stdev=stdev(differences) if len(differences) > 1 else None,
        outcome=outcome,
    )


class QualityEvaluator:
    """Verify a fixed trial plan and produce deterministic paired metrics."""

    def __init__(
        self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.clock = clock

    def evaluate(
        self,
        evaluation_id: str,
        dataset_envelope: LLMQualityDatasetEnvelope,
        packages: Mapping[str, LLMInputArtifact],
        runs: Mapping[str, InferenceRunArtifact],
        *,
        evidence_class: str,
        environment: Mapping[str, str],
    ) -> LLMQualityEvaluationReport:
        dataset = dataset_envelope.dataset
        if dataset.prompt_version not in SUPPORTED_PROMPT_VERSIONS:
            raise QualityEvaluationError("dataset prompt version is not implemented")
        trials: list[LLMQualityTrial] = []
        for case in dataset.cases:
            source = packages.get(case.package_id)
            if source is None or (
                source.package_sha256 != case.package_sha256
                or source.package.analysis_id != case.analysis_id
                or source.package.observation_id != case.observation_id
            ):
                raise QualityEvaluationError(f"case source mismatch: {case.case_id}")
            self._verify_labels(case, source)
            for repetition in range(1, dataset.trial_count + 1):
                pair_id = f"{evaluation_id}-{case.case_id}-r{repetition}"
                for rag_mode in (RAGMode.OFF, RAGMode.ON):
                    run_id = inference_run_id(
                        evaluation_id, case.case_id, repetition, rag_mode
                    )
                    run = runs.get(run_id)
                    if run is None:
                        raise QualityEvaluationError(f"missing planned run: {run_id}")
                    self._verify_run(dataset, source, run, rag_mode)
                    artifact_sha256 = canonical_digest(run)
                    trials.append(
                        LLMQualityTrial(
                            trial_id=run_id,
                            pair_id=pair_id,
                            case_id=case.case_id,
                            repetition=repetition,
                            rag_mode=rag_mode,
                            input_package_sha256=source.package_sha256,
                            inference_run_id=run.run_id,
                            inference_artifact_sha256=artifact_sha256,
                            status=run.status,
                            started_at=run.started_at,
                            ended_at=run.ended_at,
                            latency_seconds=(
                                run.total_duration_ns / 1_000_000_000
                                if run.total_duration_ns is not None
                                else (run.ended_at - run.started_at).total_seconds()
                            ),
                            failure_code=run.failure.code if run.failure else None,
                            validation_issue_codes=(
                                tuple(item.code for item in run.validation.issues)
                                if run.validation is not None
                                else ()
                            ),
                            scores=score_candidate(case, run),
                        )
                    )
        created_at = self.clock()
        if created_at.tzinfo is None:
            raise QualityEvaluationError("evaluation clock returned a naive timestamp")
        return LLMQualityEvaluationReport(
            evaluation_id=evaluation_id,
            created_at=created_at,
            evidence_class=evidence_class,
            dataset_version=dataset.dataset_version,
            dataset_sha256=dataset_envelope.dataset_sha256,
            model_name=dataset.model_name,
            model_digest=dataset.model_digest,
            prompt_version=dataset.prompt_version,
            options=dataset.options,
            environment=dict(sorted(environment.items())),
            trials=tuple(trials),
            comparisons=tuple(
                _compare_metric(trials, metric, higher_is_better)
                for metric, higher_is_better in _METRICS
            ),
        )

    @staticmethod
    def _verify_labels(case: LLMQualityCase, source: LLMInputArtifact) -> None:
        package = source.package
        facts = {
            item.statistic_id: (item.value, item.unit) for item in case.expected_facts
        }
        source_facts = {
            item.statistic_id: (item.value, item.unit) for item in package.statistics
        }
        recommendations = {
            item.recommendation_id: (
                item.resource,
                item.current_value,
                item.recommended_value,
            )
            for item in case.expected_recommendations
        }
        source_recommendations = {
            item.recommendation_id: (
                item.resource,
                item.current_value,
                item.recommended_value,
            )
            for item in package.recommendations
        }
        source_analysis = {
            item.condition_id: set(item.evidence_ids) for item in package.conditions
        } | {
            item.recommendation_id: set(item.evidence_ids)
            for item in package.recommendations
        }
        source_chunks = {item.chunk_id for item in package.evidence_excerpts}
        if (
            set(case.expected_condition_ids)
            != {item.condition_id for item in package.conditions}
            or facts != source_facts
            or case.expected_uncertainties != package.risks_and_uncertainties
            or recommendations != source_recommendations
            or any(
                set(item.required_analysis_ids) != source_analysis[item.target_id]
                or not set(item.allowed_knowledge_ids).issubset(source_chunks)
                for item in case.citation_judgments
            )
        ):
            raise QualityEvaluationError(
                f"fixed labels do not match M9 source: {case.case_id}"
            )

    @staticmethod
    def _verify_run(
        dataset: LLMQualityDataset,
        source: LLMInputArtifact,
        run: InferenceRunArtifact,
        rag_mode: RAGMode,
    ) -> None:
        # Attribute access is deliberately centralized so every pair is checked
        # before any score is produced.
        if (
            run.package_id != source.package.package_id
            or run.package_sha256 != source.package_sha256
            or run.rag_mode is not rag_mode
            or run.model_name != dataset.model_name
            or run.model_digest != dataset.model_digest
            or run.options != dataset.options
            or run.prompt_version != dataset.prompt_version
        ):
            raise QualityEvaluationError(f"run configuration mismatch: {run.run_id}")


class QualityEvaluationStore:
    """Immutable atomic persistence for M13 reports."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, evaluation_id: str) -> Path:
        return self.directory / f"{evaluation_id}.json"

    def save(self, report: LLMQualityEvaluationReport) -> Path:
        try:
            validated = LLMQualityEvaluationReport.model_validate(
                report.model_dump(mode="json")
            )
        except ValidationError as error:
            raise QualityEvaluationStoreError(
                f"invalid quality report: {error}"
            ) from error
        envelope = LLMQualityEvaluationEnvelope(
            report_sha256=canonical_digest(validated), report=validated
        )
        path = self._path(validated.evaluation_id)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                envelope.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            os.link(temporary, path)
            temporary.unlink()
        except FileExistsError as error:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise QualityEvaluationStoreError(
                f"quality evaluation already exists: {validated.evaluation_id}"
            ) from error
        except OSError as error:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise QualityEvaluationStoreError(str(error)) from error
        return path

    def load(self, evaluation_id: str) -> LLMQualityEvaluationReport:
        try:
            envelope = LLMQualityEvaluationEnvelope.model_validate_json(
                self._path(evaluation_id).read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            raise QualityEvaluationStoreError(
                f"invalid quality evaluation: {error}"
            ) from error
        return envelope.report


def quality_dataset_digest(dataset: LLMQualityDataset) -> str:
    """Canonical digest helper used when authoring a reviewed dataset."""

    encoded = json.dumps(
        dataset.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
