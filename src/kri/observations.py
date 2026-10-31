"""Deterministic M4 observation normalization, quality, storage, and replay."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from kri.contracts import (
    OBSERVATION_ID_PATTERN,
    DataQualityReport,
    MetricKind,
    MetricSeries,
    NormalizedMetricSeries,
    ObservationProvenance,
    ObservationSnapshot,
    ObservationSummary,
    QualityIssue,
    QualitySeverity,
    QualityStatus,
    RawMetricsSnapshot,
    WorkloadSnapshot,
)

BUILDER_VERSION = "1.0"


@dataclass(frozen=True)
class _NormalizationSpec:
    signal_name: str
    metric_kind: MetricKind
    expected_unit: str
    aggregation_scope: str
    stable_labels: tuple[str, ...]


NORMALIZATION_SPECS: dict[str, _NormalizationSpec] = {
    "container_cpu_usage_seconds_total": _NormalizationSpec(
        "cpu_usage_seconds_total",
        MetricKind.COUNTER,
        "cpu_seconds",
        "container",
        ("namespace", "pod", "container"),
    ),
    "container_cpu_cfs_periods_total": _NormalizationSpec(
        "cpu_cfs_periods_total",
        MetricKind.COUNTER,
        "periods",
        "container",
        ("namespace", "pod", "container"),
    ),
    "container_cpu_cfs_throttled_periods_total": _NormalizationSpec(
        "cpu_cfs_throttled_periods_total",
        MetricKind.COUNTER,
        "periods",
        "container",
        ("namespace", "pod", "container"),
    ),
    "container_cpu_cfs_throttled_seconds_total": _NormalizationSpec(
        "cpu_cfs_throttled_seconds_total",
        MetricKind.COUNTER,
        "seconds",
        "container",
        ("namespace", "pod", "container"),
    ),
    "container_memory_working_set_bytes": _NormalizationSpec(
        "memory_working_set_bytes",
        MetricKind.GAUGE,
        "bytes",
        "container",
        ("namespace", "pod", "container"),
    ),
    "kri_http_requests_total": _NormalizationSpec(
        "http_requests_total",
        MetricKind.COUNTER,
        "requests",
        "pod_route_status",
        ("namespace", "pod", "method", "route", "status_code"),
    ),
    "kri_http_request_errors_total": _NormalizationSpec(
        "http_request_errors_total",
        MetricKind.COUNTER,
        "errors",
        "pod_route_status",
        ("namespace", "pod", "method", "route", "status_code"),
    ),
    "kri_http_request_duration_seconds_bucket": _NormalizationSpec(
        "http_request_duration_seconds_bucket",
        MetricKind.HISTOGRAM_BUCKET,
        "observations",
        "pod_route_bucket",
        ("namespace", "pod", "method", "route", "le"),
    ),
    "kri_http_request_duration_seconds_sum": _NormalizationSpec(
        "http_request_duration_seconds_sum",
        MetricKind.HISTOGRAM_SUM,
        "seconds",
        "pod_route",
        ("namespace", "pod", "method", "route"),
    ),
    "kri_http_request_duration_seconds_count": _NormalizationSpec(
        "http_request_duration_seconds_count",
        MetricKind.HISTOGRAM_COUNT,
        "observations",
        "pod_route",
        ("namespace", "pod", "method", "route"),
    ),
}

_CUMULATIVE_KINDS = {
    MetricKind.COUNTER,
    MetricKind.HISTOGRAM_BUCKET,
    MetricKind.HISTOGRAM_SUM,
    MetricKind.HISTOGRAM_COUNT,
}


class ObservationError(RuntimeError):
    """Raw inputs cannot produce or replay a trustworthy observation."""


class ObservationStoreError(RuntimeError):
    """A versioned observation artifact could not be stored or loaded."""


def _source_digest(
    workload: WorkloadSnapshot,
    metrics: RawMetricsSnapshot,
) -> str:
    canonical = json.dumps(
        {
            "workload_snapshot": workload.model_dump(mode="json"),
            "raw_metrics_snapshot": metrics.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _issue(
    severity: QualitySeverity,
    code: str,
    source: str,
    field: str,
    message: str,
) -> QualityIssue:
    return QualityIssue(
        severity=severity,
        code=code,
        source=source,
        field=field,
        message=message,
    )


class ObservationBuilder:
    """Build and deterministically replay M4 observation snapshots."""

    def __init__(
        self,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.clock = clock

    def build(
        self,
        workload: WorkloadSnapshot,
        metrics: RawMetricsSnapshot,
        observation_id: str | None = None,
    ) -> ObservationSnapshot:
        created_at = self.clock()
        if created_at.tzinfo is None:
            raise ObservationError(
                "observation builder clock returned a naive timestamp"
            )
        identifier = observation_id or f"obs-{uuid4().hex[:12]}"
        return self._assemble(workload, metrics, identifier, created_at)

    def replay(self, snapshot: ObservationSnapshot) -> ObservationSnapshot:
        if (
            _source_digest(
                snapshot.workload_snapshot,
                snapshot.raw_metrics_snapshot,
            )
            != snapshot.provenance.source_digest_sha256
        ):
            raise ObservationError("observation raw-source digest does not match")
        replayed = self._assemble(
            snapshot.workload_snapshot,
            snapshot.raw_metrics_snapshot,
            snapshot.observation_id,
            snapshot.created_at,
        )
        if replayed != snapshot:
            raise ObservationError("observation replay does not match stored content")
        return replayed

    def _assemble(
        self,
        workload: WorkloadSnapshot,
        metrics: RawMetricsSnapshot,
        observation_id: str,
        created_at: datetime,
    ) -> ObservationSnapshot:
        if workload.identity != metrics.identity:
            raise ObservationError("Kubernetes and Prometheus identities do not match")
        normalized, report = self._normalize(workload, metrics)
        provenance = ObservationProvenance(
            builder_version=BUILDER_VERSION,
            workload_schema_version=workload.schema_version,
            metrics_schema_version=metrics.schema_version,
            workload_observed_at=workload.observed_at,
            metrics_collected_at=metrics.collected_at,
            source_digest_sha256=_source_digest(workload, metrics),
        )
        return ObservationSnapshot(
            observation_id=observation_id,
            created_at=created_at,
            workload_snapshot=workload,
            raw_metrics_snapshot=metrics,
            normalized_series=normalized,
            quality_report=report,
            provenance=provenance,
        )

    def _normalize(
        self,
        workload: WorkloadSnapshot,
        metrics: RawMetricsSnapshot,
    ) -> tuple[tuple[NormalizedMetricSeries, ...], DataQualityReport]:
        issues: list[QualityIssue] = []
        for missing in sorted(
            workload.missing_data,
            key=lambda value: (value.source, value.field, value.reason),
        ):
            issues.append(
                _issue(
                    QualitySeverity.WARNING,
                    "source_missing_data",
                    missing.source,
                    missing.field,
                    missing.reason,
                )
            )
        if not workload.pods:
            issues.append(
                _issue(
                    QualitySeverity.ERROR,
                    "no_pods",
                    "kubernetes",
                    "pods",
                    "no workload Pods were observed",
                )
            )

        observed_names = {series.metric_name for series in metrics.series}
        reported_missing = {missing.field: missing for missing in metrics.missing_data}
        for metric_name in sorted(NORMALIZATION_SPECS.keys() - observed_names):
            reported = reported_missing.get(metric_name)
            issues.append(
                _issue(
                    QualitySeverity.WARNING if reported else QualitySeverity.ERROR,
                    "missing_metric_family"
                    if reported
                    else "unreported_missing_metric_family",
                    "prometheus",
                    metric_name,
                    reported.reason
                    if reported
                    else "metric family is absent without a missing-data report",
                )
            )
        for missing_name, missing in sorted(reported_missing.items()):
            if missing_name not in NORMALIZATION_SPECS:
                issues.append(
                    _issue(
                        QualitySeverity.WARNING,
                        "source_missing_data",
                        "prometheus",
                        missing_name,
                        missing.reason,
                    )
                )

        normalized: list[NormalizedMetricSeries] = []
        collision_keys: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for series in sorted(metrics.series, key=self._raw_sort_key):
            spec = NORMALIZATION_SPECS.get(series.metric_name)
            if spec is None:
                issues.append(
                    _issue(
                        QualitySeverity.ERROR,
                        "unknown_metric_family",
                        "normalization",
                        series.metric_name,
                        "no M4 normalization contract exists for this metric",
                    )
                )
                continue
            labels = {
                name: series.labels[name]
                for name in spec.stable_labels
                if name in series.labels
            }
            missing_labels = sorted(set(spec.stable_labels) - labels.keys())
            for label in missing_labels:
                issues.append(
                    _issue(
                        QualitySeverity.ERROR,
                        "missing_series_label",
                        "normalization",
                        f"{series.metric_name}.labels.{label}",
                        "required stable label is absent",
                    )
                )
            if series.unit != spec.expected_unit:
                issues.append(
                    _issue(
                        QualitySeverity.ERROR,
                        "unit_mismatch",
                        "normalization",
                        series.metric_name,
                        f"expected {spec.expected_unit}, observed {series.unit}",
                    )
                )
            self._check_samples(series, spec, issues)
            collision_key = (spec.signal_name, tuple(sorted(labels.items())))
            if collision_key in collision_keys:
                issues.append(
                    _issue(
                        QualitySeverity.ERROR,
                        "normalized_series_collision",
                        "normalization",
                        series.metric_name,
                        "multiple raw series map to the same normalized scope",
                    )
                )
            collision_keys.add(collision_key)
            normalized.append(
                NormalizedMetricSeries(
                    signal_name=spec.signal_name,
                    source_metric_name=series.metric_name,
                    metric_kind=spec.metric_kind,
                    unit=series.unit,
                    aggregation_scope=spec.aggregation_scope,
                    labels=labels,
                    samples=series.samples,
                )
            )

        if not metrics.series:
            issues.append(
                _issue(
                    QualitySeverity.ERROR,
                    "no_metric_series",
                    "prometheus",
                    "series",
                    "no raw metric series were collected",
                )
            )
        issues.sort(
            key=lambda item: (
                item.severity.value,
                item.code,
                item.source,
                item.field,
                item.message,
            )
        )
        normalized.sort(
            key=lambda item: (
                item.signal_name,
                tuple(sorted(item.labels.items())),
                item.source_metric_name,
            )
        )
        status = (
            QualityStatus.INSUFFICIENT
            if any(issue.severity is QualitySeverity.ERROR for issue in issues)
            else QualityStatus.DEGRADED
            if issues
            else QualityStatus.COMPLETE
        )
        report = DataQualityReport(
            status=status,
            expected_metric_families=len(NORMALIZATION_SPECS),
            observed_metric_families=len(
                observed_names.intersection(NORMALIZATION_SPECS)
            ),
            issues=tuple(issues),
        )
        return tuple(normalized), report

    @staticmethod
    def _raw_sort_key(
        series: MetricSeries,
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        return series.metric_name, tuple(sorted(series.labels.items()))

    @staticmethod
    def _check_samples(
        series: MetricSeries,
        spec: _NormalizationSpec,
        issues: list[QualityIssue],
    ) -> None:
        if spec.metric_kind in _CUMULATIVE_KINDS:
            if len(series.samples) < 2:
                issues.append(
                    _issue(
                        QualitySeverity.WARNING,
                        "insufficient_counter_samples",
                        "prometheus",
                        series.metric_name,
                        "at least two samples are required for a future rate",
                    )
                )
            if any(
                current.value < previous.value
                for previous, current in zip(
                    series.samples,
                    series.samples[1:],
                    strict=False,
                )
            ):
                issues.append(
                    _issue(
                        QualitySeverity.WARNING,
                        "counter_reset",
                        "prometheus",
                        series.metric_name,
                        "cumulative source value decreased inside the interval",
                    )
                )
        if spec.metric_kind is MetricKind.HISTOGRAM_BUCKET:
            bound = series.labels.get("le")
            try:
                if bound != "+Inf":
                    float(bound or "")
            except ValueError:
                issues.append(
                    _issue(
                        QualitySeverity.ERROR,
                        "malformed_histogram_bound",
                        "normalization",
                        f"{series.metric_name}.labels.le",
                        f"invalid histogram bound: {bound!r}",
                    )
                )


class ObservationStore:
    """Immutable atomic JSON storage plus bounded inspection and replay."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, observation_id: str) -> Path:
        if OBSERVATION_ID_PATTERN.fullmatch(observation_id) is None:
            raise ObservationStoreError("invalid observation ID")
        return self.directory / f"{observation_id}.json"

    def save(self, snapshot: ObservationSnapshot) -> Path:
        path = self._path(snapshot.observation_id)
        if path.exists():
            raise ObservationStoreError(
                f"observation already exists: {snapshot.observation_id}"
            )
        try:
            ObservationBuilder().replay(snapshot)
        except ObservationError as error:
            raise ObservationStoreError(str(error)) from error
        temporary = path.with_suffix(".json.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                snapshot.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as error:
            raise ObservationStoreError(str(error)) from error
        return path

    def load(self, observation_id: str) -> ObservationSnapshot:
        path = self._path(observation_id)
        try:
            snapshot = ObservationSnapshot.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise ObservationStoreError(
                f"observation does not exist: {observation_id}"
            ) from error
        except (OSError, ValidationError) as error:
            raise ObservationStoreError(
                f"invalid observation artifact: {error}"
            ) from error
        if (
            _source_digest(
                snapshot.workload_snapshot,
                snapshot.raw_metrics_snapshot,
            )
            != snapshot.provenance.source_digest_sha256
        ):
            raise ObservationStoreError("observation raw-source digest does not match")
        return snapshot

    def inspect(self, observation_id: str) -> ObservationSummary:
        snapshot = self.load(observation_id)
        return ObservationSummary(
            observation_id=snapshot.observation_id,
            created_at=snapshot.created_at,
            identity=snapshot.workload_snapshot.identity,
            interval_start=snapshot.raw_metrics_snapshot.interval_start,
            interval_end=snapshot.raw_metrics_snapshot.interval_end,
            quality_status=snapshot.quality_report.status,
            issue_count=len(snapshot.quality_report.issues),
            normalized_series_count=len(snapshot.normalized_series),
            sample_count=sum(
                len(series.samples) for series in snapshot.normalized_series
            ),
        )

    def replay(self, observation_id: str) -> ObservationSnapshot:
        try:
            return ObservationBuilder().replay(self.load(observation_id))
        except ObservationError as error:
            raise ObservationStoreError(str(error)) from error
