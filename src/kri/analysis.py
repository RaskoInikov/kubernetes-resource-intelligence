"""Deterministic M5 statistics, conditions, evidence, and recommendations."""

import math
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from itertools import pairwise
from statistics import fmean
from uuid import uuid4

from kri.contracts import (
    AnalysisEvidence,
    AnalysisProvenance,
    AnalysisReport,
    AnalysisSufficiency,
    CalculatedStatistic,
    ConditionSeverity,
    ContainerResources,
    DetectedCondition,
    NormalizedMetricSeries,
    ObservationSnapshot,
    QualityStatus,
    ResourceRecommendation,
)
from kri.observations import (
    ObservationBuilder,
    ObservationError,
    ObservationStore,
    ObservationStoreError,
)

ANALYZER_VERSION = "1.1"
POLICY_VERSION = "1.1"
CPU_THROTTLE_THRESHOLD = 0.20
CPU_LIMIT_THRESHOLD = 0.90
MEMORY_LIMIT_THRESHOLD = 0.90
REQUEST_UTILIZATION_THRESHOLD = 1.20
CPU_THROTTLE_CRITICAL_THRESHOLD = 0.50
LIMIT_CRITICAL_THRESHOLD = 1.0
REQUEST_UTILIZATION_CRITICAL_THRESHOLD = 1.50
RECOMMENDATION_MULTIPLIER = 1.25
MAX_INCREASE_MULTIPLIER = 2.0
MIB = 1024 * 1024
_CPU_PATTERN = re.compile(r"^(?P<value>(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))(?P<unit>m?)$")
_MEMORY_PATTERN = re.compile(r"^(?P<value>[1-9][0-9]*)(?P<unit>Ki|Mi|Gi)$")
_MEMORY_FACTORS = {"Ki": 1024, "Mi": MIB, "Gi": 1024**3}
_RESOURCE_SIGNALS = {
    "cpu_usage_seconds_total",
    "cpu_cfs_periods_total",
    "cpu_cfs_throttled_periods_total",
    "cpu_cfs_throttled_seconds_total",
    "memory_working_set_bytes",
}


class AnalysisError(RuntimeError):
    """An observation cannot be safely analyzed."""


def _cpu_millicores(value: str) -> float:
    match = _CPU_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid CPU quantity: {value}")
    amount = float(match.group("value"))
    millicores = amount if match.group("unit") == "m" else amount * 1000
    if millicores <= 0:
        raise ValueError(f"invalid CPU quantity: {value}")
    return millicores


def _memory_bytes(value: str) -> int:
    match = _MEMORY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid memory quantity: {value}")
    return int(match.group("value")) * _MEMORY_FACTORS[match.group("unit")]


def _percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires values")
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _counter_summary(
    series: NormalizedMetricSeries,
) -> tuple[float, float, float, bool] | None:
    """Return delta, average rate, cadence-aware peak rate, and coalescing flag."""

    if len(series.samples) < 2:
        return None
    rates: list[float] = []
    changed_samples = [series.samples[0]]
    for previous, current in zip(series.samples, series.samples[1:], strict=False):
        delta = current.value - previous.value
        elapsed = (current.timestamp - previous.timestamp).total_seconds()
        if delta < 0 or elapsed <= 0:
            return None
        rates.append(delta / elapsed)
        if delta > 0:
            changed_samples.append(current)
    total_delta = series.samples[-1].value - series.samples[0].value
    total_seconds = (
        series.samples[-1].timestamp - series.samples[0].timestamp
    ).total_seconds()
    average_rate = total_delta / total_seconds
    coalesced_updates = len(changed_samples) < len(series.samples)
    if coalesced_updates and len(changed_samples) >= 3:
        effective_rates = [
            (current.value - previous.value)
            / (current.timestamp - previous.timestamp).total_seconds()
            for previous, current in pairwise(changed_samples[1:])
        ]
        peak_rate = max(effective_rates)
    elif coalesced_updates:
        peak_rate = average_rate
    else:
        peak_rate = max(rates)
    return total_delta, average_rate, peak_rate, coalesced_updates


def _scope(series: NormalizedMetricSeries) -> tuple[str, str]:
    return series.labels.get("pod", "unknown"), series.labels.get(
        "container", "application"
    )


def _scope_labels(pod: str, container: str) -> dict[str, str]:
    return {"pod": pod, "container": container}


def _format_cpu_millicores(value: int) -> str:
    return f"{value}m"


def _format_memory(value: int) -> str:
    return f"{value // MIB}Mi"


class DeterministicAnalyzer:
    """Analyze a replay-valid M4 observation using policy version 1.0."""

    def __init__(
        self,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.clock = clock

    def analyze_saved(
        self,
        store: ObservationStore,
        observation_id: str,
        analysis_id: str | None = None,
    ) -> AnalysisReport:
        try:
            observation = store.replay(observation_id)
        except ObservationStoreError as error:
            raise AnalysisError(str(error)) from error
        return self.analyze(observation, analysis_id)

    def analyze(
        self,
        observation: ObservationSnapshot,
        analysis_id: str | None = None,
    ) -> AnalysisReport:
        try:
            ObservationBuilder().replay(observation)
        except ObservationError as error:
            raise AnalysisError(str(error)) from error
        created_at = self.clock()
        if created_at.tzinfo is None:
            raise AnalysisError("analyzer clock returned a naive timestamp")

        evidence = self._series_evidence(observation)
        evidence_by_series = {
            self._series_key(series): evidence[index].evidence_id
            for index, series in enumerate(observation.normalized_series)
        }
        quality_evidence, risks = self._quality_evidence(observation)
        risks.append(
            "Analysis is limited to the recorded interval "
            f"{observation.raw_metrics_snapshot.interval_start.isoformat()} through "
            f"{observation.raw_metrics_snapshot.interval_end.isoformat()}; results "
            "may not generalize beyond this workload window."
        )
        evidence.extend(quality_evidence)
        resources = self._application_resources(observation)
        resource_evidence = self._resource_evidence(resources)
        evidence.extend(resource_evidence)

        statistics, unavailable = self._statistics(
            observation,
            evidence_by_series,
            resources,
            resource_evidence,
        )
        risks.extend(unavailable)
        sufficiency = self._sufficiency(observation, statistics)
        conditions = (
            self._conditions(statistics)
            if sufficiency is not AnalysisSufficiency.INSUFFICIENT
            else []
        )
        for condition in conditions:
            if condition.observed_value < condition.threshold * 1.05:
                risks.append(
                    f"Condition {condition.condition_id} is within 5% of its "
                    f"decision threshold ({condition.observed_value:.6g} versus "
                    f"{condition.threshold:.6g}); its classification is sensitive "
                    "to normal measurement variation."
                )
        recommendations = (
            self._recommendations(
                conditions,
                statistics,
                resources,
                resource_evidence,
                risks,
            )
            if sufficiency is not AnalysisSufficiency.INSUFFICIENT
            else []
        )
        if recommendations:
            risks.append(
                "Recommendations have not been applied or validated by a bounded "
                "post-change experiment; approval and remeasurement are required."
            )
        if sufficiency is AnalysisSufficiency.INSUFFICIENT:
            risks.append(
                "Observation evidence is insufficient; conditions and recommendations "
                "were suppressed."
            )

        return AnalysisReport(
            analysis_id=analysis_id or f"analysis-{uuid4().hex[:12]}",
            observation_id=observation.observation_id,
            created_at=created_at,
            identity=observation.workload_snapshot.identity,
            sufficiency=sufficiency,
            provenance=AnalysisProvenance(
                analyzer_version=ANALYZER_VERSION,
                policy_version=POLICY_VERSION,
                observation_source_digest_sha256=(
                    observation.provenance.source_digest_sha256
                ),
            ),
            statistics=tuple(sorted(statistics, key=lambda item: item.statistic_id)),
            conditions=tuple(sorted(conditions, key=lambda item: item.condition_id)),
            recommendations=tuple(
                sorted(recommendations, key=lambda item: item.recommendation_id)
            ),
            evidence=tuple(sorted(evidence, key=lambda item: item.evidence_id)),
            risks_and_uncertainties=tuple(sorted(set(risks))),
        )

    @staticmethod
    def _series_key(
        series: NormalizedMetricSeries,
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        return series.signal_name, tuple(sorted(series.labels.items()))

    def _series_evidence(
        self, observation: ObservationSnapshot
    ) -> list[AnalysisEvidence]:
        result: list[AnalysisEvidence] = []
        for index, series in enumerate(observation.normalized_series, start=1):
            result.append(
                AnalysisEvidence(
                    evidence_id=f"series-{index:04d}",
                    source="normalized_series",
                    signal_name=series.signal_name,
                    labels=series.labels,
                    interval_start=series.samples[0].timestamp,
                    interval_end=series.samples[-1].timestamp,
                    sample_count=len(series.samples),
                    description=(
                        f"{series.source_metric_name} normalized as "
                        f"{series.signal_name}"
                    ),
                )
            )
        return result

    @staticmethod
    def _quality_evidence(
        observation: ObservationSnapshot,
    ) -> tuple[list[AnalysisEvidence], list[str]]:
        evidence: list[AnalysisEvidence] = []
        risks: list[str] = []
        for index, issue in enumerate(observation.quality_report.issues, start=1):
            description = f"{issue.code}: {issue.field}: {issue.message}"
            evidence.append(
                AnalysisEvidence(
                    evidence_id=f"quality-{index:04d}",
                    source="quality_report",
                    resource_field=issue.field,
                    sample_count=0,
                    description=description,
                )
            )
            risks.append(description)
        return evidence, risks

    @staticmethod
    def _application_resources(
        observation: ObservationSnapshot,
    ) -> ContainerResources | None:
        return next(
            (
                item
                for item in observation.workload_snapshot.container_resources
                if item.container_name == "application"
            ),
            None,
        )

    @staticmethod
    def _resource_evidence(
        resources: ContainerResources | None,
    ) -> list[AnalysisEvidence]:
        if resources is None:
            return []
        result: list[AnalysisEvidence] = []
        for field in ("cpu_request", "cpu_limit", "memory_request", "memory_limit"):
            value = getattr(resources, field)
            if value is not None:
                result.append(
                    AnalysisEvidence(
                        evidence_id=f"resource-{field.replace('_', '-')}",
                        source="workload_configuration",
                        resource_field=field,
                        labels={"container": resources.container_name},
                        sample_count=0,
                        description=f"application {field} is {value}",
                    )
                )
        return result

    def _statistics(
        self,
        observation: ObservationSnapshot,
        evidence_by_series: dict[tuple[str, tuple[tuple[str, str], ...]], str],
        resources: ContainerResources | None,
        resource_evidence: list[AnalysisEvidence],
    ) -> tuple[list[CalculatedStatistic], list[str]]:
        statistics: list[CalculatedStatistic] = []
        risks: list[str] = []
        series_by_scope: dict[tuple[str, tuple[str, str]], NormalizedMetricSeries] = {}
        for series in observation.normalized_series:
            if series.signal_name not in _RESOURCE_SIGNALS:
                continue
            key = (series.signal_name, _scope(series))
            if key in series_by_scope:
                risks.append(
                    f"Duplicate normalized scope suppressed for {series.signal_name} "
                    f"{dict(series.labels)}."
                )
                continue
            series_by_scope[key] = series

        resource_values = self._resource_values(resources, risks)
        resource_evidence_ids = {
            item.resource_field: item.evidence_id for item in resource_evidence
        }
        scopes = sorted(
            scope
            for signal, scope in series_by_scope
            if signal in {"cpu_usage_seconds_total", "memory_working_set_bytes"}
        )
        scopes = sorted(set(scopes))
        for pod, container in scopes:
            labels = _scope_labels(pod, container)
            cpu = series_by_scope.get(("cpu_usage_seconds_total", (pod, container)))
            if cpu is not None:
                summary = _counter_summary(cpu)
                if summary is None:
                    risks.append(f"CPU counter is unusable for {pod}/{container}.")
                else:
                    _, average, peak, coalesced_updates = summary
                    if coalesced_updates:
                        risks.append(
                            "CPU counter samples contain repeated range evaluations "
                            f"for {pod}/{container}; peak rate uses intervals between "
                            "observed counter updates, excludes the first potentially "
                            "partial update, and remains limited by scrape cadence."
                        )
                    cpu_evidence = self._evidence_id(cpu, evidence_by_series)
                    self._add_stat(
                        statistics,
                        "cpu_average_cores",
                        average,
                        "cores",
                        labels,
                        (cpu_evidence,),
                    )
                    self._add_stat(
                        statistics,
                        "cpu_peak_cores",
                        peak,
                        "cores",
                        labels,
                        (cpu_evidence,),
                    )
                    self._resource_ratio_stats(
                        statistics,
                        labels,
                        average,
                        peak,
                        resource_values,
                        cpu_evidence,
                        resource_evidence_ids,
                    )
            self._throttle_stats(
                statistics,
                series_by_scope,
                evidence_by_series,
                pod,
                container,
            )
            memory = series_by_scope.get(("memory_working_set_bytes", (pod, container)))
            if memory is not None:
                self._memory_stats(
                    statistics,
                    memory,
                    evidence_by_series,
                    resource_values,
                    resource_evidence_ids,
                )

        self._http_stats(observation, evidence_by_series, statistics, risks)
        if not scopes:
            risks.append("No per-container CPU or memory series were available.")
        return statistics, risks

    @staticmethod
    def _resource_values(
        resources: ContainerResources | None,
        risks: list[str],
    ) -> dict[str, float]:
        if resources is None:
            risks.append("Application container resources were not observed.")
            return {}
        result: dict[str, float] = {}
        for field in ("cpu_request", "cpu_limit"):
            value = getattr(resources, field)
            if value is None:
                risks.append(f"Application {field} is missing.")
                continue
            try:
                result[field] = _cpu_millicores(value) / 1000
            except ValueError as error:
                risks.append(str(error))
        for field in ("memory_request", "memory_limit"):
            value = getattr(resources, field)
            if value is None:
                risks.append(f"Application {field} is missing.")
                continue
            try:
                result[field] = float(_memory_bytes(value))
            except ValueError as error:
                risks.append(str(error))
        return result

    @staticmethod
    def _evidence_id(
        series: NormalizedMetricSeries,
        evidence_by_series: dict[tuple[str, tuple[tuple[str, str], ...]], str],
    ) -> str:
        return evidence_by_series[
            (series.signal_name, tuple(sorted(series.labels.items())))
        ]

    @staticmethod
    def _add_stat(
        statistics: list[CalculatedStatistic],
        name: str,
        value: float,
        unit: str,
        labels: dict[str, str],
        evidence_ids: tuple[str, ...],
        aggregation_scope: str = "pod_container",
    ) -> None:
        suffix = ":".join(labels.get(key, "all") for key in sorted(labels))
        statistics.append(
            CalculatedStatistic(
                statistic_id=f"{name}:{suffix}",
                name=name,
                value=value,
                unit=unit,
                aggregation_scope=aggregation_scope,
                labels=labels,
                evidence_ids=tuple(sorted(set(evidence_ids))),
            )
        )

    def _resource_ratio_stats(
        self,
        statistics: list[CalculatedStatistic],
        labels: dict[str, str],
        average: float,
        peak: float,
        resources: dict[str, float],
        cpu_evidence: str,
        resource_evidence: dict[str | None, str],
    ) -> None:
        if "cpu_request" in resources and "cpu_request" in resource_evidence:
            self._add_stat(
                statistics,
                "cpu_request_utilization_average_ratio",
                average / resources["cpu_request"],
                "ratio",
                labels,
                (cpu_evidence, resource_evidence["cpu_request"]),
            )
        if "cpu_limit" in resources and "cpu_limit" in resource_evidence:
            self._add_stat(
                statistics,
                "cpu_limit_utilization_peak_ratio",
                peak / resources["cpu_limit"],
                "ratio",
                labels,
                (cpu_evidence, resource_evidence["cpu_limit"]),
            )

    def _throttle_stats(
        self,
        statistics: list[CalculatedStatistic],
        series_by_scope: dict[tuple[str, tuple[str, str]], NormalizedMetricSeries],
        evidence_by_series: dict[tuple[str, tuple[tuple[str, str], ...]], str],
        pod: str,
        container: str,
    ) -> None:
        labels = _scope_labels(pod, container)
        periods = series_by_scope.get(("cpu_cfs_periods_total", (pod, container)))
        throttled = series_by_scope.get(
            ("cpu_cfs_throttled_periods_total", (pod, container))
        )
        throttled_seconds = series_by_scope.get(
            ("cpu_cfs_throttled_seconds_total", (pod, container))
        )
        period_summary = _counter_summary(periods) if periods else None
        throttled_summary = _counter_summary(throttled) if throttled else None
        if (
            period_summary is not None
            and throttled_summary is not None
            and period_summary[0] > 0
            and periods is not None
            and throttled is not None
        ):
            self._add_stat(
                statistics,
                "cpu_throttle_period_ratio",
                throttled_summary[0] / period_summary[0],
                "ratio",
                labels,
                (
                    self._evidence_id(periods, evidence_by_series),
                    self._evidence_id(throttled, evidence_by_series),
                ),
            )
        seconds_summary = (
            _counter_summary(throttled_seconds) if throttled_seconds else None
        )
        if seconds_summary is not None and throttled_seconds is not None:
            self._add_stat(
                statistics,
                "cpu_throttled_seconds_per_second",
                seconds_summary[1],
                "seconds_per_second",
                labels,
                (self._evidence_id(throttled_seconds, evidence_by_series),),
            )

    def _memory_stats(
        self,
        statistics: list[CalculatedStatistic],
        memory: NormalizedMetricSeries,
        evidence_by_series: dict[tuple[str, tuple[tuple[str, str], ...]], str],
        resources: dict[str, float],
        resource_evidence: dict[str | None, str],
    ) -> None:
        labels = _scope_labels(*_scope(memory))
        values = [sample.value for sample in memory.samples]
        evidence = self._evidence_id(memory, evidence_by_series)
        mean = fmean(values)
        p95 = _percentile(values, 0.95)
        maximum = max(values)
        for name, value in (
            ("memory_mean_working_set_bytes", mean),
            ("memory_p95_working_set_bytes", p95),
            ("memory_max_working_set_bytes", maximum),
        ):
            self._add_stat(statistics, name, value, "bytes", labels, (evidence,))
        if "memory_request" in resources and "memory_request" in resource_evidence:
            self._add_stat(
                statistics,
                "memory_request_utilization_p95_ratio",
                p95 / resources["memory_request"],
                "ratio",
                labels,
                (evidence, resource_evidence["memory_request"]),
            )
        if "memory_limit" in resources and "memory_limit" in resource_evidence:
            self._add_stat(
                statistics,
                "memory_limit_utilization_max_ratio",
                maximum / resources["memory_limit"],
                "ratio",
                labels,
                (evidence, resource_evidence["memory_limit"]),
            )

    def _http_stats(
        self,
        observation: ObservationSnapshot,
        evidence_by_series: dict[tuple[str, tuple[tuple[str, str], ...]], str],
        statistics: list[CalculatedStatistic],
        risks: list[str],
    ) -> None:
        work_series = [
            series
            for series in observation.normalized_series
            if series.labels.get("route") == "/work"
        ]
        requests = [
            series
            for series in work_series
            if series.signal_name == "http_requests_total"
        ]
        errors = [
            series
            for series in work_series
            if series.signal_name == "http_request_errors_total"
        ]
        request_summaries = [(series, _counter_summary(series)) for series in requests]
        valid_requests = [
            (series, summary)
            for series, summary in request_summaries
            if summary is not None
        ]
        if valid_requests:
            request_evidence = tuple(
                self._evidence_id(series, evidence_by_series)
                for series, _ in valid_requests
            )
            self._add_stat(
                statistics,
                "http_requests_per_second",
                sum(summary[1] for _, summary in valid_requests),
                "requests_per_second",
                {"route": "/work"},
                request_evidence,
                "workload_route",
            )
            total_requests = sum(summary[0] for _, summary in valid_requests)
            valid_errors = [
                (series, summary)
                for series in errors
                if (summary := _counter_summary(series)) is not None
            ]
            if valid_errors and total_requests > 0:
                self._add_stat(
                    statistics,
                    "http_error_ratio",
                    sum(summary[0] for _, summary in valid_errors) / total_requests,
                    "ratio",
                    {"route": "/work"},
                    tuple(
                        sorted(
                            {
                                *request_evidence,
                                *(
                                    self._evidence_id(series, evidence_by_series)
                                    for series, _ in valid_errors
                                ),
                            }
                        )
                    ),
                    "workload_route",
                )
        duration_sums = [
            series
            for series in work_series
            if series.signal_name == "http_request_duration_seconds_sum"
        ]
        duration_counts = [
            series
            for series in work_series
            if series.signal_name == "http_request_duration_seconds_count"
        ]
        sum_values = [
            (series, summary)
            for series in duration_sums
            if (summary := _counter_summary(series)) is not None
        ]
        count_values = [
            (series, summary)
            for series in duration_counts
            if (summary := _counter_summary(series)) is not None
        ]
        total_count = sum(summary[0] for _, summary in count_values)
        if sum_values and total_count > 0:
            duration_evidence = tuple(
                self._evidence_id(series, evidence_by_series)
                for series, _ in [*sum_values, *count_values]
            )
            self._add_stat(
                statistics,
                "http_latency_mean_seconds",
                sum(summary[0] for _, summary in sum_values) / total_count,
                "seconds",
                {"route": "/work"},
                duration_evidence,
                "workload_route",
            )
        histogram = self._histogram_quantile(work_series, evidence_by_series, 0.95)
        if histogram is not None:
            value, histogram_evidence = histogram
            self._add_stat(
                statistics,
                "http_latency_p95_seconds",
                value,
                "seconds",
                {"route": "/work"},
                histogram_evidence,
                "workload_route",
            )
        if requests and not valid_requests:
            risks.append("HTTP request counters were present but unusable.")

    def _histogram_quantile(
        self,
        series_values: list[NormalizedMetricSeries],
        evidence_by_series: dict[tuple[str, tuple[tuple[str, str], ...]], str],
        quantile: float,
    ) -> tuple[float, tuple[str, ...]] | None:
        buckets: dict[float, float] = {}
        evidence: list[str] = []
        for series in series_values:
            if series.signal_name != "http_request_duration_seconds_bucket":
                continue
            summary = _counter_summary(series)
            if summary is None:
                continue
            bound_text = series.labels.get("le")
            if bound_text is None:
                continue
            try:
                bound = math.inf if bound_text == "+Inf" else float(bound_text)
            except ValueError:
                continue
            buckets[bound] = buckets.get(bound, 0.0) + summary[0]
            evidence.append(self._evidence_id(series, evidence_by_series))
        if math.inf not in buckets or buckets[math.inf] <= 0:
            return None
        rank = quantile * buckets[math.inf]
        previous_bound = 0.0
        previous_count = 0.0
        finite_bounds = sorted(bound for bound in buckets if math.isfinite(bound))
        for bound in finite_bounds:
            count = buckets[bound]
            if count >= rank:
                fraction = (rank - previous_count) / (count - previous_count)
                return (
                    previous_bound + (bound - previous_bound) * fraction,
                    tuple(sorted(set(evidence))),
                )
            previous_bound = bound
            previous_count = count
        return previous_bound, tuple(sorted(set(evidence)))

    @staticmethod
    def _sufficiency(
        observation: ObservationSnapshot,
        statistics: list[CalculatedStatistic],
    ) -> AnalysisSufficiency:
        has_resource_stat = any(
            item.name.startswith(("cpu_", "memory_")) for item in statistics
        )
        if (
            observation.quality_report.status is QualityStatus.INSUFFICIENT
            or not has_resource_stat
        ):
            return AnalysisSufficiency.INSUFFICIENT
        if observation.quality_report.status is QualityStatus.DEGRADED:
            return AnalysisSufficiency.PARTIAL
        return AnalysisSufficiency.SUFFICIENT

    def _conditions(
        self,
        statistics: list[CalculatedStatistic],
    ) -> list[DetectedCondition]:
        conditions: list[DetectedCondition] = []
        policies = (
            (
                "cpu_throttle_period_ratio",
                "cpu_throttling_high",
                CPU_THROTTLE_THRESHOLD,
                "CPU CFS throttling is high",
                CPU_THROTTLE_CRITICAL_THRESHOLD,
            ),
            (
                "cpu_limit_utilization_peak_ratio",
                "cpu_limit_saturation",
                CPU_LIMIT_THRESHOLD,
                "Peak CPU usage is near the configured limit",
                LIMIT_CRITICAL_THRESHOLD,
            ),
            (
                "memory_limit_utilization_max_ratio",
                "memory_limit_pressure",
                MEMORY_LIMIT_THRESHOLD,
                "Maximum memory working set is near the configured limit",
                LIMIT_CRITICAL_THRESHOLD,
            ),
            (
                "cpu_request_utilization_average_ratio",
                "cpu_request_low",
                REQUEST_UTILIZATION_THRESHOLD,
                "Average CPU usage materially exceeds the request",
                REQUEST_UTILIZATION_CRITICAL_THRESHOLD,
            ),
            (
                "memory_request_utilization_p95_ratio",
                "memory_request_low",
                REQUEST_UTILIZATION_THRESHOLD,
                "Memory p95 materially exceeds the request",
                REQUEST_UTILIZATION_CRITICAL_THRESHOLD,
            ),
        )
        for statistic in statistics:
            for (
                statistic_name,
                condition_type,
                threshold,
                message,
                critical_threshold,
            ) in policies:
                if statistic.name != statistic_name or statistic.value < threshold:
                    continue
                pod = statistic.labels.get("pod", "workload")
                container = statistic.labels.get("container", "application")
                conditions.append(
                    DetectedCondition(
                        condition_id=f"{condition_type}:{pod}:{container}",
                        condition_type=condition_type,
                        severity=(
                            ConditionSeverity.CRITICAL
                            if statistic.value >= critical_threshold
                            else ConditionSeverity.WARNING
                        ),
                        message=message,
                        observed_value=statistic.value,
                        threshold=threshold,
                        statistic_ids=(statistic.statistic_id,),
                        evidence_ids=statistic.evidence_ids,
                    )
                )
        return conditions

    def _recommendations(
        self,
        conditions: list[DetectedCondition],
        statistics: list[CalculatedStatistic],
        resources: ContainerResources | None,
        resource_evidence: list[AnalysisEvidence],
        risks: list[str],
    ) -> list[ResourceRecommendation]:
        if resources is None:
            return []
        by_type: dict[str, list[DetectedCondition]] = {}
        for condition in conditions:
            by_type.setdefault(condition.condition_type, []).append(condition)
        stats_by_id = {item.statistic_id: item for item in statistics}
        evidence_by_field = {
            item.resource_field: item.evidence_id for item in resource_evidence
        }
        recommendations: list[ResourceRecommendation] = []
        cpu_limit_conditions = [
            *by_type.get("cpu_throttling_high", []),
            *by_type.get("cpu_limit_saturation", []),
        ]
        if cpu_limit_conditions and resources.cpu_limit:
            peak_values = [
                item.value for item in statistics if item.name == "cpu_peak_cores"
            ]
            recommendation = self._cpu_recommendation(
                "cpu_limit",
                resources.cpu_limit,
                None,
                max(peak_values, default=0.0) * 1000,
                cpu_limit_conditions,
                stats_by_id,
                evidence_by_field,
            )
            if recommendation:
                recommendations.append(recommendation)
        request_conditions = by_type.get("cpu_request_low", [])
        if request_conditions and resources.cpu_request:
            average_values = [
                item.value for item in statistics if item.name == "cpu_average_cores"
            ]
            recommendation = self._cpu_recommendation(
                "cpu_request",
                resources.cpu_request,
                resources.cpu_limit,
                max(average_values, default=0.0) * 1000,
                request_conditions,
                stats_by_id,
                evidence_by_field,
            )
            if recommendation:
                recommendations.append(recommendation)
                target = (
                    math.ceil(
                        max(
                            _cpu_millicores(resources.cpu_request)
                            * RECOMMENDATION_MULTIPLIER,
                            max(average_values, default=0.0)
                            * 1000
                            * RECOMMENDATION_MULTIPLIER,
                        )
                        / 10
                    )
                    * 10
                )
                if _cpu_millicores(recommendation.recommended_value) < target:
                    risks.append(
                        f"CPU request headroom target {_format_cpu_millicores(target)} "
                        f"was constrained to {recommendation.recommended_value} by the "
                        "current CPU limit; the limit recommendation must be applied "
                        "or the request must be reevaluated before treating it as "
                        "adequately sized."
                    )
        memory_limit_conditions = by_type.get("memory_limit_pressure", [])
        if memory_limit_conditions and resources.memory_limit:
            maxima = [
                item.value
                for item in statistics
                if item.name == "memory_max_working_set_bytes"
            ]
            recommendation = self._memory_recommendation(
                "memory_limit",
                resources.memory_limit,
                None,
                max(maxima, default=0.0),
                memory_limit_conditions,
                stats_by_id,
                evidence_by_field,
            )
            if recommendation:
                recommendations.append(recommendation)
        memory_request_conditions = by_type.get("memory_request_low", [])
        if memory_request_conditions and resources.memory_request:
            p95_values = [
                item.value
                for item in statistics
                if item.name == "memory_p95_working_set_bytes"
            ]
            recommendation = self._memory_recommendation(
                "memory_request",
                resources.memory_request,
                resources.memory_limit,
                max(p95_values, default=0.0),
                memory_request_conditions,
                stats_by_id,
                evidence_by_field,
            )
            if recommendation:
                recommendations.append(recommendation)
        return recommendations

    @staticmethod
    def _recommendation_refs(
        conditions: list[DetectedCondition],
        stats_by_id: dict[str, CalculatedStatistic],
        resource_evidence_id: str | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        condition_ids = tuple(sorted(item.condition_id for item in conditions))
        statistic_ids = tuple(
            sorted({value for item in conditions for value in item.statistic_ids})
        )
        evidence_ids = {value for item in conditions for value in item.evidence_ids}
        for statistic_id in statistic_ids:
            evidence_ids.update(stats_by_id[statistic_id].evidence_ids)
        if resource_evidence_id:
            evidence_ids.add(resource_evidence_id)
        return condition_ids, statistic_ids, tuple(sorted(evidence_ids))

    def _cpu_recommendation(
        self,
        resource: str,
        current_value: str,
        configured_limit: str | None,
        observed_millicores: float,
        conditions: list[DetectedCondition],
        stats_by_id: dict[str, CalculatedStatistic],
        evidence_by_field: dict[str | None, str],
    ) -> ResourceRecommendation | None:
        try:
            current = _cpu_millicores(current_value)
            upper = current * MAX_INCREASE_MULTIPLIER
            if configured_limit:
                upper = min(upper, _cpu_millicores(configured_limit))
        except ValueError:
            return None
        candidate = max(
            current * RECOMMENDATION_MULTIPLIER,
            observed_millicores * RECOMMENDATION_MULTIPLIER,
        )
        recommended = min(math.ceil(candidate / 10) * 10, math.floor(upper / 10) * 10)
        if recommended <= current:
            return None
        constrained = recommended < math.ceil(candidate / 10) * 10
        condition_ids, statistic_ids, evidence_ids = self._recommendation_refs(
            conditions, stats_by_id, evidence_by_field.get(resource)
        )
        basis = (
            "average CPU usage exceeding the configured request"
            if resource == "cpu_request"
            else "CPU limit saturation or throttling"
        )
        return ResourceRecommendation(
            recommendation_id=f"increase-{resource.replace('_', '-')}",
            resource=resource,
            current_value=current_value,
            recommended_value=_format_cpu_millicores(recommended),
            lower_bound=current_value,
            upper_bound=_format_cpu_millicores(math.floor(upper)),
            rationale=(
                f"Increase is based on {basis}; the bounded value is "
                "below the 25% headroom target because of the applicable limit or "
                "policy cap."
                if constrained
                else f"Increase is based on {basis} with 25% headroom within the "
                "policy 2x cap."
            ),
            condition_ids=condition_ids,
            statistic_ids=statistic_ids,
            evidence_ids=evidence_ids,
        )

    def _memory_recommendation(
        self,
        resource: str,
        current_value: str,
        configured_limit: str | None,
        observed_bytes: float,
        conditions: list[DetectedCondition],
        stats_by_id: dict[str, CalculatedStatistic],
        evidence_by_field: dict[str | None, str],
    ) -> ResourceRecommendation | None:
        try:
            current = _memory_bytes(current_value)
            upper = current * MAX_INCREASE_MULTIPLIER
            if configured_limit:
                upper = min(upper, _memory_bytes(configured_limit))
        except ValueError:
            return None
        candidate = max(
            current * RECOMMENDATION_MULTIPLIER,
            observed_bytes * RECOMMENDATION_MULTIPLIER,
        )
        recommended = min(
            math.ceil(candidate / MIB) * MIB, math.floor(upper / MIB) * MIB
        )
        if recommended <= current:
            return None
        constrained = recommended < math.ceil(candidate / MIB) * MIB
        condition_ids, statistic_ids, evidence_ids = self._recommendation_refs(
            conditions, stats_by_id, evidence_by_field.get(resource)
        )
        basis = (
            "memory p95 exceeding the configured request"
            if resource == "memory_request"
            else "the maximum memory working set approaching the configured limit"
        )
        return ResourceRecommendation(
            recommendation_id=f"increase-{resource.replace('_', '-')}",
            resource=resource,
            current_value=current_value,
            recommended_value=_format_memory(recommended),
            lower_bound=current_value,
            upper_bound=_format_memory(math.floor(upper / MIB) * MIB),
            rationale=(
                f"Increase is based on {basis}; the bounded value is "
                "below the 25% headroom target because of the applicable limit or "
                "policy cap."
                if constrained
                else f"Increase is based on {basis} with 25% headroom within the "
                "policy 2x cap."
            ),
            condition_ids=condition_ids,
            statistic_ids=statistic_ids,
            evidence_ids=evidence_ids,
        )
