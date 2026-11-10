"""Offline M14 recommendation-effectiveness planning and evaluation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import cast

from pydantic import BaseModel

from kri.analysis import DeterministicAnalyzer
from kri.contracts import (
    AnalysisReport,
    EffectDirection,
    EffectivenessApproval,
    EffectivenessClassification,
    EffectivenessGuardrail,
    EffectivenessIssue,
    EffectivenessMeasurement,
    EffectivenessMetric,
    EffectivenessMetricResult,
    EffectivenessObjective,
    EffectivenessPlan,
    EffectivenessRole,
    EffectivenessTrialReference,
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    ObservationSnapshot,
    RecommendationEffectivenessReport,
    ResourceMutation,
    VerificationStatus,
    WorkloadConfiguration,
)
from kri.observations import ObservationStore, ObservationStoreError


def canonical_digest(value: object) -> str:
    """Return a stable digest for a Pydantic contract or JSON-compatible value."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    """Digest exact retained source bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_effectiveness_plan(
    analysis: AnalysisReport,
    baseline: WorkloadConfiguration,
    *,
    plan_id: str,
    created_by: str,
    context: str,
    image_identity: str,
    load_configuration: LoadConfiguration,
    repetitions: int,
    observation_window_seconds: int,
    objectives: tuple[EffectivenessObjective, ...],
    guardrails: tuple[EffectivenessGuardrail, ...],
    recommendation_id: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EffectivenessPlan:
    """Copy one exact approval-required M5 recommendation into a safe plan."""

    recommendation = next(
        (
            item
            for item in analysis.recommendations
            if item.recommendation_id == recommendation_id
        ),
        None,
    )
    if recommendation is None:
        raise ValueError("source analysis does not contain the recommendation")
    if not recommendation.requires_approval:
        raise ValueError("source recommendation must require approval")
    if getattr(baseline, recommendation.resource) != recommendation.current_value:
        raise ValueError("baseline does not match recommendation current value")
    candidate = baseline.model_copy(
        update={recommendation.resource: recommendation.recommended_value}
    )
    # Revalidate updates because model_copy deliberately skips Pydantic validation.
    candidate = WorkloadConfiguration.model_validate(candidate.model_dump())
    created_at = clock()
    if created_at.tzinfo is None:
        raise ValueError("plan clock returned a naive timestamp")
    return EffectivenessPlan(
        plan_id=plan_id,
        created_at=created_at,
        created_by=created_by,
        source_analysis_id=analysis.analysis_id,
        source_analysis_sha256=canonical_digest(analysis),
        source_observation_sha256=(
            analysis.provenance.observation_source_digest_sha256
        ),
        source_recommendation_id=recommendation.recommendation_id,
        source_evidence_ids=recommendation.evidence_ids,
        context=context,
        cluster=analysis.identity.cluster,
        namespace=analysis.identity.namespace,
        workload=analysis.identity.deployment_name,
        image_identity=image_identity,
        baseline_configuration=baseline,
        candidate_configuration=candidate,
        mutation=ResourceMutation(
            field=recommendation.resource,
            baseline_value=recommendation.current_value,
            candidate_value=recommendation.recommended_value,
        ),
        load_configuration=load_configuration,
        repetitions=repetitions,
        observation_window_seconds=observation_window_seconds,
        stop_conditions=(
            "Stop on failed load Job, application unavailability, or warning events.",
        ),
        rollback_procedure=(
            "Restore the exact baseline configuration after the bounded candidate run."
        ),
        cleanup_procedure=(
            "Delete only plan-owned experiment Jobs after terminal evidence is saved."
        ),
        experiment_artifact_root="results/experiments",
        observation_artifact_root="results/observations",
        objectives=objectives,
        guardrails=guardrails,
    )


def _statistic(
    analysis: AnalysisReport, name: str, aggregation: str
) -> tuple[float | None, tuple[str, ...]]:
    matches = [item for item in analysis.statistics if item.name == name]
    if not matches:
        return None, ()
    values = [item.value for item in matches]
    if aggregation == "sum":
        value = sum(values)
    elif aggregation == "mean":
        value = fmean(values)
    elif aggregation == "first" and len(values) == 1:
        value = values[0]
    else:
        return None, ()
    return value, tuple(
        sorted({evidence for item in matches for evidence in item.evidence_ids})
    )


def _measurement(
    reference: EffectivenessTrialReference,
    experiment: ExperimentRecord,
    observation: ObservationSnapshot,
) -> EffectivenessMeasurement:
    analysis = DeterministicAnalyzer(clock=lambda: observation.created_at).analyze(
        observation, f"m14-{reference.trial_id}"
    )
    throughput, throughput_evidence = _statistic(
        analysis, "http_requests_per_second", "first"
    )
    latency, latency_evidence = _statistic(
        analysis, "http_latency_p95_seconds", "first"
    )
    throttle, throttle_evidence = _statistic(
        analysis, "cpu_throttle_period_ratio", "mean"
    )
    cpu, cpu_evidence = _statistic(analysis, "cpu_average_cores", "sum")
    memory, memory_evidence = _statistic(
        analysis, "memory_p95_working_set_bytes", "sum"
    )
    application_errors, error_evidence = _statistic(
        analysis, "http_error_ratio", "first"
    )
    load_summary = experiment.load_summary
    client_failure_ratio = (
        (load_summary.request_failures + load_summary.request_timeouts)
        / load_summary.requests_started
        if load_summary is not None and load_summary.requests_started > 0
        else None
    )
    errors = (
        max(application_errors, client_failure_ratio)
        if application_errors is not None and client_failure_ratio is not None
        else None
    )
    pods = observation.workload_snapshot.pods
    ready = (
        sum(item.ready is True for item in pods)
        / experiment.workload_configuration.replicas
        if pods and all(item.ready is not None for item in pods)
        else None
    )
    restarts = (
        float(sum(item.restart_count or 0 for item in pods))
        if pods and all(item.restart_count is not None for item in pods)
        else None
    )
    limitations = [item.message for item in observation.quality_report.issues]
    for metric, value in (
        ("throughput", throughput),
        ("p95 latency", latency),
        ("throttling", throttle),
        ("CPU", cpu),
        ("memory", memory),
        ("application error ratio", application_errors),
        ("client failure ratio", client_failure_ratio),
        ("combined error ratio", errors),
        ("readiness", ready),
        ("restarts", restarts),
    ):
        if value is None:
            limitations.append(f"Required {metric} measurement is unavailable.")
    return EffectivenessMeasurement(
        trial_id=reference.trial_id,
        role=reference.role,
        repetition=reference.repetition,
        experiment_id=experiment.experiment_id,
        observation_id=observation.observation_id,
        interval_start=observation.raw_metrics_snapshot.interval_start,
        interval_end=observation.raw_metrics_snapshot.interval_end,
        throughput_rps=throughput,
        p95_latency_seconds=latency,
        throttle_ratio=throttle,
        cpu_average_cores=cpu,
        memory_p95_bytes=memory,
        application_error_ratio=application_errors,
        client_failure_ratio=client_failure_ratio,
        client_request_failures=(
            load_summary.request_failures if load_summary is not None else None
        ),
        client_request_timeouts=(
            load_summary.request_timeouts if load_summary is not None else None
        ),
        error_ratio=errors,
        ready_ratio=ready,
        restarts=restarts,
        target_attainment=(
            throughput / experiment.load_configuration.request_rate
            if throughput is not None
            else None
        ),
        throughput_per_cpu_core=(
            throughput / cpu
            if throughput is not None and cpu is not None and cpu > 0
            else None
        ),
        evidence_ids=tuple(
            sorted(
                {
                    *throughput_evidence,
                    *latency_evidence,
                    *throttle_evidence,
                    *cpu_evidence,
                    *memory_evidence,
                    *error_evidence,
                    *(
                        (f"experiment:{experiment.experiment_id}:load-summary",)
                        if load_summary is not None
                        else ()
                    ),
                }
            )
        ),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _configuration_from_observation(
    observation: ObservationSnapshot,
) -> WorkloadConfiguration | None:
    resources = [
        item
        for item in observation.workload_snapshot.container_resources
        if item.container_name == "application"
    ]
    if len(resources) != 1:
        return None
    item = resources[0]
    if any(
        value is None
        for value in (
            item.cpu_request,
            item.cpu_limit,
            item.memory_request,
            item.memory_limit,
        )
    ):
        return None
    return WorkloadConfiguration(
        cpu_request=item.cpu_request,
        cpu_limit=item.cpu_limit,
        memory_request=item.memory_request,
        memory_limit=item.memory_limit,
        replicas=len(observation.workload_snapshot.pods),
    )


def _resolve_trial(
    plan: EffectivenessPlan, reference: EffectivenessTrialReference
) -> tuple[EffectivenessMeasurement | None, list[EffectivenessIssue]]:
    issues: list[EffectivenessIssue] = []

    def issue(code: str, message: str) -> None:
        issues.append(
            EffectivenessIssue(
                code=code,
                trial_id=reference.trial_id,
                message=message,
                blocking=True,
            )
        )

    experiment_path = Path(reference.experiment_path)
    observation_path = Path(reference.observation_path)
    for path, root, code in (
        (
            experiment_path,
            Path(plan.experiment_artifact_root),
            "experiment_path_outside_root",
        ),
        (
            observation_path,
            Path(plan.observation_artifact_root),
            "observation_path_outside_root",
        ),
    ):
        if not path.resolve().is_relative_to(root.resolve()):
            issue(code, "Artifact path is outside the plan's declared root.")
    if reference.declared_confounders:
        issue(
            "declared_confounder",
            "Declared trial confounders prevent a causal effectiveness conclusion.",
        )
    try:
        if file_digest(experiment_path) != reference.experiment_sha256:
            issue("experiment_digest_mismatch", "Experiment digest does not match.")
        if file_digest(observation_path) != reference.observation_sha256:
            issue("observation_digest_mismatch", "Observation digest does not match.")
        experiment = ExperimentRecord.model_validate_json(
            experiment_path.read_text(encoding="utf-8")
        )
        observation = ObservationStore(observation_path.parent).replay(
            observation_path.stem
        )
    except (OSError, ValueError, ObservationStoreError) as error:
        issue("source_artifact_invalid", str(error))
        return None, issues
    if experiment.experiment_id != reference.experiment_id:
        issue("experiment_identity_mismatch", "Experiment ID does not match reference.")
    if observation.observation_id != reference.observation_id:
        issue(
            "observation_identity_mismatch", "Observation ID does not match reference."
        )
    if experiment.lifecycle_state is not ExperimentState.SUCCEEDED:
        issue(
            "experiment_not_succeeded", "Experiment lacks a succeeded terminal state."
        )
    expected = (
        plan.baseline_configuration
        if reference.role is EffectivenessRole.BASELINE
        else plan.candidate_configuration
    )
    if experiment.workload_configuration != expected:
        issue("experiment_configuration_mismatch", "Experiment configuration differs.")
    if experiment.load_configuration != plan.load_configuration:
        issue("load_configuration_mismatch", "Experiment load controls differ.")
    if _configuration_from_observation(observation) != expected:
        issue("observation_configuration_mismatch", "Observed resources differ.")
    identity = observation.workload_snapshot.identity
    if (identity.cluster, identity.namespace, identity.deployment_name) != (
        plan.cluster,
        plan.namespace,
        plan.workload,
    ):
        issue("workload_identity_mismatch", "Observation workload identity differs.")
    interval = observation.raw_metrics_snapshot
    if (interval.interval_end - interval.interval_start).total_seconds() < (
        plan.observation_window_seconds
    ):
        issue("observation_window_short", "Observation window is shorter than planned.")
    start = experiment.job_start_timestamp or experiment.start_timestamp
    if (
        experiment.end_timestamp is None
        or interval.interval_start < start
        or interval.interval_end > experiment.end_timestamp
    ):
        issue(
            "observation_window_incomparable", "Metrics are outside the load interval."
        )
    measurement = _measurement(reference, experiment, observation)
    if measurement.limitations:
        issue("measurement_incomplete", "Required measurements have limitations.")
    return measurement, issues


def _metric_value(
    measurement: EffectivenessMeasurement, metric: EffectivenessMetric
) -> float | None:
    return cast(float | None, getattr(measurement, metric.value))


def _desirable_relative_change(
    baseline: float, candidate: float, direction: EffectDirection
) -> float | None:
    if baseline == 0:
        return 0.0 if candidate == 0 else None
    raw = (candidate - baseline) / abs(baseline)
    return raw if direction is EffectDirection.HIGHER else -raw


def _target_passes(
    candidate: float, target: float | None, direction: EffectDirection
) -> bool:
    if target is None:
        return True
    if direction is EffectDirection.HIGHER:
        return candidate >= target
    return candidate <= target


def classify_measurements(
    plan: EffectivenessPlan,
    measurements: Sequence[EffectivenessMeasurement],
    issues: Sequence[EffectivenessIssue] = (),
) -> tuple[
    EffectivenessClassification,
    tuple[EffectivenessMetricResult, ...],
    tuple[EffectivenessIssue, ...],
]:
    """Apply policy 1.0 without hiding missing values or trial variation."""

    collected_issues = list(issues)
    counts = Counter(item.role for item in measurements)
    expected = plan.repetitions
    if any(counts[role] != expected for role in EffectivenessRole):
        collected_issues.append(
            EffectivenessIssue(
                code="insufficient_repetitions",
                message="Both roles must contain every planned repetition.",
                blocking=True,
            )
        )
    required_metrics = {item.metric for item in plan.objectives} | {
        item.metric for item in plan.guardrails
    }
    results: list[EffectivenessMetricResult] = []
    for metric in EffectivenessMetric:
        baseline = tuple(
            value
            for item in measurements
            if item.role is EffectivenessRole.BASELINE
            if (value := _metric_value(item, metric)) is not None
        )
        candidate = tuple(
            value
            for item in measurements
            if item.role is EffectivenessRole.CANDIDATE
            if (value := _metric_value(item, metric)) is not None
        )
        complete = len(baseline) == expected and len(candidate) == expected
        baseline_mean = fmean(baseline) if complete else None
        candidate_mean = fmean(candidate) if complete else None
        absolute = (
            candidate_mean - baseline_mean
            if baseline_mean is not None and candidate_mean is not None
            else None
        )
        relative = (
            absolute / abs(baseline_mean)
            if absolute is not None and baseline_mean is not None and baseline_mean != 0
            else None
        )
        objective_passed: bool | None = None
        matching_objectives = [
            item for item in plan.objectives if item.metric is metric
        ]
        if (
            matching_objectives
            and complete
            and baseline_mean is not None
            and candidate_mean is not None
        ):
            objective_passed = all(
                (
                    (
                        change := _desirable_relative_change(
                            baseline_mean, candidate_mean, item.direction
                        )
                    )
                    is not None
                    and change >= item.minimum_relative_improvement
                    and _target_passes(
                        candidate_mean, item.target_value, item.direction
                    )
                )
                for item in matching_objectives
            )
        guardrail_passed: bool | None = None
        matching_guardrails = [
            item for item in plan.guardrails if item.metric is metric
        ]
        if (
            matching_guardrails
            and complete
            and baseline_mean is not None
            and candidate_mean is not None
        ):
            guardrail_passed = all(
                (
                    (
                        change := _desirable_relative_change(
                            baseline_mean, candidate_mean, item.direction
                        )
                    )
                    is not None
                    and change >= -item.maximum_relative_regression
                    and _target_passes(
                        candidate_mean, item.absolute_limit, item.direction
                    )
                )
                for item in matching_guardrails
            )
        if metric in required_metrics and not complete:
            collected_issues.append(
                EffectivenessIssue(
                    code="required_metric_missing",
                    message=f"Required metric {metric.value} is incomplete.",
                    blocking=True,
                )
            )
        results.append(
            EffectivenessMetricResult(
                metric=metric,
                baseline_values=baseline,
                candidate_values=candidate,
                baseline_mean=baseline_mean,
                candidate_mean=candidate_mean,
                baseline_stdev=pstdev(baseline) if complete else None,
                candidate_stdev=pstdev(candidate) if complete else None,
                absolute_difference=absolute,
                relative_difference=relative,
                objective_passed=objective_passed,
                guardrail_passed=guardrail_passed,
            )
        )
    if any(item.blocking for item in collected_issues):
        classification = EffectivenessClassification.INCONCLUSIVE
    elif any(item.guardrail_passed is False for item in results):
        classification = EffectivenessClassification.HARMFUL
    elif all(
        item.objective_passed is True
        for item in results
        if item.metric
        in {objective.metric for objective in plan.objectives if objective.required}
    ):
        classification = EffectivenessClassification.EFFECTIVE
    else:
        classification = EffectivenessClassification.INEFFECTIVE
    return classification, tuple(results), tuple(collected_issues)


def evaluate_effectiveness(
    plan: EffectivenessPlan,
    references: Sequence[EffectivenessTrialReference],
    *,
    report_id: str,
    approval: EffectivenessApproval | None = None,
    rollback_status: VerificationStatus = VerificationStatus.NOT_VERIFIED,
    cleanup_status: VerificationStatus = VerificationStatus.NOT_VERIFIED,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RecommendationEffectivenessReport:
    """Resolve immutable artifacts and produce one read-only M14 report."""

    measurements: list[EffectivenessMeasurement] = []
    issues: list[EffectivenessIssue] = []
    plan_sha256 = canonical_digest(plan)
    if approval is None:
        issues.append(
            EffectivenessIssue(
                code="approval_missing",
                message="No explicit approval record was supplied.",
                blocking=True,
            )
        )
    elif approval.plan_id != plan.plan_id or approval.plan_sha256 != plan_sha256:
        issues.append(
            EffectivenessIssue(
                code="approval_plan_mismatch",
                message="Approval does not bind the evaluated plan digest.",
                blocking=True,
            )
        )
    elif not approval.approved:
        issues.append(
            EffectivenessIssue(
                code="approval_denied",
                message="The plan was not approved for execution.",
                blocking=True,
            )
        )
    identities = [(item.role, item.repetition) for item in references]
    if len(identities) != len(set(identities)):
        issues.append(
            EffectivenessIssue(
                code="duplicate_trial_role_repetition",
                message="Trial role/repetition pairs must be unique.",
                blocking=True,
            )
        )
    source_ids = [(item.experiment_id, item.observation_id) for item in references]
    if len(source_ids) != len(set(source_ids)):
        issues.append(
            EffectivenessIssue(
                code="duplicate_trial_sources",
                message="Repeated trials must reference distinct source artifacts.",
                blocking=True,
            )
        )
    for reference in references:
        measurement, trial_issues = _resolve_trial(plan, reference)
        issues.extend(trial_issues)
        if measurement is not None:
            measurements.append(measurement)
    classification, metric_results, final_issues = classify_measurements(
        plan, measurements, issues
    )
    created_at = clock()
    if created_at.tzinfo is None:
        raise ValueError("report clock returned a naive timestamp")
    return RecommendationEffectivenessReport(
        report_id=report_id,
        created_at=created_at,
        plan_id=plan.plan_id,
        plan_sha256=plan_sha256,
        classification=classification,
        measurements=tuple(measurements),
        metric_results=metric_results,
        issues=final_issues,
        confounders=tuple(
            dict.fromkeys(
                confounder
                for item in references
                for confounder in item.declared_confounders
            )
        ),
        rollback_status=rollback_status,
        cleanup_status=cleanup_status,
    )
