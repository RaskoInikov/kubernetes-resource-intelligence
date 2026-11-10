"""Offline M14 recommendation-effectiveness planning and policy tests."""

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from kri.contracts import (
    EffectDirection,
    EffectivenessApproval,
    EffectivenessClassification,
    EffectivenessGuardrail,
    EffectivenessIssue,
    EffectivenessMeasurement,
    EffectivenessMetric,
    EffectivenessObjective,
    EffectivenessPlan,
    EffectivenessPlanEnvelope,
    EffectivenessRole,
    EffectivenessTrialManifest,
    EffectivenessTrialReference,
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    LoadExecutionSummary,
    RecommendationEffectivenessReportEnvelope,
    ResourceMutation,
    TerminationSource,
    VerificationStatus,
    WorkloadConfiguration,
    WorkloadMode,
)
from kri.effectiveness import (
    _configuration_from_observation,
    _measurement,
    _statistic,
    _target_passes,
    build_effectiveness_plan,
    canonical_digest,
    classify_measurements,
    evaluate_effectiveness,
    file_digest,
)
from kri.observations import ObservationStore
from scripts.evaluate_ab_experiments import _run_m14
from tests.test_analysis import START, analyzer, complete_series, observation

NOW = datetime(2026, 11, 6, tzinfo=UTC)
DIGEST = "1" * 64


def configuration(cpu_limit: str) -> WorkloadConfiguration:
    return WorkloadConfiguration(
        cpu_request="100m",
        cpu_limit=cpu_limit,
        memory_request="64Mi",
        memory_limit="128Mi",
        replicas=1,
    )


def plan() -> EffectivenessPlan:
    return EffectivenessPlan(
        plan_id="m14-test-plan",
        created_at=NOW,
        created_by="test-author",
        source_analysis_id="analysis-source",
        source_analysis_sha256=DIGEST,
        source_observation_sha256="2" * 64,
        source_recommendation_id="increase-cpu-limit",
        source_evidence_ids=("evidence-source",),
        context="kind-test",
        cluster="kind-test",
        namespace="payments",
        workload="kri-workload",
        image_identity="example@sha256:" + DIGEST,
        baseline_configuration=configuration("200m"),
        candidate_configuration=configuration("250m"),
        mutation=ResourceMutation(
            field="cpu_limit", baseline_value="200m", candidate_value="250m"
        ),
        load_configuration=LoadConfiguration(
            workload_mode=WorkloadMode.CPU,
            concurrency=2,
            request_rate=10,
            duration_seconds=30,
        ),
        repetitions=2,
        observation_window_seconds=20,
        stop_conditions=("Stop on workload instability.",),
        rollback_procedure="Restore baseline resources.",
        cleanup_procedure="Delete only plan-owned Jobs.",
        experiment_artifact_root="results/experiments",
        observation_artifact_root="results/observations",
        objectives=(
            EffectivenessObjective(
                objective_id="throughput-improvement",
                metric=EffectivenessMetric.THROUGHPUT_RPS,
                direction=EffectDirection.HIGHER,
                minimum_relative_improvement=0.1,
                target_value=11,
            ),
            EffectivenessObjective(
                objective_id="cpu-efficiency-improvement",
                metric=EffectivenessMetric.THROUGHPUT_PER_CPU_CORE,
                direction=EffectDirection.HIGHER,
                minimum_relative_improvement=0.05,
            ),
        ),
        guardrails=(
            EffectivenessGuardrail(
                guardrail_id="latency-regression",
                metric=EffectivenessMetric.P95_LATENCY_SECONDS,
                direction=EffectDirection.LOWER,
                maximum_relative_regression=0.1,
                absolute_limit=1.1,
            ),
            EffectivenessGuardrail(
                guardrail_id="error-regression",
                metric=EffectivenessMetric.ERROR_RATIO,
                direction=EffectDirection.LOWER,
                maximum_relative_regression=0.1,
                absolute_limit=0.02,
            ),
            EffectivenessGuardrail(
                guardrail_id="readiness",
                metric=EffectivenessMetric.READY_RATIO,
                direction=EffectDirection.HIGHER,
                maximum_relative_regression=0,
                absolute_limit=1,
            ),
            EffectivenessGuardrail(
                guardrail_id="restarts",
                metric=EffectivenessMetric.RESTARTS,
                direction=EffectDirection.LOWER,
                maximum_relative_regression=0,
                absolute_limit=0,
            ),
        ),
    )


def approval_for(
    value: EffectivenessPlan, *, approved: bool = True
) -> EffectivenessApproval:
    return EffectivenessApproval(
        plan_id=value.plan_id,
        plan_sha256=canonical_digest(value),
        approved=approved,
        decided_at=NOW,
        decided_by="operator",
        scope="Bounded disposable experiment only.",
    )


def measurement(
    role: EffectivenessRole,
    repetition: int,
    *,
    throughput: float,
    latency: float,
    error: float | None = 0.01,
    ready: float = 1,
    restarts: float = 0,
) -> EffectivenessMeasurement:
    return EffectivenessMeasurement(
        trial_id=f"{role.value}-{repetition}",
        role=role,
        repetition=repetition,
        experiment_id=f"experiment-{role.value}-{repetition}",
        observation_id=f"observation-{role.value}-{repetition}",
        interval_start=NOW,
        interval_end=NOW + timedelta(seconds=20),
        throughput_rps=throughput,
        p95_latency_seconds=latency,
        throttle_ratio=0.2,
        cpu_average_cores=0.2,
        memory_p95_bytes=100,
        error_ratio=error,
        ready_ratio=ready,
        restarts=restarts,
        target_attainment=throughput / 10,
        throughput_per_cpu_core=throughput / 0.2,
        evidence_ids=(f"evidence-{role.value}-{repetition}",),
        limitations=(),
    )


def paired(
    candidate_throughput: float, candidate_latency: float = 0.9
) -> tuple[EffectivenessMeasurement, ...]:
    return (
        measurement(EffectivenessRole.BASELINE, 1, throughput=10, latency=1),
        measurement(
            EffectivenessRole.CANDIDATE,
            1,
            throughput=candidate_throughput,
            latency=candidate_latency,
        ),
        measurement(EffectivenessRole.BASELINE, 2, throughput=10.2, latency=1.02),
        measurement(
            EffectivenessRole.CANDIDATE,
            2,
            throughput=candidate_throughput + 0.2,
            latency=candidate_latency + 0.02,
        ),
    )


def test_policy_classifies_effective_and_preserves_variation() -> None:
    outcome, results, issues = classify_measurements(plan(), paired(12))
    assert outcome is EffectivenessClassification.EFFECTIVE
    assert issues == ()
    throughput = next(
        item for item in results if item.metric is EffectivenessMetric.THROUGHPUT_RPS
    )
    assert throughput.baseline_mean == pytest.approx(10.1)
    assert throughput.candidate_mean == pytest.approx(12.1)
    assert throughput.baseline_stdev == pytest.approx(0.1)
    assert throughput.relative_difference == pytest.approx(2 / 10.1)
    assert throughput.objective_passed is True


def test_policy_classifies_ineffective_harmful_and_inconclusive() -> None:
    ineffective, _, _ = classify_measurements(plan(), paired(10.5))
    assert ineffective is EffectivenessClassification.INEFFECTIVE

    harmful, results, _ = classify_measurements(plan(), paired(12, 1.2))
    assert harmful is EffectivenessClassification.HARMFUL
    latency = next(
        item
        for item in results
        if item.metric is EffectivenessMetric.P95_LATENCY_SECONDS
    )
    assert latency.guardrail_passed is False

    values = list(paired(12))
    values[-1] = values[-1].model_copy(update={"error_ratio": None})
    inconclusive, _, issues = classify_measurements(plan(), values)
    assert inconclusive is EffectivenessClassification.INCONCLUSIVE
    assert {item.code for item in issues} == {"required_metric_missing"}

    forced, _, _ = classify_measurements(
        plan(),
        paired(12),
        (
            EffectivenessIssue(
                code="confounder", message="Node changed.", blocking=True
            ),
        ),
    )
    assert forced is EffectivenessClassification.INCONCLUSIVE


def test_policy_rejects_missing_repetitions_and_zero_baseline() -> None:
    values = paired(12)[:2]
    outcome, _, issues = classify_measurements(plan(), values)
    assert outcome is EffectivenessClassification.INCONCLUSIVE
    assert "insufficient_repetitions" in {item.code for item in issues}

    zero_values = tuple(
        item.model_copy(update={"restarts": 0.0}) for item in paired(12)
    )
    outcome, results, _ = classify_measurements(plan(), zero_values)
    assert outcome is EffectivenessClassification.EFFECTIVE
    restarts = next(
        item for item in results if item.metric is EffectivenessMetric.RESTARTS
    )
    assert restarts.relative_difference is None
    assert restarts.guardrail_passed is True


def test_plan_allows_only_the_exact_m5_recommendation() -> None:
    report = analyzer().analyze(observation(), "analysis-source")
    built = build_effectiveness_plan(
        report,
        configuration("200m"),
        plan_id="m14-built",
        created_by="tester",
        context="kind-test",
        image_identity="example@sha256:" + DIGEST,
        load_configuration=plan().load_configuration,
        repetitions=2,
        observation_window_seconds=10,
        objectives=plan().objectives,
        guardrails=plan().guardrails,
        recommendation_id="increase-cpu-limit",
        clock=lambda: NOW,
    )
    assert built.mutation.candidate_value == "250m"
    assert built.source_analysis_sha256 == canonical_digest(report)

    with pytest.raises(ValueError, match="does not contain"):
        build_effectiveness_plan(
            report,
            configuration("200m"),
            plan_id="bad",
            created_by="tester",
            context="kind-test",
            image_identity="image",
            load_configuration=plan().load_configuration,
            repetitions=2,
            observation_window_seconds=10,
            objectives=plan().objectives,
            guardrails=plan().guardrails,
            recommendation_id="missing",
        )
    with pytest.raises(ValidationError, match="only the declared"):
        EffectivenessPlan.model_validate(
            plan().model_dump()
            | {
                "candidate_configuration": configuration("250m").model_copy(
                    update={"memory_request": "96Mi"}
                )
            }
        )


def test_read_only_evaluator_retains_integrity_failures(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment.json"
    observation_path = tmp_path / "observation.json"
    experiment.write_text("{}")
    observation_path.write_text("{}")
    reference = EffectivenessTrialReference(
        trial_id="baseline-one",
        role=EffectivenessRole.BASELINE,
        repetition=1,
        experiment_id="experiment-one",
        experiment_path=str(experiment),
        experiment_sha256=file_digest(experiment),
        observation_id="observation-one",
        observation_path=str(observation_path),
        observation_sha256=file_digest(observation_path),
        declared_confounders=("Image identity is not recorded by M1.",),
    )
    report = evaluate_effectiveness(
        plan(),
        (reference, reference),
        report_id="report-invalid",
        rollback_status=VerificationStatus.VERIFIED,
        clock=lambda: NOW,
    )
    assert report.classification is EffectivenessClassification.INCONCLUSIVE
    assert report.automatic_kubernetes_changes is False
    assert report.rollback_status is VerificationStatus.VERIFIED
    assert report.cleanup_status is VerificationStatus.NOT_VERIFIED
    assert report.confounders == ("Image identity is not recorded by M1.",)
    codes = {item.code for item in report.issues}
    assert "duplicate_trial_role_repetition" in codes
    assert "duplicate_trial_sources" in codes
    assert "source_artifact_invalid" in codes
    assert "insufficient_repetitions" in codes
    assert "experiment_path_outside_root" in codes
    assert "observation_path_outside_root" in codes
    assert "declared_confounder" in codes


def test_existing_ab_script_writes_digest_bound_m14_report(tmp_path: Path) -> None:
    plan_value = plan()
    plan_envelope = EffectivenessPlanEnvelope(
        plan_sha256=canonical_digest(plan_value), plan=plan_value
    )
    experiment = tmp_path / "experiment.json"
    observation_path = tmp_path / "observation.json"
    experiment.write_text("{}")
    observation_path.write_text("{}")
    reference = EffectivenessTrialReference(
        trial_id="baseline-one",
        role=EffectivenessRole.BASELINE,
        repetition=1,
        experiment_id="experiment-one",
        experiment_path=str(experiment),
        experiment_sha256=file_digest(experiment),
        observation_id="observation-one",
        observation_path=str(observation_path),
        observation_sha256=file_digest(observation_path),
    )
    manifest = EffectivenessTrialManifest(
        plan_id=plan_value.plan_id,
        plan_sha256=plan_envelope.plan_sha256,
        trials=(reference,),
    )
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "approval.json"
    manifest_path = tmp_path / "trials.json"
    output = tmp_path / "report.json"
    plan_path.write_text(plan_envelope.model_dump_json())
    approval_path.write_text(approval_for(plan_value).model_dump_json())
    manifest_path.write_text(manifest.model_dump_json())
    args = argparse.Namespace(
        m14_plan=plan_path,
        m14_approval=approval_path,
        m14_trials=manifest_path,
        report_id="m14-report",
        rollback_status=VerificationStatus.NOT_VERIFIED,
        cleanup_status=VerificationStatus.NOT_VERIFIED,
        output=output,
    )
    _run_m14(args)
    envelope = RecommendationEffectivenessReportEnvelope.model_validate_json(
        output.read_text()
    )
    assert envelope.report.classification is EffectivenessClassification.INCONCLUSIVE
    with pytest.raises(ValueError, match="overwrite"):
        _run_m14(args)

    mismatched = manifest.model_copy(update={"plan_id": "other"})
    manifest_path.write_text(mismatched.model_dump_json())
    output.unlink()
    with pytest.raises(ValueError, match="does not match"):
        _run_m14(args)


def _saved_reference(
    tmp_path: Path, role: EffectivenessRole, repetition: int
) -> EffectivenessTrialReference:
    plan_value = plan()
    config = (
        plan_value.baseline_configuration
        if role is EffectivenessRole.BASELINE
        else plan_value.candidate_configuration
    )
    resources = (
        observation()
        .workload_snapshot.container_resources[0]
        .model_copy(update={"cpu_limit": config.cpu_limit})
    )
    snapshot = observation(
        resources=(resources,), observation_id=f"obs-{role.value}-{repetition}"
    )
    observation_path = ObservationStore(tmp_path).save(snapshot)
    experiment = ExperimentRecord(
        experiment_id=f"exp-{role.value}-{repetition}",
        workload_configuration=config,
        load_configuration=plan_value.load_configuration,
        start_timestamp=START,
        job_uid=f"job-{role.value}-{repetition}",
        job_start_timestamp=START,
        end_timestamp=START + timedelta(seconds=30),
        lifecycle_state=ExperimentState.SUCCEEDED,
        termination_reason="CompletionsReached",
        termination_source=TerminationSource.KUBERNETES,
        load_summary=LoadExecutionSummary(
            execution_status="completed",
            exit_code=0,
            requests_started=100,
            requests_completed=100,
            requests_succeeded=100,
            request_failures=0,
            request_timeouts=0,
            stuck_workers=0,
        ),
    )
    experiment_path = tmp_path / f"{experiment.experiment_id}.json"
    experiment_path.write_text(experiment.model_dump_json())
    return EffectivenessTrialReference(
        trial_id=f"{role.value}-{repetition}",
        role=role,
        repetition=repetition,
        experiment_id=experiment.experiment_id,
        experiment_path=str(experiment_path),
        experiment_sha256=file_digest(experiment_path),
        observation_id=snapshot.observation_id,
        observation_path=str(observation_path),
        observation_sha256=file_digest(observation_path),
    )


def test_artifact_evaluator_extracts_all_metrics_without_mutation(
    tmp_path: Path,
) -> None:
    references = tuple(
        _saved_reference(tmp_path, role, repetition)
        for role in EffectivenessRole
        for repetition in (1, 2)
    )
    evaluated_plan = plan().model_copy(
        update={
            "observation_window_seconds": 10,
            "experiment_artifact_root": str(tmp_path),
            "observation_artifact_root": str(tmp_path),
        }
    )
    report = evaluate_effectiveness(
        evaluated_plan,
        references,
        report_id="report-complete",
        approval=approval_for(evaluated_plan),
        clock=lambda: NOW,
    )
    assert report.classification is EffectivenessClassification.HARMFUL
    assert report.issues == ()
    assert len(report.measurements) == 4
    first = report.measurements[0]
    assert first.throughput_rps == pytest.approx(10)
    assert first.p95_latency_seconds == pytest.approx(0.5)
    assert first.throttle_ratio == pytest.approx(0.2)
    assert first.cpu_average_cores == pytest.approx(0.2)
    assert first.memory_p95_bytes is not None
    assert first.application_error_ratio == pytest.approx(0.1)
    assert first.client_failure_ratio == 0
    assert first.client_request_failures == 0
    assert first.client_request_timeouts == 0
    assert first.error_ratio == pytest.approx(0.1)
    assert first.ready_ratio == 1
    assert first.restarts == 0
    assert first.target_attainment == 1
    assert first.throughput_per_cpu_core == 50


def test_m14_error_guardrail_keeps_client_failures_and_timeouts(
    tmp_path: Path,
) -> None:
    reference = _saved_reference(tmp_path, EffectivenessRole.BASELINE, 1)
    experiment = ExperimentRecord.model_validate_json(
        Path(reference.experiment_path).read_text()
    ).model_copy(
        update={
            "load_summary": LoadExecutionSummary(
                execution_status="completed",
                exit_code=0,
                requests_started=100,
                requests_completed=100,
                requests_succeeded=80,
                request_failures=5,
                request_timeouts=15,
                stuck_workers=0,
            )
        }
    )

    measurement = _measurement(reference, experiment, observation())

    assert measurement.application_error_ratio == pytest.approx(0.1)
    assert measurement.client_failure_ratio == pytest.approx(0.2)
    assert measurement.error_ratio == pytest.approx(0.2)
    assert measurement.client_request_failures == 5
    assert measurement.client_request_timeouts == 15
    assert f"experiment:{experiment.experiment_id}:load-summary" in (
        measurement.evidence_ids
    )


def test_m14_missing_client_evidence_is_not_replaced_with_zero(
    tmp_path: Path,
) -> None:
    reference = _saved_reference(tmp_path, EffectivenessRole.BASELINE, 1)
    experiment = ExperimentRecord.model_validate_json(
        Path(reference.experiment_path).read_text()
    ).model_copy(update={"schema_version": "1.1", "load_summary": None})

    measurement = _measurement(reference, experiment, observation())

    assert measurement.application_error_ratio == pytest.approx(0.1)
    assert measurement.client_failure_ratio is None
    assert measurement.error_ratio is None
    assert any("client failure ratio" in item for item in measurement.limitations)
    experiment_path = Path(reference.experiment_path)
    experiment_path.write_text(experiment.model_dump_json())
    updated = reference.model_copy(
        update={"experiment_sha256": file_digest(experiment_path)}
    )
    evaluated_plan = plan().model_copy(
        update={
            "observation_window_seconds": 10,
            "experiment_artifact_root": str(tmp_path),
            "observation_artifact_root": str(tmp_path),
        }
    )
    report = evaluate_effectiveness(
        evaluated_plan,
        (updated,),
        report_id="missing-client-evidence",
        approval=approval_for(evaluated_plan),
        clock=lambda: NOW,
    )
    assert "measurement_incomplete" in {item.code for item in report.issues}


def test_metric_helpers_preserve_missing_and_invalid_aggregation() -> None:
    analysis = analyzer().analyze(observation(), "analysis-source")
    assert _statistic(analysis, "missing", "sum") == (None, ())
    assert _statistic(analysis, "cpu_average_cores", "unknown") == (None, ())
    empty_resources = observation().model_copy(
        update={
            "workload_snapshot": observation().workload_snapshot.model_copy(
                update={"container_resources": ()}
            )
        }
    )
    assert _configuration_from_observation(empty_resources) is None
    missing_value = (
        observation()
        .workload_snapshot.container_resources[0]
        .model_copy(update={"cpu_limit": None})
    )
    missing_configuration = observation().model_copy(
        update={
            "workload_snapshot": observation().workload_snapshot.model_copy(
                update={"container_resources": (missing_value,)}
            )
        }
    )
    assert _configuration_from_observation(missing_configuration) is None
    assert canonical_digest({"stable": True}) == canonical_digest({"stable": True})
    assert _target_passes(1, None, EffectDirection.HIGHER) is True


def test_plan_builder_rejects_unapproved_mismatch_and_naive_clock() -> None:
    report = analyzer().analyze(observation(), "analysis-source")
    recommendation = report.recommendations[0]
    unapproved = recommendation.model_copy(update={"requires_approval": False})
    altered = report.model_copy(update={"recommendations": (unapproved,)})
    with pytest.raises(ValueError, match="require approval"):
        build_effectiveness_plan(
            altered,
            configuration("200m"),
            plan_id="m14-built",
            created_by="tester",
            context="kind-test",
            image_identity="image",
            load_configuration=plan().load_configuration,
            repetitions=2,
            observation_window_seconds=10,
            objectives=plan().objectives,
            guardrails=plan().guardrails,
            recommendation_id=unapproved.recommendation_id,
            clock=lambda: NOW,
        )
    with pytest.raises(ValueError, match="current value"):
        build_effectiveness_plan(
            report,
            configuration("250m"),
            plan_id="m14-built",
            created_by="tester",
            context="kind-test",
            image_identity="image",
            load_configuration=plan().load_configuration,
            repetitions=2,
            observation_window_seconds=10,
            objectives=plan().objectives,
            guardrails=plan().guardrails,
            recommendation_id="increase-cpu-limit",
            clock=lambda: NOW,
        )
    with pytest.raises(ValueError, match="naive"):
        build_effectiveness_plan(
            report,
            configuration("200m"),
            plan_id="m14-built",
            created_by="tester",
            context="kind-test",
            image_identity="image",
            load_configuration=plan().load_configuration,
            repetitions=2,
            observation_window_seconds=10,
            objectives=plan().objectives,
            guardrails=plan().guardrails,
            recommendation_id="increase-cpu-limit",
            clock=lambda: datetime(2026, 11, 6),
        )


def test_artifact_evaluator_reports_every_comparability_failure(tmp_path: Path) -> None:
    reference = _saved_reference(tmp_path, EffectivenessRole.BASELINE, 1)
    experiment_path = Path(reference.experiment_path)
    experiment = ExperimentRecord.model_validate_json(experiment_path.read_text())
    running = experiment.model_copy(
        update={
            "lifecycle_state": ExperimentState.RUNNING,
            "end_timestamp": None,
            "termination_reason": None,
            "termination_source": None,
            "load_summary": None,
        }
    )
    experiment_path.write_text(running.model_dump_json())
    bad_reference = reference.model_copy(
        update={
            "experiment_id": "wrong-experiment",
            "observation_id": "wrong-observation",
            "experiment_sha256": "0" * 64,
            "observation_sha256": "0" * 64,
        }
    )
    bad_plan = plan().model_copy(
        update={
            "cluster": "other-cluster",
            "baseline_configuration": configuration("250m"),
            "load_configuration": plan().load_configuration.model_copy(
                update={"request_rate": 20}
            ),
            "observation_window_seconds": 20,
        }
    )
    report = evaluate_effectiveness(
        bad_plan, (bad_reference,), report_id="bad-report", clock=lambda: NOW
    )
    assert {
        "experiment_digest_mismatch",
        "observation_digest_mismatch",
        "experiment_identity_mismatch",
        "observation_identity_mismatch",
        "experiment_not_succeeded",
        "experiment_configuration_mismatch",
        "load_configuration_mismatch",
        "observation_configuration_mismatch",
        "workload_identity_mismatch",
        "observation_window_short",
        "observation_window_incomparable",
    }.issubset({item.code for item in report.issues})


def test_incomplete_measurement_is_preserved_and_blocks(tmp_path: Path) -> None:
    reference = _saved_reference(tmp_path, EffectivenessRole.BASELINE, 1)
    experiment = ExperimentRecord.model_validate_json(
        Path(reference.experiment_path).read_text()
    )
    without_errors = tuple(
        item
        for item in complete_series()
        if item.metric_name != "kri_http_request_errors_total"
    )
    incomplete = observation(
        metric_series=without_errors, observation_id="obs-incomplete"
    )
    direct = _measurement(reference, experiment, incomplete)
    assert direct.error_ratio is None
    assert any("error ratio" in item for item in direct.limitations)

    path = ObservationStore(tmp_path).save(incomplete)
    incomplete_reference = reference.model_copy(
        update={
            "observation_id": incomplete.observation_id,
            "observation_path": str(path),
            "observation_sha256": file_digest(path),
        }
    )
    report = evaluate_effectiveness(
        plan().model_copy(update={"observation_window_seconds": 10}),
        (incomplete_reference,),
        report_id="incomplete-report",
        clock=lambda: NOW,
    )
    assert "measurement_incomplete" in {item.code for item in report.issues}


def test_report_rejects_naive_clock(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="naive"):
        evaluate_effectiveness(
            plan(),
            (),
            report_id="naive-report",
            clock=lambda: datetime(2026, 11, 6),
        )


def test_artifact_evaluation_requires_exact_positive_approval() -> None:
    value = plan()
    missing = evaluate_effectiveness(
        value, (), report_id="missing-approval", clock=lambda: NOW
    )
    assert "approval_missing" in {item.code for item in missing.issues}
    denied = evaluate_effectiveness(
        value,
        (),
        report_id="denied-approval",
        approval=approval_for(value, approved=False),
        clock=lambda: NOW,
    )
    assert "approval_denied" in {item.code for item in denied.issues}
    mismatch = evaluate_effectiveness(
        value,
        (),
        report_id="mismatched-approval",
        approval=approval_for(value).model_copy(update={"plan_id": "other-plan"}),
        clock=lambda: NOW,
    )
    assert "approval_plan_mismatch" in {item.code for item in mismatch.issues}


def test_effectiveness_contracts_reject_inconsistent_integrity() -> None:
    with pytest.raises(ValidationError, match="must change"):
        ResourceMutation(
            field="cpu_limit", baseline_value="200m", candidate_value="200m"
        )

    base = plan()
    payload = base.model_dump()
    with pytest.raises(ValidationError, match="timestamp"):
        EffectivenessPlan.model_validate(
            payload | {"created_at": datetime(2026, 11, 6)}
        )
    wrong_mutation = base.mutation.model_copy(update={"candidate_value": "300m"})
    with pytest.raises(ValidationError, match="mutation values"):
        EffectivenessPlan.model_validate(payload | {"mutation": wrong_mutation})
    candidate_replicas = base.candidate_configuration.model_copy(update={"replicas": 2})
    with pytest.raises(ValidationError, match="replica"):
        EffectivenessPlan.model_validate(
            payload | {"candidate_configuration": candidate_replicas}
        )
    with pytest.raises(ValidationError, match="objective IDs"):
        EffectivenessPlan.model_validate(
            payload | {"objectives": (base.objectives[0], base.objectives[0])}
        )
    with pytest.raises(ValidationError, match="efficiency objective"):
        EffectivenessPlan.model_validate(
            payload | {"objectives": (base.objectives[0],)}
        )
    with pytest.raises(ValidationError, match="performance objective"):
        EffectivenessPlan.model_validate(
            payload | {"objectives": (base.objectives[1],)}
        )
    with pytest.raises(ValidationError, match="guardrail IDs"):
        EffectivenessPlan.model_validate(
            payload | {"guardrails": (base.guardrails[0], base.guardrails[0])}
        )

    approval = EffectivenessApproval(
        plan_id=base.plan_id,
        plan_sha256=canonical_digest(base),
        approved=False,
        decided_at=NOW,
        decided_by="operator",
        scope="No experiment approved.",
    )
    assert approval.decided_at == NOW
    with pytest.raises(ValidationError, match="timestamp"):
        EffectivenessApproval.model_validate(
            approval.model_dump() | {"decided_at": datetime(2026, 11, 6)}
        )
    with pytest.raises(ValidationError, match="plan digest"):
        EffectivenessPlanEnvelope(plan_sha256="0" * 64, plan=base)

    report = evaluate_effectiveness(
        base, (), report_id="contract-report", clock=lambda: NOW
    )
    report_payload = report.model_dump()
    with pytest.raises(ValidationError, match="timestamp"):
        type(report).model_validate(
            report_payload | {"created_at": datetime(2026, 11, 6)}
        )
    with pytest.raises(ValidationError, match="blocking issues"):
        type(report).model_validate(
            report_payload | {"classification": EffectivenessClassification.EFFECTIVE}
        )
    with pytest.raises(ValidationError, match="report digest"):
        RecommendationEffectivenessReportEnvelope(report_sha256="0" * 64, report=report)
