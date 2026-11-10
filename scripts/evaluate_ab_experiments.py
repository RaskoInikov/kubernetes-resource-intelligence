"""Reproduce an A/B evaluation from saved M1 and M4 artifacts."""

# Report prose and generated Markdown table rows are intentionally kept whole.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import fmean

from kri.analysis import DeterministicAnalyzer
from kri.contracts import (
    AnalysisReport,
    EffectivenessApproval,
    EffectivenessPlanEnvelope,
    EffectivenessTrialManifest,
    ExperimentRecord,
    NormalizedMetricSeries,
    ObservationSnapshot,
    RecommendationEffectivenessReportEnvelope,
    VerificationStatus,
)
from kri.effectiveness import canonical_digest, evaluate_effectiveness
from kri.observations import ObservationStore


@dataclass(frozen=True)
class RunEvaluation:
    """Values extracted without changing the retained source artifacts."""

    experiment_path: Path
    observation_path: Path
    experiment: ExperimentRecord
    observation: ObservationSnapshot
    analysis: AnalysisReport
    throughput_rps: float
    latency_p95_seconds: float
    aggregate_cpu_average_cores: float
    maximum_pod_cpu_peak_cores: float
    mean_throttle_period_ratio: float
    aggregate_throttled_seconds_per_second: float
    observed_request_delta: float
    observed_error_delta: float
    request_coverage_seconds: tuple[float, ...]
    ready_pods: int
    total_restarts: int
    interval_warning_events: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_experiment(path: Path) -> ExperimentRecord:
    return ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _load_observation(path: Path) -> ObservationSnapshot:
    return ObservationStore(path.parent).replay(path.stem)


def _statistics(report: AnalysisReport, name: str) -> tuple[float, ...]:
    values = tuple(item.value for item in report.statistics if item.name == name)
    if not values:
        raise ValueError(f"analysis does not contain required statistic {name!r}")
    return values


def _counter_delta(series: NormalizedMetricSeries) -> float:
    if len(series.samples) < 2:
        raise ValueError(f"series {series.signal_name!r} does not contain two samples")
    delta = series.samples[-1].value - series.samples[0].value
    if delta < 0:
        raise ValueError(f"series {series.signal_name!r} contains a counter reset")
    return delta


def _evaluate(experiment_path: Path, observation_path: Path) -> RunEvaluation:
    experiment = _load_experiment(experiment_path)
    observation = _load_observation(observation_path)
    analysis = DeterministicAnalyzer().analyze(observation)
    request_series = tuple(
        series
        for series in observation.normalized_series
        if series.signal_name == "http_requests_total"
        and series.labels.get("route") == "/work"
    )
    if not request_series:
        raise ValueError("observation does not contain /work request counters")
    observed_request_delta = sum(_counter_delta(series) for series in request_series)
    error_delta = sum(
        _counter_delta(series)
        for series in request_series
        if not series.labels.get("status_code", "").startswith(("2", "3"))
    )
    interval = observation.raw_metrics_snapshot
    warning_events = sum(
        event.event_type.lower() == "warning"
        and event.timestamp is not None
        and interval.interval_start <= event.timestamp <= interval.interval_end
        for event in observation.workload_snapshot.events
    )
    return RunEvaluation(
        experiment_path=experiment_path,
        observation_path=observation_path,
        experiment=experiment,
        observation=observation,
        analysis=analysis,
        throughput_rps=_statistics(analysis, "http_requests_per_second")[0],
        latency_p95_seconds=_statistics(analysis, "http_latency_p95_seconds")[0],
        aggregate_cpu_average_cores=sum(_statistics(analysis, "cpu_average_cores")),
        maximum_pod_cpu_peak_cores=max(_statistics(analysis, "cpu_peak_cores")),
        mean_throttle_period_ratio=fmean(
            _statistics(analysis, "cpu_throttle_period_ratio")
        ),
        aggregate_throttled_seconds_per_second=sum(
            _statistics(analysis, "cpu_throttled_seconds_per_second")
        ),
        observed_request_delta=observed_request_delta,
        observed_error_delta=error_delta,
        request_coverage_seconds=tuple(
            (series.samples[-1].timestamp - series.samples[0].timestamp).total_seconds()
            for series in request_series
        ),
        ready_pods=sum(pod.ready is True for pod in observation.workload_snapshot.pods),
        total_restarts=sum(
            pod.restart_count
            for pod in observation.workload_snapshot.pods
            if pod.restart_count is not None
        ),
        interval_warning_events=warning_events,
    )


def _validate_comparability(baseline: RunEvaluation, candidate: RunEvaluation) -> None:
    for run in (baseline, candidate):
        configured = run.experiment.workload_configuration
        resources = tuple(
            item
            for item in run.observation.workload_snapshot.container_resources
            if item.container_name == "application"
        )
        if len(resources) != 1:
            raise ValueError("observation must contain one application container")
        observed = resources[0]
        expected = (
            configured.cpu_request,
            configured.cpu_limit,
            configured.memory_request,
            configured.memory_limit,
        )
        actual = (
            observed.cpu_request,
            observed.cpu_limit,
            observed.memory_request,
            observed.memory_limit,
        )
        if actual != expected:
            raise ValueError("experiment resources do not match its paired observation")
    if (
        baseline.experiment.load_configuration
        != candidate.experiment.load_configuration
    ):
        raise ValueError("A/B load configurations differ")
    first = baseline.observation.workload_snapshot.identity
    second = candidate.observation.workload_snapshot.identity
    identity_fields = ("cluster", "namespace", "deployment_name")
    if any(
        getattr(first, field) != getattr(second, field) for field in identity_fields
    ):
        raise ValueError("A/B observations do not identify the same workload")
    if (
        baseline.experiment.workload_configuration.replicas
        != candidate.experiment.workload_configuration.replicas
    ):
        raise ValueError("A/B replica counts differ")


def _delta(candidate: float, baseline: float) -> float:
    return candidate - baseline


def _relative_delta(candidate: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("relative difference is undefined for a zero baseline")
    return _delta(candidate, baseline) / baseline


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _signed_percent(value: float) -> str:
    return f"{value * 100:+.2f}%"


def _signed(value: float, digits: int = 3) -> str:
    return f"{value:+.{digits}f}"


def _duration_overlap(run: RunEvaluation) -> float:
    metrics = run.observation.raw_metrics_snapshot
    experiment_start = (
        run.experiment.job_start_timestamp or run.experiment.start_timestamp
    )
    nominal_end = experiment_start + timedelta(
        seconds=run.experiment.load_configuration.duration_seconds
    )
    start = max(metrics.interval_start, experiment_start)
    end = min(metrics.interval_end, nominal_end)
    return max(0.0, (end - start).total_seconds())


def _quality_issue(run: RunEvaluation, field: str) -> bool:
    return any(issue.field == field for issue in run.observation.quality_report.issues)


def _render_report(baseline: RunEvaluation, candidate: RunEvaluation) -> str:
    _validate_comparability(baseline, candidate)
    load = baseline.experiment.load_configuration
    a_workload = baseline.experiment.workload_configuration
    b_workload = candidate.experiment.workload_configuration
    a_error_ratio = baseline.observed_error_delta / baseline.observed_request_delta
    b_error_ratio = candidate.observed_error_delta / candidate.observed_request_delta
    missing_error_metric = all(
        _quality_issue(run, "kri_http_request_errors_total")
        for run in (baseline, candidate)
    )
    interval_seconds = (
        baseline.observation.raw_metrics_snapshot.interval_end
        - baseline.observation.raw_metrics_snapshot.interval_start
    ).total_seconds()
    generated_at = max(
        baseline.observation.created_at, candidate.observation.created_at
    )

    lines = [
        "# A/B workload resource experiment evaluation",
        "",
        (
            "This report replays the retained, immutable observations through the "
            "M5 deterministic analyzer. It does not query Kubernetes or Prometheus. "
            f"Artifact cutoff: `{generated_at.isoformat()}`."
        ),
        "",
        "## Reproduce",
        "",
        "```console",
        "python scripts/evaluate_ab_experiments.py \\",
        f"  --baseline-experiment {baseline.experiment_path} \\",
        f"  --baseline-observation {baseline.observation_path} \\",
        f"  --candidate-experiment {candidate.experiment_path} \\",
        f"  --candidate-observation {candidate.observation_path} \\",
        "  --output docs/AB_EXPERIMENT_REPORT.md",
        "```",
        "",
        "Input integrity:",
        "",
        f"- A experiment `{baseline.experiment.experiment_id}`: `{_sha256(baseline.experiment_path)}`",
        f"- A observation `{baseline.observation.observation_id}`: `{_sha256(baseline.observation_path)}`",
        f"- B experiment `{candidate.experiment.experiment_id}`: `{_sha256(candidate.experiment_path)}`",
        f"- B observation `{candidate.observation.observation_id}`: `{_sha256(candidate.observation_path)}`",
        "",
        "## Experiment controls",
        "",
        (
            f"Both records specify `{load.workload_mode}` load, concurrency "
            f"{load.concurrency}, target {load.request_rate:.0f} requests/s, duration "
            f"{load.duration_seconds} seconds, and 2 replicas. B changed CPU request "
            f"from {a_workload.cpu_request} to {b_workload.cpu_request}, CPU limit from "
            f"{a_workload.cpu_limit} to {b_workload.cpu_limit}, and memory request from "
            f"{a_workload.memory_request} to {b_workload.memory_request}; the "
            f"{a_workload.memory_limit} memory limit was unchanged."
        ),
        "",
        (
            "The paired observations have matching recorded resource values, but "
            "different Deployment UIDs: "
            f"`{baseline.observation.workload_snapshot.identity.deployment_uid}` "
            "for A and "
            f"`{candidate.observation.workload_snapshot.identity.deployment_uid}` "
            "for B."
        ),
        "",
        "## Results",
        "",
        "| Measurement | A baseline | B candidate | B - A | Relative change |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| Actual `/work` throughput | {baseline.throughput_rps:.3f} req/s | "
            f"{candidate.throughput_rps:.3f} req/s | "
            f"{_signed(_delta(candidate.throughput_rps, baseline.throughput_rps))} req/s | "
            f"{_signed_percent(_relative_delta(candidate.throughput_rps, baseline.throughput_rps))} |"
        ),
        (
            f"| `/work` histogram p95 | {baseline.latency_p95_seconds * 1000:.3f} ms | "
            f"{candidate.latency_p95_seconds * 1000:.3f} ms | "
            f"{_signed(_delta(candidate.latency_p95_seconds, baseline.latency_p95_seconds) * 1000)} ms | "
            f"{_signed_percent(_relative_delta(candidate.latency_p95_seconds, baseline.latency_p95_seconds))} |"
        ),
        (
            f"| Aggregate average CPU | {baseline.aggregate_cpu_average_cores * 1000:.3f} mCPU | "
            f"{candidate.aggregate_cpu_average_cores * 1000:.3f} mCPU | "
            f"{_signed(_delta(candidate.aggregate_cpu_average_cores, baseline.aggregate_cpu_average_cores) * 1000)} mCPU | "
            f"{_signed_percent(_relative_delta(candidate.aggregate_cpu_average_cores, baseline.aggregate_cpu_average_cores))} |"
        ),
        (
            f"| Highest per-Pod CPU peak | {baseline.maximum_pod_cpu_peak_cores * 1000:.3f} mCPU | "
            f"{candidate.maximum_pod_cpu_peak_cores * 1000:.3f} mCPU | "
            f"{_signed(_delta(candidate.maximum_pod_cpu_peak_cores, baseline.maximum_pod_cpu_peak_cores) * 1000)} mCPU | "
            f"{_signed_percent(_relative_delta(candidate.maximum_pod_cpu_peak_cores, baseline.maximum_pod_cpu_peak_cores))} |"
        ),
        (
            f"| Mean throttled-period ratio | {_percent(baseline.mean_throttle_period_ratio)} | "
            f"{_percent(candidate.mean_throttle_period_ratio)} | "
            f"{_signed((candidate.mean_throttle_period_ratio - baseline.mean_throttle_period_ratio) * 100)} pp | "
            f"{_signed_percent(_relative_delta(candidate.mean_throttle_period_ratio, baseline.mean_throttle_period_ratio))} |"
        ),
        (
            f"| Aggregate throttled CPU seconds/s | {baseline.aggregate_throttled_seconds_per_second:.3f} | "
            f"{candidate.aggregate_throttled_seconds_per_second:.3f} | "
            f"{_signed(_delta(candidate.aggregate_throttled_seconds_per_second, baseline.aggregate_throttled_seconds_per_second))} | "
            f"{_signed_percent(_relative_delta(candidate.aggregate_throttled_seconds_per_second, baseline.aggregate_throttled_seconds_per_second))} |"
        ),
        (
            f"| Response-code-derived error rate | {_percent(a_error_ratio)} | "
            f"{_percent(b_error_ratio)} | {_signed((b_error_ratio - a_error_ratio) * 100)} pp | n/a (zero baseline) |"
        ),
        "",
        (
            f"Throughput attainment improved from {_percent(baseline.throughput_rps / load.request_rate)} "
            f"to {_percent(candidate.throughput_rps / load.request_rate)} of the configured target "
            f"({_signed((candidate.throughput_rps - baseline.throughput_rps) / load.request_rate * 100)} percentage points), "
            "but B still did not sustain the 20 req/s target. The extra CPU was consumed: "
            f"average aggregate CPU rose {_percent(_relative_delta(candidate.aggregate_cpu_average_cores, baseline.aggregate_cpu_average_cores))}. "
            "Despite that, throttling frequency was effectively unchanged and remained extreme."
        ),
        "",
        "## Workload stability",
        "",
        "| Indicator | A baseline | B candidate |",
        "| --- | ---: | ---: |",
        f"| Ready Pods at collection | {baseline.ready_pods}/2 | {candidate.ready_pods}/2 |",
        f"| Container restarts at collection | {baseline.total_restarts} | {candidate.total_restarts} |",
        f"| Warning events timestamped inside metrics interval | {baseline.interval_warning_events} | {candidate.interval_warning_events} |",
        f"| Observed `/work` request delta | {baseline.observed_request_delta:.0f} | {candidate.observed_request_delta:.0f} |",
        f"| Observed non-2xx/3xx request delta | {baseline.observed_error_delta:.0f} | {candidate.observed_error_delta:.0f} |",
        f"| Observation quality | `{baseline.observation.quality_report.status}` | `{candidate.observation.quality_report.status}` |",
        "",
        (
            "Both snapshots show 2/2 ready Pods, zero restarts, no warning event "
            "timestamped inside the metric window, no counter-reset quality finding, and "
            "only HTTP 200 `/work` request series. This supports short-window server-side "
            "stability. It does not prove load-generator completion or client-side success."
        ),
        "",
        "## Calculation notes",
        "",
        '- Throughput is the sum of per-Pod `(last counter - first counter) / elapsed sample time` for `http_requests_total{route="/work"}`.',
        "- p95 is M5's interpolation over the aggregate delta of cumulative `/work` histogram buckets; it is an estimate bounded by the exported buckets.",
        "- Aggregate average CPU is the sum of M5 per-Pod average rates from `container_cpu_usage_seconds_total`. Pod peaks are not summed because their timestamps need not align.",
        "- Throttle frequency is the arithmetic mean of per-Pod throttled-period ratios. Throttled CPU seconds/s is summed across the two Pods.",
        "- The response-code error rate uses non-2xx/3xx deltas divided by all observed `/work` request deltas. It is shown separately from the missing contractual error counter.",
        "",
        "## Data-quality limitations",
        "",
        (
            f"- Both observations are `degraded`: `kri_http_request_errors_total` returned no series. "
            f"All observed request-status series are HTTP 200, giving a response-code-derived 0% rate, "
            f"but the required error signal is not independently verified. Missing data is not treated as zero: "
            "dedicated-counter error rate remains unavailable "
            f"(confirmed missing in both snapshots: {str(missing_error_metric).lower()})."
        ),
        (
            f"- Each metrics query spans {interval_seconds:.0f} seconds, but `/work` counter coverage is "
            f"{min(baseline.request_coverage_seconds):.0f}-{max(baseline.request_coverage_seconds):.0f} seconds for A "
            f"and {min(candidate.request_coverage_seconds):.0f}-{max(candidate.request_coverage_seconds):.0f} seconds for B. "
            f"The experiment/metrics-window overlaps are {_duration_overlap(baseline):.3f} seconds and "
            f"{_duration_overlap(candidate):.3f} seconds respectively; A starts observing before load starts and omits the nominal final segment."
        ),
        (
            "- Both experiment records still say `running` and have no end timestamp, even though their configured "
            "durations elapsed before observation creation. Therefore completion, duration adherence, stop behavior, "
            "and load-generator client failures cannot be verified from these records."
        ),
        "- Pod readiness and restart counts are point-in-time Kubernetes observations, not continuous availability measurements. Event absence is limited by event collection and retention.",
        "- B changes CPU request, CPU limit, and memory request together. The experiment cannot isolate which change caused the throughput/latency result. Resource requests affect scheduling, while the CPU limit directly changes available CPU.",
        "- The records do not capture the application/load image digest or node conditions, so unchanged binaries and an otherwise identical environment cannot be proven.",
        "- Observations do not carry an experiment ID. Pairing is based on matching resource values and overlapping timestamps, not an explicit artifact foreign key; the different Deployment UIDs confirm separate deployments.",
        "- This is one sequential A/B pair with no repeated or randomized trials. The numerical difference is real for these saved windows but has no confidence interval and should not be generalized as a causal effect size.",
        "",
        "## Conclusion",
        "",
        (
            "For the retained observations, B is directionally better: `/work` throughput is "
            f"{_signed_percent(_relative_delta(candidate.throughput_rps, baseline.throughput_rps))} and p95 latency is "
            f"{_signed_percent(_relative_delta(candidate.latency_p95_seconds, baseline.latency_p95_seconds))}, with ready Pods, zero restarts, "
            "and no observed non-success response codes in both snapshots. The gain costs "
            f"{_signed_percent(_relative_delta(candidate.aggregate_cpu_average_cores, baseline.aggregate_cpu_average_cores))} more average CPU. "
            f"Mean throttled-period ratio changes only {_signed((candidate.mean_throttle_period_ratio - baseline.mean_throttle_period_ratio) * 100)} percentage points "
            f"and remains {_percent(candidate.mean_throttle_period_ratio)}, while throughput reaches only "
            f"{_percent(candidate.throughput_rps / load.request_rate)} of target."
        ),
        "",
        (
            "The evidence supports retaining B as the better of these two tested configurations, but not declaring "
            "the resource problem solved. A synchronized post-change experiment with terminal lifecycle records, "
            "the dedicated error series, load-generator summary, immutable image digests, and repeated trials is "
            "needed before treating the effect as validated or adopting a further CPU increase."
        ),
        "",
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-experiment", type=Path)
    parser.add_argument("--baseline-observation", type=Path)
    parser.add_argument("--candidate-experiment", type=Path)
    parser.add_argument("--candidate-observation", type=Path)
    parser.add_argument("--m14-plan", type=Path)
    parser.add_argument("--m14-approval", type=Path)
    parser.add_argument("--m14-trials", type=Path)
    parser.add_argument("--report-id")
    parser.add_argument(
        "--rollback-status",
        choices=tuple(VerificationStatus),
        default=VerificationStatus.NOT_VERIFIED,
    )
    parser.add_argument(
        "--cleanup-status",
        choices=tuple(VerificationStatus),
        default=VerificationStatus.NOT_VERIFIED,
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _run_m14(args: argparse.Namespace) -> None:
    if (
        args.m14_plan is None
        or args.m14_approval is None
        or args.m14_trials is None
        or args.report_id is None
    ):
        raise ValueError(
            "M14 mode requires --m14-plan, --m14-approval, --m14-trials, "
            "and --report-id"
        )
    plan_envelope = EffectivenessPlanEnvelope.model_validate_json(
        args.m14_plan.read_text(encoding="utf-8")
    )
    manifest = EffectivenessTrialManifest.model_validate_json(
        args.m14_trials.read_text(encoding="utf-8")
    )
    approval = EffectivenessApproval.model_validate_json(
        args.m14_approval.read_text(encoding="utf-8")
    )
    if (
        manifest.plan_id != plan_envelope.plan.plan_id
        or manifest.plan_sha256 != plan_envelope.plan_sha256
    ):
        raise ValueError("trial manifest does not match the effectiveness plan")
    report = evaluate_effectiveness(
        plan_envelope.plan,
        manifest.trials,
        report_id=args.report_id,
        approval=approval,
        rollback_status=VerificationStatus(args.rollback_status),
        cleanup_status=VerificationStatus(args.cleanup_status),
    )
    envelope = RecommendationEffectivenessReportEnvelope(
        report_sha256=canonical_digest(report), report=report
    )
    if args.output.exists():
        raise ValueError(f"refusing to overwrite M14 report: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(envelope.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)


def main() -> int:
    args = _parser().parse_args()
    if args.m14_plan is not None:
        _run_m14(args)
        print(f"wrote {args.output}")
        return 0
    legacy_paths = (
        args.baseline_experiment,
        args.baseline_observation,
        args.candidate_experiment,
        args.candidate_observation,
    )
    if any(path is None for path in legacy_paths):
        raise ValueError("legacy mode requires all baseline and candidate paths")
    assert args.baseline_experiment is not None
    assert args.baseline_observation is not None
    assert args.candidate_experiment is not None
    assert args.candidate_observation is not None
    baseline = _evaluate(args.baseline_experiment, args.baseline_observation)
    candidate = _evaluate(args.candidate_experiment, args.candidate_observation)
    report = _render_report(baseline, candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
