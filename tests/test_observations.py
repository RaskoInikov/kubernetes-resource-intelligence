"""Offline tests for M4 normalization, quality, storage, and replay."""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from kri.contracts import (
    ContainerResources,
    DataQualityReport,
    MetricSample,
    MetricSeries,
    MissingData,
    ObservationProvenance,
    ObservationSnapshot,
    PodObservation,
    QualityIssue,
    QualitySeverity,
    QualityStatus,
    RawMetricsSnapshot,
    WorkloadIdentity,
    WorkloadSnapshot,
)
from kri.observations import (
    NORMALIZATION_SPECS,
    ObservationBuilder,
    ObservationError,
    ObservationStore,
    ObservationStoreError,
)

START = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
END = START + timedelta(seconds=5)
CREATED = END + timedelta(seconds=1)


def identity(uid: str = "deployment-uid") -> WorkloadIdentity:
    return WorkloadIdentity(
        cluster="kind-test",
        namespace="payments",
        deployment_name="kri-workload",
        deployment_uid=uid,
    )


def workload(
    *,
    workload_identity: WorkloadIdentity | None = None,
    pods: tuple[PodObservation, ...] | None = None,
    missing: tuple[MissingData, ...] = (),
) -> WorkloadSnapshot:
    observed_pods = pods
    if observed_pods is None:
        observed_pods = (
            PodObservation(
                name="kri-workload-abc",
                uid="pod-uid",
                ready=True,
                restart_count=0,
            ),
        )
    return WorkloadSnapshot(
        observed_at=END,
        identity=workload_identity or identity(),
        deployment_resource_version="42",
        pods=observed_pods,
        container_resources=(
            ContainerResources(
                container_name="application",
                cpu_request="50m",
                cpu_limit="100m",
                memory_request="64Mi",
                memory_limit="192Mi",
            ),
        ),
        events=(),
        missing_data=missing,
    )


def _labels(metric_name: str) -> dict[str, str]:
    labels = {
        "__name__": metric_name,
        "namespace": "payments",
        "pod": "kri-workload-abc",
        "instance": "10.0.0.1:8080",
    }
    if metric_name.startswith("container_"):
        labels["container"] = "application"
    else:
        labels.update(method="GET", route="/work", job="kri-workload")
    if metric_name in {"kri_http_requests_total", "kri_http_request_errors_total"}:
        labels["status_code"] = "200"
    if metric_name.endswith("_bucket"):
        labels["le"] = "0.5"
    return labels


def metric_series(
    metric_name: str,
    *,
    values: tuple[float, ...] = (1.0, 2.0),
    labels: dict[str, str] | None = None,
    unit: str | None = None,
) -> MetricSeries:
    spec = NORMALIZATION_SPECS[metric_name]
    samples = tuple(
        MetricSample(timestamp=START + timedelta(seconds=index * 5), value=value)
        for index, value in enumerate(values)
    )
    return MetricSeries(
        metric_name=metric_name,
        labels=labels or _labels(metric_name),
        unit=unit or spec.expected_unit,
        samples=samples,
    )


def raw_metrics(
    *,
    metrics_identity: WorkloadIdentity | None = None,
    series: tuple[MetricSeries, ...] | None = None,
    missing: tuple[MissingData, ...] = (),
) -> RawMetricsSnapshot:
    observed_series = series
    if observed_series is None:
        observed_series = tuple(
            metric_series(name) for name in reversed(NORMALIZATION_SPECS)
        )
    return RawMetricsSnapshot(
        collected_at=CREATED,
        interval_start=START,
        interval_end=END,
        identity=metrics_identity or identity(),
        series=observed_series,
        missing_data=missing,
    )


def builder() -> ObservationBuilder:
    return ObservationBuilder(clock=lambda: CREATED)


def test_build_complete_snapshot_preserves_raw_data_and_normalizes_stably() -> None:
    raw = raw_metrics()

    snapshot = builder().build(workload(), raw, "obs-complete")

    assert snapshot.schema_version == "1.0"
    assert snapshot.quality_report.status is QualityStatus.COMPLETE
    assert snapshot.quality_report.issues == ()
    assert snapshot.quality_report.expected_metric_families == 10
    assert snapshot.quality_report.observed_metric_families == 10
    assert snapshot.raw_metrics_snapshot == raw
    assert len(snapshot.normalized_series) == 10
    assert [item.signal_name for item in snapshot.normalized_series] == sorted(
        item.signal_name for item in snapshot.normalized_series
    )
    cpu = next(
        item
        for item in snapshot.normalized_series
        if item.signal_name == "cpu_usage_seconds_total"
    )
    assert cpu.labels == {
        "namespace": "payments",
        "pod": "kri-workload-abc",
        "container": "application",
    }
    assert "instance" not in cpu.labels
    assert cpu.samples == next(
        item.samples
        for item in raw.series
        if item.metric_name == "container_cpu_usage_seconds_total"
    )
    assert len(snapshot.provenance.source_digest_sha256) == 64
    assert builder().replay(snapshot) == snapshot


def test_builder_normalizes_timestamps_to_utc_and_generates_safe_id() -> None:
    local_time = datetime(2026, 10, 31, 15, 0, tzinfo=timezone(timedelta(hours=3)))
    snapshot = ObservationBuilder(clock=lambda: local_time).build(
        workload(), raw_metrics()
    )

    assert snapshot.observation_id.startswith("obs-")
    assert snapshot.created_at == datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def test_builder_rejects_identity_mismatch_and_naive_clock() -> None:
    with pytest.raises(ObservationError, match="identities"):
        builder().build(
            workload(),
            raw_metrics(metrics_identity=identity("different-uid")),
            "obs-mismatch",
        )
    with pytest.raises(ObservationError, match="naive"):
        ObservationBuilder(clock=lambda: datetime(2026, 1, 1)).build(
            workload(), raw_metrics(), "obs-naive"
        )


def test_degraded_quality_reports_missing_data_short_counter_and_reset() -> None:
    error_name = "kri_http_request_errors_total"
    series = tuple(
        metric_series(
            name,
            values=(2.0, 1.0)
            if name == "container_cpu_usage_seconds_total"
            else (1.0,)
            if name == "kri_http_requests_total"
            else (1.0, 2.0),
        )
        for name in NORMALIZATION_SPECS
        if name != error_name
    )
    snapshot = builder().build(
        workload(
            missing=(
                MissingData(source="kubernetes", field="events", reason="not reported"),
            )
        ),
        raw_metrics(
            series=series,
            missing=(
                MissingData(
                    source="prometheus",
                    field=error_name,
                    reason="query returned no series",
                ),
                MissingData(
                    source="prometheus",
                    field="optional_future_metric",
                    reason="not configured",
                ),
            ),
        ),
        "obs-degraded",
    )

    assert snapshot.quality_report.status is QualityStatus.DEGRADED
    assert snapshot.quality_report.observed_metric_families == 9
    codes = [item.code for item in snapshot.quality_report.issues]
    assert codes == sorted(codes)
    assert set(codes) == {
        "counter_reset",
        "insufficient_counter_samples",
        "missing_metric_family",
        "source_missing_data",
    }


def test_insufficient_quality_reports_contract_violations() -> None:
    bucket_name = "kri_http_request_duration_seconds_bucket"
    malformed_bucket_labels = _labels(bucket_name)
    malformed_bucket_labels["le"] = "not-a-number"
    request_name = "kri_http_requests_total"
    missing_label_values = _labels(request_name)
    del missing_label_values["route"]
    duplicate = metric_series("container_memory_working_set_bytes")
    unknown = MetricSeries(
        metric_name="unknown_total",
        labels={"namespace": "payments", "pod": "kri-workload-abc"},
        unit="things",
        samples=(MetricSample(timestamp=START, value=1),),
    )
    series = tuple(
        item
        for item in (
            metric_series(bucket_name, labels=malformed_bucket_labels),
            metric_series(request_name, labels=missing_label_values, unit="wrong"),
            duplicate,
            duplicate.model_copy(
                update={"labels": {**duplicate.labels, "instance": "other"}}
            ),
            unknown,
        )
    )

    snapshot = builder().build(
        workload(), raw_metrics(series=series), "obs-insufficient"
    )

    assert snapshot.quality_report.status is QualityStatus.INSUFFICIENT
    codes = {item.code for item in snapshot.quality_report.issues}
    assert {
        "malformed_histogram_bound",
        "missing_series_label",
        "normalized_series_collision",
        "unit_mismatch",
        "unknown_metric_family",
        "unreported_missing_metric_family",
    }.issubset(codes)


def test_positive_infinity_histogram_bound_is_valid() -> None:
    bucket_name = "kri_http_request_duration_seconds_bucket"
    labels = _labels(bucket_name)
    labels["le"] = "+Inf"
    series = tuple(
        metric_series(name, labels=labels)
        if name == bucket_name
        else metric_series(name)
        for name in NORMALIZATION_SPECS
    )

    snapshot = builder().build(
        workload(), raw_metrics(series=series), "obs-infinite-bound"
    )

    assert snapshot.quality_report.status is QualityStatus.COMPLETE


def test_no_pods_or_metrics_is_insufficient_without_synthesized_series() -> None:
    snapshot = builder().build(
        workload(pods=()),
        raw_metrics(series=()),
        "obs-empty",
    )

    assert snapshot.normalized_series == ()
    assert snapshot.quality_report.status is QualityStatus.INSUFFICIENT
    codes = {item.code for item in snapshot.quality_report.issues}
    assert {"no_pods", "no_metric_series"}.issubset(codes)


def test_store_saves_loads_inspects_and_replays_immutable_snapshot(
    tmp_path: Path,
) -> None:
    snapshot = builder().build(workload(), raw_metrics(), "obs-stored")
    store = ObservationStore(tmp_path / "observations")

    path = store.save(snapshot)
    loaded = store.load("obs-stored")
    summary = store.inspect("obs-stored")

    assert path == tmp_path / "observations" / "obs-stored.json"
    assert loaded == snapshot
    assert store.replay("obs-stored") == snapshot
    assert summary.quality_status is QualityStatus.COMPLETE
    assert summary.issue_count == 0
    assert summary.normalized_series_count == 10
    assert summary.sample_count == 20
    with pytest.raises(ObservationStoreError, match="already exists"):
        store.save(snapshot)


def test_store_rejects_unsafe_missing_malformed_and_digest_invalid_artifacts(
    tmp_path: Path,
) -> None:
    store = ObservationStore(tmp_path)
    with pytest.raises(ObservationStoreError, match="invalid observation ID"):
        store.load("../unsafe")
    with pytest.raises(ObservationStoreError, match="does not exist"):
        store.load("obs-missing")

    malformed = tmp_path / "obs-malformed.json"
    malformed.write_text("not json", encoding="utf-8")
    with pytest.raises(ObservationStoreError, match="invalid observation artifact"):
        store.load("obs-malformed")

    snapshot = builder().build(workload(), raw_metrics(), "obs-digest")
    payload = snapshot.model_dump(mode="json")
    payload["raw_metrics_snapshot"]["series"][0]["samples"][0]["value"] = 99
    (tmp_path / "obs-digest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ObservationStoreError, match="digest"):
        store.load("obs-digest")


def test_replay_and_save_reject_tampered_normalized_content(tmp_path: Path) -> None:
    snapshot = builder().build(workload(), raw_metrics(), "obs-tampered")
    normalized = list(snapshot.normalized_series)
    normalized[0] = normalized[0].model_copy(update={"unit": "tampered"})
    tampered = snapshot.model_copy(update={"normalized_series": tuple(normalized)})

    with pytest.raises(ObservationError, match="replay"):
        builder().replay(tampered)
    with pytest.raises(ObservationStoreError, match="replay"):
        ObservationStore(tmp_path).save(tampered)

    tampered_path = tmp_path / "obs-tampered.json"
    tampered_path.write_text(tampered.model_dump_json(), encoding="utf-8")
    with pytest.raises(ObservationStoreError, match="replay"):
        ObservationStore(tmp_path).replay("obs-tampered")


def test_replay_rejects_raw_digest_tampering() -> None:
    snapshot = builder().build(workload(), raw_metrics(), "obs-raw-tampered")
    tampered_metrics = snapshot.raw_metrics_snapshot.model_copy(
        update={
            "collected_at": snapshot.raw_metrics_snapshot.collected_at
            + timedelta(seconds=1)
        }
    )
    tampered = snapshot.model_copy(update={"raw_metrics_snapshot": tampered_metrics})

    with pytest.raises(ObservationError, match="digest"):
        builder().replay(tampered)


def test_observation_contract_validation_failures() -> None:
    snapshot = builder().build(workload(), raw_metrics(), "obs-contract")
    with pytest.raises(ValidationError, match="quality status"):
        DataQualityReport(
            status=QualityStatus.COMPLETE,
            expected_metric_families=1,
            observed_metric_families=0,
            issues=(
                QualityIssue(
                    severity=QualitySeverity.WARNING,
                    code="missing",
                    source="prometheus",
                    field="metric",
                    message="missing",
                ),
            ),
        )
    with pytest.raises(ValidationError, match="provenance timestamps"):
        ObservationProvenance(
            workload_schema_version="1.0",
            metrics_schema_version="1.0",
            workload_observed_at=datetime(2026, 1, 1),
            metrics_collected_at=CREATED,
            source_digest_sha256="a" * 64,
        )
    with pytest.raises(ValidationError, match="observation ID"):
        ObservationSnapshot.model_validate(
            {**snapshot.model_dump(), "observation_id": "NOT SAFE"}
        )
    with pytest.raises(ValidationError, match="creation timestamp"):
        ObservationSnapshot.model_validate(
            {**snapshot.model_dump(), "created_at": datetime(2026, 1, 1)}
        )
    mismatched_metrics = snapshot.raw_metrics_snapshot.model_copy(
        update={"identity": identity("different")}
    )
    with pytest.raises(ValidationError, match="identities"):
        ObservationSnapshot.model_validate(
            {**snapshot.model_dump(), "raw_metrics_snapshot": mismatched_metrics}
        )


def test_store_wraps_filesystem_errors(tmp_path: Path) -> None:
    blocking_file = tmp_path / "blocking"
    blocking_file.write_text("file", encoding="utf-8")
    snapshot = builder().build(workload(), raw_metrics(), "obs-write-error")

    with pytest.raises(ObservationStoreError):
        ObservationStore(blocking_file).save(snapshot)

    artifact_directory = tmp_path / "obs-read-error.json"
    artifact_directory.mkdir()
    with pytest.raises(ObservationStoreError, match="invalid observation artifact"):
        ObservationStore(tmp_path).load("obs-read-error")
