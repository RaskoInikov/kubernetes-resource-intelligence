import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from kri.contracts import (
    CitationJudgment,
    ExpectedNumericalFact,
    ExpectedRecommendation,
    InferenceFailure,
    InferenceOptions,
    InferenceRunArtifact,
    InferenceStatus,
    LLMQualityCase,
    LLMQualityDataset,
    LLMQualityDatasetEnvelope,
    LLMQualityEvaluationEnvelope,
    QualityOutcome,
    RAGMode,
)
from kri.inference import InferenceRunner, canonical_digest
from kri.quality_evaluation import (
    QualityEvaluationError,
    QualityEvaluationStore,
    QualityEvaluationStoreError,
    QualityEvaluator,
    inference_run_id,
    load_quality_dataset,
    quality_dataset_digest,
    score_candidate,
)
from tests.test_inference import (
    MODEL_DIGEST,
    FakeClient,
    source_artifact,
    valid_candidate,
)

NOW = datetime(2026, 11, 5, tzinfo=UTC)


def quality_case() -> LLMQualityCase:
    source = source_artifact()
    package = source.package
    condition = package.conditions[0]
    recommendation = package.recommendations[0]
    statistic = package.statistics[0]
    chunk = package.evidence_excerpts[0].chunk_id
    return LLMQualityCase(
        case_id="cpu-case",
        package_id=package.package_id,
        package_sha256=source.package_sha256,
        analysis_id=package.analysis_id,
        observation_id=package.observation_id,
        expected_condition_ids=(condition.condition_id,),
        expected_facts=(
            ExpectedNumericalFact(
                statistic_id=statistic.statistic_id,
                value=statistic.value,
                unit=statistic.unit,
            ),
        ),
        expected_uncertainties=package.risks_and_uncertainties,
        expected_recommendations=(
            ExpectedRecommendation(
                recommendation_id=recommendation.recommendation_id,
                resource=recommendation.resource,
                current_value=recommendation.current_value,
                recommended_value=recommendation.recommended_value,
            ),
        ),
        citation_judgments=(
            CitationJudgment(
                target_id=condition.condition_id,
                required_analysis_ids=condition.evidence_ids,
                allowed_knowledge_ids=(chunk,),
                required_knowledge_ids=(chunk,),
            ),
            CitationJudgment(
                target_id=recommendation.recommendation_id,
                required_analysis_ids=recommendation.evidence_ids,
                allowed_knowledge_ids=(chunk,),
                required_knowledge_ids=(chunk,),
            ),
        ),
        exclusions=("No style score.",),
        provenance="Retained deterministic fixture.",
    )


def dataset_envelope() -> LLMQualityDatasetEnvelope:
    dataset = LLMQualityDataset(
        dataset_version="1.0.0",
        created_at=NOW,
        author="author",
        reviewer="reviewer",
        reviewed_at=NOW + timedelta(seconds=1),
        leakage_notes=("No output used.",),
        model_name="qwen3:test",
        model_digest=MODEL_DIGEST,
        prompt_version="1.4",
        options=InferenceOptions(),
        trial_count=2,
        cases=(quality_case(),),
    )
    return LLMQualityDatasetEnvelope(
        dataset_sha256=quality_dataset_digest(dataset), dataset=dataset
    )


def run(mode: RAGMode, repetition: int = 1) -> InferenceRunArtifact:
    source = source_artifact()
    run_id = inference_run_id("quality-eval", "cpu-case", repetition, mode)
    candidate = valid_candidate(source, run_id=run_id, rag_mode=mode)
    result = InferenceRunner(
        FakeClient(candidate.model_dump_json()),
        "http://ollama.test",
        "qwen3:test",
        expected_model_digest=MODEL_DIGEST,
        clock=lambda: NOW,
    ).run(source, run_id, mode, InferenceOptions())
    return result.model_copy(update={"prompt_version": "1.4"})


def all_runs() -> dict[str, InferenceRunArtifact]:
    return {
        item.run_id: item
        for repetition in (1, 2)
        for mode in (RAGMode.OFF, RAGMode.ON)
        for item in (run(mode, repetition),)
    }


def test_fixed_dataset_scores_and_replays_paired_trials(tmp_path: Path) -> None:
    envelope = dataset_envelope()
    runs = all_runs()
    report = QualityEvaluator(clock=lambda: NOW).evaluate(
        "quality-eval",
        envelope,
        {source_artifact().package.package_id: source_artifact()},
        runs,
        evidence_class="offline-recorded",
        environment={"cpu": "test"},
    )

    assert len(report.trials) == 4
    assert all(trial.scores is not None for trial in report.trials)
    assert all(
        trial.scores.supported_fact_rate == 1 for trial in report.trials if trial.scores
    )
    assert all(item.total_pair_count == 2 for item in report.comparisons)
    assert all(
        item.outcome is QualityOutcome.INCONCLUSIVE for item in report.comparisons
    )
    assert report.comparisons[0].paired_difference_stdev == 0

    store = QualityEvaluationStore(tmp_path)
    path = store.save(report)
    assert path.name == "quality-eval.json"
    assert store.load("quality-eval") == report
    with pytest.raises(QualityEvaluationStoreError, match="already exists"):
        store.save(report)


def test_scoring_reports_unsupported_missing_and_citation_errors() -> None:
    accepted = run(RAGMode.ON)
    candidate = accepted.candidate
    assert candidate is not None
    bad_claim = (
        candidate.problems[0].numerical_claims[0].model_copy(update={"value": 999.0})
    )
    bad_problem = candidate.problems[0].model_copy(
        update={"numerical_claims": (bad_claim,), "citations": ()}
    )
    bad = candidate.model_copy(
        update={"problems": (bad_problem,), "recommendations": (), "uncertainties": ()}
    )
    artifact = accepted.model_copy(update={"candidate": bad})

    scores = score_candidate(quality_case(), artifact)

    assert scores is not None
    assert scores.supported_fact_rate == 0
    assert scores.unsupported_claim_rate == 1
    assert scores.citation_precision is None
    assert scores.citation_recall == 0
    assert scores.uncertainty_coverage == 0
    assert scores.recommendation_consistency == 0
    failed = accepted.model_copy(update={"candidate": None})
    assert score_candidate(quality_case(), failed) is None

    unknown_problem = candidate.problems[0].model_copy(
        update={
            "condition_id": "unknown-condition",
            "citations": (
                candidate.problems[0]
                .citations[0]
                .model_copy(update={"source_id": "unknown-evidence"}),
            ),
        }
    )
    unknown_candidate = candidate.model_copy(update={"problems": (unknown_problem,)})
    unknown_scores = score_candidate(
        quality_case(), accepted.model_copy(update={"candidate": unknown_candidate})
    )
    assert unknown_scores is not None
    assert (
        unknown_scores.correct_citation_count < unknown_scores.generated_citation_count
    )


def test_evaluator_keeps_failures_and_classifies_differences() -> None:
    runs = all_runs()
    failed_id = inference_run_id("quality-eval", "cpu-case", 2, RAGMode.ON)
    original = runs[failed_id]
    runs[failed_id] = original.model_copy(
        update={
            "status": InferenceStatus.FAILED,
            "candidate": None,
            "validation": None,
            "accepted_output": None,
            "raw_response": None,
            "raw_response_sha256": None,
            "failure": InferenceFailure(code="timeout", message="timed out"),
            "total_duration_ns": None,
            "ended_at": NOW + timedelta(seconds=5),
        }
    )
    report = QualityEvaluator(clock=lambda: NOW).evaluate(
        "quality-eval",
        dataset_envelope(),
        {source_artifact().package.package_id: source_artifact()},
        runs,
        evidence_class="fresh-real",
        environment={},
    )

    failed_trial = next(item for item in report.trials if item.trial_id == failed_id)
    assert failed_trial.failure_code == "timeout"
    assert failed_trial.latency_seconds == 5
    supported = next(
        item for item in report.comparisons if item.metric == "supported_fact_rate"
    )
    validation = next(
        item for item in report.comparisons if item.metric == "validation_success"
    )
    assert supported.missing_pair_count == 1
    assert validation.outcome is QualityOutcome.REGRESSED

    improved_runs = all_runs()
    off_id = inference_run_id("quality-eval", "cpu-case", 2, RAGMode.OFF)
    off = improved_runs[off_id]
    improved_runs[off_id] = off.model_copy(
        update={
            "status": InferenceStatus.FAILED,
            "candidate": None,
            "validation": None,
            "accepted_output": None,
            "failure": InferenceFailure(code="timeout", message="timed out"),
        }
    )
    improved = QualityEvaluator(clock=lambda: NOW).evaluate(
        "quality-eval",
        dataset_envelope(),
        {source_artifact().package.package_id: source_artifact()},
        improved_runs,
        evidence_class="offline-recorded",
        environment={},
    )
    improved_validation = next(
        item for item in improved.comparisons if item.metric == "validation_success"
    )
    assert improved_validation.outcome is QualityOutcome.IMPROVED


def test_dataset_and_evaluator_reject_integrity_and_plan_mismatches(
    tmp_path: Path,
) -> None:
    envelope = dataset_envelope()
    path = tmp_path / "dataset.json"
    path.write_text(envelope.model_dump_json())
    assert load_quality_dataset(path) == envelope
    path.write_text("bad")
    with pytest.raises(QualityEvaluationError, match="invalid quality dataset"):
        load_quality_dataset(path)

    evaluator = QualityEvaluator(clock=lambda: NOW)
    source = source_artifact()
    packages = {source.package.package_id: source}
    runs = all_runs()
    with pytest.raises(QualityEvaluationError, match="missing planned run"):
        evaluator.evaluate(
            "quality-eval",
            envelope,
            packages,
            {},
            evidence_class="offline-recorded",
            environment={},
        )
    with pytest.raises(QualityEvaluationError, match="source mismatch"):
        evaluator.evaluate(
            "quality-eval",
            envelope,
            {},
            runs,
            evidence_class="offline-recorded",
            environment={},
        )
    changed_case = quality_case().model_copy(
        update={"expected_uncertainties": ("changed",)}
    )
    changed_dataset = envelope.dataset.model_copy(update={"cases": (changed_case,)})
    changed_envelope = LLMQualityDatasetEnvelope(
        dataset_sha256=quality_dataset_digest(changed_dataset), dataset=changed_dataset
    )
    with pytest.raises(QualityEvaluationError, match="fixed labels"):
        evaluator.evaluate(
            "quality-eval",
            changed_envelope,
            packages,
            runs,
            evidence_class="offline-recorded",
            environment={},
        )
    bad_runs = dict(runs)
    key = next(iter(bad_runs))
    bad_runs[key] = bad_runs[key].model_copy(update={"model_name": "qwen3:other"})
    with pytest.raises(QualityEvaluationError, match="configuration mismatch"):
        evaluator.evaluate(
            "quality-eval",
            envelope,
            packages,
            bad_runs,
            evidence_class="offline-recorded",
            environment={},
        )
    with pytest.raises(QualityEvaluationError, match="naive"):
        QualityEvaluator(clock=lambda: datetime(2026, 1, 1)).evaluate(
            "quality-eval",
            envelope,
            packages,
            runs,
            evidence_class="offline-recorded",
            environment={},
        )
    old_dataset = envelope.dataset.model_copy(update={"prompt_version": "1.3"})
    old_envelope = LLMQualityDatasetEnvelope.model_construct(
        dataset_sha256="0" * 64, dataset=old_dataset
    )
    with pytest.raises(QualityEvaluationError, match="prompt version"):
        evaluator.evaluate(
            "quality-eval",
            old_envelope,
            packages,
            runs,
            evidence_class="offline-recorded",
            environment={},
        )


def test_quality_contracts_and_store_detect_invalid_state(tmp_path: Path) -> None:
    case = quality_case()
    with pytest.raises(ValidationError, match="must be allowed"):
        case.citation_judgments[0].model_copy(
            update={"required_knowledge_ids": ("other",)}
        ).model_validate(
            {
                **case.citation_judgments[0].model_dump(),
                "required_knowledge_ids": ("other",),
            }
        )
    with pytest.raises(ValidationError, match="distinct"):
        LLMQualityDataset.model_validate(
            {**dataset_envelope().dataset.model_dump(), "reviewer": "author"}
        )
    invalid_case_payload = case.model_dump()
    for field, message in (
        ("expected_facts", "duplicate facts"),
        ("expected_recommendations", "duplicate recommendations"),
        ("citation_judgments", "duplicate citations"),
    ):
        payload = dict(invalid_case_payload)
        payload[field] = (*payload[field], payload[field][0])
        with pytest.raises(ValidationError, match=message):
            LLMQualityCase.model_validate(payload)
    with pytest.raises(ValidationError, match="quality case IDs"):
        LLMQualityCase.model_validate({**invalid_case_payload, "case_id": "BAD"})
    with pytest.raises(ValidationError, match="cover every"):
        LLMQualityCase.model_validate(
            {
                **invalid_case_payload,
                "citation_judgments": invalid_case_payload["citation_judgments"][:-1],
            }
        )
    dataset_payload = dataset_envelope().dataset.model_dump()
    for update, message in (
        ({"dataset_version": "bad"}, "must be semantic"),
        ({"created_at": datetime(2026, 1, 1)}, "must include a timezone"),
        ({"reviewed_at": NOW - timedelta(seconds=1)}, "cannot precede"),
        (
            {"cases": (*dataset_payload["cases"], dataset_payload["cases"][0])},
            "case IDs",
        ),
    ):
        with pytest.raises(ValidationError, match=message):
            LLMQualityDataset.model_validate({**dataset_payload, **update})
    with pytest.raises(ValidationError, match="digest"):
        LLMQualityDatasetEnvelope(
            dataset_sha256="0" * 64, dataset=dataset_envelope().dataset
        )

    report = QualityEvaluator(clock=lambda: NOW).evaluate(
        "quality-eval",
        dataset_envelope(),
        {source_artifact().package.package_id: source_artifact()},
        all_runs(),
        evidence_class="offline-recorded",
        environment={},
    )
    with pytest.raises(ValidationError, match="digest"):
        LLMQualityEvaluationEnvelope(report_sha256="0" * 64, report=report)
    store = QualityEvaluationStore(tmp_path)
    with pytest.raises(QualityEvaluationStoreError, match="invalid quality evaluation"):
        store.load("missing")
    invalid = report.model_construct(**{**report.__dict__, "evaluation_id": "BAD"})
    with pytest.raises(QualityEvaluationStoreError, match="invalid quality report"):
        store.save(invalid)
    store.save(report)
    payload = json.loads((tmp_path / "quality-eval.json").read_text())
    payload["report"]["model_name"] = "changed"
    (tmp_path / "quality-eval.json").write_text(json.dumps(payload))
    with pytest.raises(QualityEvaluationStoreError, match="invalid quality evaluation"):
        store.load("quality-eval")

    trial_payload = report.trials[0].model_dump()
    with pytest.raises(ValidationError, match="trial timestamps"):
        type(report.trials[0]).model_validate(
            {**trial_payload, "started_at": datetime(2026, 1, 1)}
        )
    report_payload = report.model_dump()
    with pytest.raises(ValidationError, match="evaluation timestamp"):
        type(report).model_validate(
            {**report_payload, "created_at": datetime(2026, 1, 1)}
        )


def test_quality_store_reports_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = QualityEvaluator(clock=lambda: NOW).evaluate(
        "quality-eval",
        dataset_envelope(),
        {source_artifact().package.package_id: source_artifact()},
        all_runs(),
        evidence_class="offline-recorded",
        environment={},
    )
    store = QualityEvaluationStore(tmp_path)
    original_write = Path.write_text

    def fail_write(self: Path, *_args: Any, **_kwargs: Any) -> int:
        if self.parent == tmp_path:
            raise OSError("disk full")
        return original_write(self, *_args, **_kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(QualityEvaluationStoreError, match="disk full"):
        store.save(report)


def test_real_dataset_is_fixed_and_matches_retained_packages() -> None:
    envelope = load_quality_dataset(Path("evaluation/m13-quality-v1.json"))
    assert envelope.dataset.dataset_version == "1.0.0"
    assert envelope.dataset.author != envelope.dataset.reviewer
    assert envelope.dataset.trial_count == 2
    assert len(envelope.dataset.cases) == 2
    assert all(case.expected_condition_ids for case in envelope.dataset.cases)
    assert canonical_digest(envelope.dataset) == envelope.dataset_sha256
