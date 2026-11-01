"""Offline tests for deterministic M5 resource analysis."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from kri.analysis import (
    AnalysisError,
    DeterministicAnalyzer,
    _counter_summary,
    _cpu_millicores,
    _memory_bytes,
    _percentile,
)
from kri.contracts import (
    AnalysisEvidence,
    AnalysisReport,
    AnalysisSufficiency,
    ConditionSeverity,
    ContainerResources,
    MetricKind,
    MetricSample,
    MetricSeries,
    MissingData,
    NormalizedMetricSeries,
    ObservationSnapshot,
    PodObservation,
    RawMetricsSnapshot,
    WorkloadIdentity,
    WorkloadSnapshot,
)
from kri.observations import NORMALIZATION_SPECS, ObservationBuilder, ObservationStore

START = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
END = START + timedelta(seconds=10)
CREATED = END + timedelta(seconds=1)


def identity() -> WorkloadIdentity:
    return WorkloadIdentity(
        cluster="kind-test",
        namespace="payments",
        deployment_name="kri-workload",
        deployment_uid="deployment-uid",
    )


def workload(
    resources: tuple[ContainerResources, ...] | None = None,
) -> WorkloadSnapshot:
    if resources is None:
        resources = (
            ContainerResources(
                container_name="application",
                cpu_request="100m",
                cpu_limit="200m",
                memory_request="64Mi",
                memory_limit="128Mi",
            ),
        )
    return WorkloadSnapshot(
        observed_at=END,
        identity=identity(),
        deployment_resource_version="42",
        pods=(
            PodObservation(
                name="kri-workload-abc",
                uid="pod-uid",
                ready=True,
                restart_count=0,
            ),
        ),
        container_resources=resources,
        events=(),
    )


def labels(metric_name: str) -> dict[str, str]:
    result = {
        "__name__": metric_name,
        "namespace": "payments",
        "pod": "kri-workload-abc",
    }
    if metric_name.startswith("container_"):
        result["container"] = "application"
    else:
        result.update(method="GET", route="/work", job="kri-workload")
    if metric_name == "kri_http_requests_total":
        result["status_code"] = "200"
    if metric_name == "kri_http_request_errors_total":
        result["status_code"] = "500"
    return result


def series(
    metric_name: str,
    values: tuple[float, ...],
    *,
    extra_labels: dict[str, str] | None = None,
) -> MetricSeries:
    metric_labels = labels(metric_name)
    metric_labels.update(extra_labels or {})
    return MetricSeries(
        metric_name=metric_name,
        labels=metric_labels,
        unit=NORMALIZATION_SPECS[metric_name].expected_unit,
        samples=tuple(
            MetricSample(timestamp=START + timedelta(seconds=index * 5), value=value)
            for index, value in enumerate(values)
        ),
    )


def complete_series() -> tuple[MetricSeries, ...]:
    mib = 1024 * 1024
    return (
        series("container_cpu_usage_seconds_total", (0, 1, 2)),
        series("container_cpu_cfs_periods_total", (0, 100, 200)),
        series("container_cpu_cfs_throttled_periods_total", (0, 20, 40)),
        series("container_cpu_cfs_throttled_seconds_total", (0, 0.5, 1)),
        series(
            "container_memory_working_set_bytes",
            (100 * mib, 120 * mib, 124 * mib),
        ),
        series("kri_http_requests_total", (0, 50, 100)),
        series("kri_http_request_errors_total", (0, 5, 10)),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 20, 40),
            extra_labels={"le": "0.1"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 45, 90),
            extra_labels={"le": "0.5"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 50, 100),
            extra_labels={"le": "+Inf"},
        ),
        series("kri_http_request_duration_seconds_sum", (0, 20, 40)),
        series("kri_http_request_duration_seconds_count", (0, 50, 100)),
    )


def observation(
    *,
    metric_series: tuple[MetricSeries, ...] | None = None,
    missing: tuple[MissingData, ...] = (),
    resources: tuple[ContainerResources, ...] | None = None,
    observation_id: str = "obs-analysis",
) -> ObservationSnapshot:
    values = complete_series() if metric_series is None else metric_series
    raw = RawMetricsSnapshot(
        collected_at=CREATED,
        interval_start=START,
        interval_end=END,
        identity=identity(),
        series=values,
        missing_data=missing,
    )
    return ObservationBuilder(clock=lambda: CREATED).build(
        workload(resources), raw, observation_id
    )


def analyzer() -> DeterministicAnalyzer:
    return DeterministicAnalyzer(clock=lambda: CREATED + timedelta(seconds=1))


def statistic(report: AnalysisReport, name: str) -> float:
    return next(item.value for item in report.statistics if item.name == name)


def test_analysis_calculates_statistics_conditions_and_bounded_recommendations() -> (
    None
):
    report = analyzer().analyze(observation(), "analysis-complete")

    assert report.sufficiency is AnalysisSufficiency.SUFFICIENT
    assert statistic(report, "cpu_average_cores") == pytest.approx(0.2)
    assert statistic(report, "cpu_peak_cores") == pytest.approx(0.2)
    assert statistic(report, "cpu_throttle_period_ratio") == pytest.approx(0.2)
    assert statistic(report, "cpu_throttled_seconds_per_second") == pytest.approx(0.1)
    assert statistic(report, "cpu_request_utilization_average_ratio") == pytest.approx(
        2.0
    )
    assert statistic(report, "cpu_limit_utilization_peak_ratio") == pytest.approx(1.0)
    assert statistic(report, "memory_max_working_set_bytes") == 124 * 1024 * 1024
    assert statistic(report, "http_requests_per_second") == pytest.approx(10)
    assert statistic(report, "http_error_ratio") == pytest.approx(0.1)
    assert statistic(report, "http_latency_mean_seconds") == pytest.approx(0.4)
    assert statistic(report, "http_latency_p95_seconds") == pytest.approx(0.5)

    assert {item.condition_type for item in report.conditions} == {
        "cpu_throttling_high",
        "cpu_limit_saturation",
        "memory_limit_pressure",
        "cpu_request_low",
        "memory_request_low",
    }
    severities = {item.condition_type: item.severity for item in report.conditions}
    assert severities["cpu_throttling_high"] is ConditionSeverity.WARNING
    assert severities["memory_limit_pressure"] is ConditionSeverity.WARNING
    assert severities["cpu_limit_saturation"] is ConditionSeverity.CRITICAL
    recommendations = {item.resource: item for item in report.recommendations}
    assert recommendations["cpu_limit"].recommended_value == "250m"
    assert recommendations["cpu_request"].recommended_value == "200m"
    assert recommendations["memory_limit"].recommended_value == "160Mi"
    assert recommendations["memory_request"].recommended_value == "128Mi"
    assert all(item.requires_approval for item in report.recommendations)
    assert recommendations["cpu_limit"].upper_bound == "400m"
    assert recommendations["memory_limit"].upper_bound == "256Mi"
    assert "below the 25% headroom target" in recommendations["cpu_request"].rationale
    assert any(
        "CPU request headroom target" in risk for risk in report.risks_and_uncertainties
    )

    evidence_ids = {item.evidence_id for item in report.evidence}
    statistic_ids = {item.statistic_id for item in report.statistics}
    condition_ids = {item.condition_id for item in report.conditions}
    for stat_item in report.statistics:
        assert set(stat_item.evidence_ids) <= evidence_ids
    for condition_item in report.conditions:
        assert set(condition_item.evidence_ids) <= evidence_ids
        assert set(condition_item.statistic_ids) <= statistic_ids
    for recommendation_item in report.recommendations:
        assert set(recommendation_item.evidence_ids) <= evidence_ids
        assert set(recommendation_item.statistic_ids) <= statistic_ids
        assert set(recommendation_item.condition_ids) <= condition_ids


def test_thresholds_are_inclusive_and_warning_below_critical_ratio() -> None:
    values = list(complete_series())
    memory_index = next(
        index
        for index, item in enumerate(values)
        if item.metric_name == "container_memory_working_set_bytes"
    )
    values[memory_index] = series(
        "container_memory_working_set_bytes",
        (64 * 1024 * 1024, 90 * 1024 * 1024, 115.2 * 1024 * 1024),
    )
    report = analyzer().analyze(
        observation(metric_series=tuple(values)), "analysis-boundary"
    )

    memory_condition = next(
        item
        for item in report.conditions
        if item.condition_type == "memory_limit_pressure"
    )
    assert memory_condition.observed_value == pytest.approx(0.9)
    assert memory_condition.severity is ConditionSeverity.WARNING


def test_degraded_observation_is_partial_and_preserves_missing_uncertainty() -> None:
    error_name = "kri_http_request_errors_total"
    values = tuple(item for item in complete_series() if item.metric_name != error_name)
    report = analyzer().analyze(
        observation(
            metric_series=values,
            missing=(
                MissingData(
                    source="prometheus",
                    field=error_name,
                    reason="query returned no series",
                ),
            ),
        ),
        "analysis-partial",
    )

    assert report.sufficiency is AnalysisSufficiency.PARTIAL
    assert "http_error_ratio" not in {item.name for item in report.statistics}
    assert any(
        "missing_metric_family" in risk for risk in report.risks_and_uncertainties
    )
    assert report.recommendations


def test_insufficient_observation_suppresses_conditions_and_recommendations() -> None:
    report = analyzer().analyze(observation(metric_series=()), "analysis-insufficient")

    assert report.sufficiency is AnalysisSufficiency.INSUFFICIENT
    assert report.conditions == ()
    assert report.recommendations == ()
    assert any("suppressed" in risk for risk in report.risks_and_uncertainties)


def test_counter_reset_suppresses_dependent_cpu_calculations() -> None:
    values = tuple(
        series(item.metric_name, (0, 2, 1))
        if item.metric_name == "container_cpu_usage_seconds_total"
        else item
        for item in complete_series()
    )
    report = analyzer().analyze(observation(metric_series=values), "analysis-reset")

    assert report.sufficiency is AnalysisSufficiency.PARTIAL
    assert "cpu_average_cores" not in {item.name for item in report.statistics}
    assert not {
        "cpu_limit_saturation",
        "cpu_request_low",
    }.intersection(item.condition_type for item in report.conditions)
    assert any("counter_reset" in risk for risk in report.risks_and_uncertainties)


def test_saved_observation_analysis_is_deterministic(tmp_path: Path) -> None:
    snapshot = observation(observation_id="obs-saved-analysis")
    store = ObservationStore(tmp_path)
    store.save(snapshot)

    first = analyzer().analyze_saved(store, snapshot.observation_id, "analysis-saved")
    second = analyzer().analyze(snapshot, "analysis-saved")

    assert first == second
    assert first.provenance.observation_source_digest_sha256 == (
        snapshot.provenance.source_digest_sha256
    )


def test_saved_observation_analysis_reports_store_failures(tmp_path: Path) -> None:
    store = ObservationStore(tmp_path)

    with pytest.raises(AnalysisError, match="does not exist"):
        analyzer().analyze_saved(store, "obs-missing", "analysis-missing")


def test_analyzer_rejects_tampered_observation_and_naive_clock() -> None:
    snapshot = observation()
    tampered = snapshot.model_copy(update={"normalized_series": ()})
    with pytest.raises(AnalysisError, match="replay"):
        analyzer().analyze(tampered, "analysis-tampered")
    with pytest.raises(AnalysisError, match="naive"):
        DeterministicAnalyzer(clock=lambda: datetime(2026, 1, 1)).analyze(
            snapshot, "analysis-naive"
        )


def test_invalid_or_missing_resources_are_risks_not_fabricated_recommendations() -> (
    None
):
    invalid = (
        ContainerResources(
            container_name="application",
            cpu_request="invalid",
            cpu_limit=None,
            memory_request="invalid",
            memory_limit=None,
        ),
    )
    report = analyzer().analyze(
        observation(resources=invalid), "analysis-invalid-resources"
    )

    assert not report.recommendations
    assert any("invalid CPU" in risk for risk in report.risks_and_uncertainties)
    assert any(
        "cpu_limit is missing" in risk for risk in report.risks_and_uncertainties
    )
    assert any("invalid memory" in risk for risk in report.risks_and_uncertainties)

    missing = analyzer().analyze(
        observation(resources=()), "analysis-missing-resources"
    )
    assert not missing.recommendations
    assert any("not observed" in risk for risk in missing.risks_and_uncertainties)


def test_analysis_contract_rejects_bad_references_and_duplicates() -> None:
    report = analyzer().analyze(observation(), "analysis-contract")
    payload = report.model_dump()
    payload["statistics"][0]["evidence_ids"] = ("unknown",)
    with pytest.raises(ValidationError, match="statistic references"):
        AnalysisReport.model_validate(payload)

    payload = report.model_dump()
    payload["conditions"][0]["statistic_ids"] = ("unknown",)
    with pytest.raises(ValidationError, match="condition references"):
        AnalysisReport.model_validate(payload)

    payload = report.model_dump()
    payload["recommendations"][0]["condition_ids"] = ("unknown",)
    with pytest.raises(ValidationError, match="recommendation references"):
        AnalysisReport.model_validate(payload)

    payload = report.model_dump()
    payload["evidence"] = (*payload["evidence"], payload["evidence"][0])
    with pytest.raises(ValidationError, match="duplicate evidence"):
        AnalysisReport.model_validate(payload)

    for field, message in (
        ("statistics", "duplicate statistic"),
        ("conditions", "duplicate condition"),
        ("recommendations", "duplicate recommendation"),
    ):
        payload = report.model_dump()
        payload[field] = (*payload[field], payload[field][0])
        with pytest.raises(ValidationError, match=message):
            AnalysisReport.model_validate(payload)

    payload = report.model_dump()
    payload["sufficiency"] = "insufficient"
    with pytest.raises(ValidationError, match="cannot contain recommendations"):
        AnalysisReport.model_validate(payload)


def test_analysis_contract_rejects_invalid_ids_time_and_evidence_intervals() -> None:
    report = analyzer().analyze(observation(), "analysis-valid")
    with pytest.raises(ValidationError, match="lowercase DNS"):
        AnalysisReport.model_validate({**report.model_dump(), "analysis_id": "BAD"})
    with pytest.raises(ValidationError, match="timezone"):
        AnalysisReport.model_validate(
            {**report.model_dump(), "created_at": datetime(2026, 1, 1)}
        )

    evidence = next(item for item in report.evidence if item.interval_start is not None)
    with pytest.raises(ValidationError, match="both boundaries"):
        type(evidence).model_validate({**evidence.model_dump(), "interval_end": None})

    for start, end in (
        (START.replace(tzinfo=None), END),
        (START, END.replace(tzinfo=None)),
        (END, START),
    ):
        with pytest.raises(ValidationError, match=r"timezone|follow"):
            AnalysisEvidence.model_validate(
                {
                    **evidence.model_dump(),
                    "interval_start": start,
                    "interval_end": end,
                }
            )


def test_quantity_percentile_and_short_counter_edge_cases() -> None:
    with pytest.raises(ValueError, match="CPU"):
        _cpu_millicores("0")
    with pytest.raises(ValueError, match="memory"):
        _memory_bytes("0Mi")
    with pytest.raises(ValueError, match="requires values"):
        _percentile((), 0.95)
    assert _percentile((7.0,), 0.95) == 7.0

    short = NormalizedMetricSeries.model_construct(
        signal_name="cpu_usage_seconds_total",
        source_metric_name="container_cpu_usage_seconds_total",
        labels={"pod": "pod", "container": "application"},
        unit="seconds",
        metric_kind=MetricKind.COUNTER,
        aggregation_scope="pod_container",
        samples=(),
    )
    assert _counter_summary(short) is None

    repeated = NormalizedMetricSeries(
        signal_name="cpu_usage_seconds_total",
        source_metric_name="container_cpu_usage_seconds_total",
        labels={"pod": "pod", "container": "application"},
        unit="seconds",
        metric_kind=MetricKind.COUNTER,
        aggregation_scope="pod_container",
        samples=tuple(
            MetricSample(timestamp=START + timedelta(seconds=index * 5), value=value)
            for index, value in enumerate((0.0, 1.0, 1.0, 1.0, 2.5))
        ),
    )
    summary = _counter_summary(repeated)
    assert summary is not None
    assert summary[2] == pytest.approx(0.1)
    assert summary[3] is True

    one_update = repeated.model_copy(
        update={"samples": repeated.samples[:3]},
    )
    one_update_summary = _counter_summary(one_update)
    assert one_update_summary is not None
    assert one_update_summary[2] == pytest.approx(0.1)


def test_repeated_cpu_evaluations_report_peak_resolution_risk() -> None:
    values = tuple(
        series(item.metric_name, (0, 1, 1))
        if item.metric_name == "container_cpu_usage_seconds_total"
        else item
        for item in complete_series()
    )
    report = analyzer().analyze(
        observation(metric_series=values), "analysis-cpu-resolution"
    )

    assert statistic(report, "cpu_peak_cores") == pytest.approx(0.1)
    assert any(
        "limited by scrape cadence" in risk for risk in report.risks_and_uncertainties
    )


def test_unconstrained_cpu_request_recommendation_reaches_headroom_target() -> None:
    resources = (
        ContainerResources(
            container_name="application",
            cpu_request="100m",
            cpu_limit="500m",
            memory_request="64Mi",
            memory_limit="128Mi",
        ),
    )
    values = tuple(
        series(item.metric_name, (0, 0.75, 1.5))
        if item.metric_name == "container_cpu_usage_seconds_total"
        else item
        for item in complete_series()
    )
    report = analyzer().analyze(
        observation(resources=resources, metric_series=values),
        "analysis-unconstrained-request",
    )
    recommendation = next(
        item for item in report.recommendations if item.resource == "cpu_request"
    )

    assert recommendation.recommended_value == "190m"
    assert "with 25% headroom" in recommendation.rationale
    assert not any(
        "CPU request headroom target" in risk for risk in report.risks_and_uncertainties
    )


def test_partial_resource_series_and_unusable_optional_counters_are_bounded() -> None:
    cpu_only = tuple(
        item
        for item in complete_series()
        if item.metric_name != "container_memory_working_set_bytes"
        and item.metric_name
        not in {
            "container_cpu_cfs_periods_total",
            "container_cpu_cfs_throttled_periods_total",
            "container_cpu_cfs_throttled_seconds_total",
        }
    )
    cpu_report = analyzer().analyze(
        observation(metric_series=cpu_only), "analysis-cpu-only"
    )
    assert "cpu_average_cores" in {item.name for item in cpu_report.statistics}
    assert "memory_max_working_set_bytes" not in {
        item.name for item in cpu_report.statistics
    }

    memory_only = tuple(
        item
        for item in complete_series()
        if not item.metric_name.startswith("container_cpu")
    )
    memory_report = analyzer().analyze(
        observation(metric_series=memory_only), "analysis-memory-only"
    )
    assert "memory_max_working_set_bytes" in {
        item.name for item in memory_report.statistics
    }
    assert "cpu_average_cores" not in {item.name for item in memory_report.statistics}

    reset_names = {
        "container_cpu_cfs_periods_total",
        "container_cpu_cfs_throttled_periods_total",
        "container_cpu_cfs_throttled_seconds_total",
        "kri_http_requests_total",
    }
    reset_values = tuple(
        series(item.metric_name, (0, 2, 1), extra_labels={"le": item.labels["le"]})
        if item.metric_name in reset_names and "le" in item.labels
        else series(item.metric_name, (0, 2, 1))
        if item.metric_name in reset_names
        else item
        for item in complete_series()
    )
    reset_report = analyzer().analyze(
        observation(metric_series=reset_values), "analysis-optional-resets"
    )
    names = {item.name for item in reset_report.statistics}
    assert "cpu_throttle_period_ratio" not in names
    assert "cpu_throttled_seconds_per_second" not in names
    assert "http_requests_per_second" not in names
    assert any(
        "HTTP request counters" in risk for risk in reset_report.risks_and_uncertainties
    )


def test_only_duplicate_resource_scopes_report_suppression_risk() -> None:
    values = (
        *complete_series(),
        series(
            "container_cpu_usage_seconds_total",
            (0, 1, 2),
            extra_labels={"instance": "duplicate"},
        ),
    )
    report = analyzer().analyze(
        observation(metric_series=values), "analysis-resource-duplicate"
    )

    duplicate_risks = [
        risk for risk in report.risks_and_uncertainties if "Duplicate" in risk
    ]
    assert len(duplicate_risks) == 1
    assert "cpu_usage_seconds_total" in duplicate_risks[0]


def test_histogram_ignores_unusable_buckets_and_handles_terminal_and_plateau() -> None:
    base = tuple(
        item
        for item in complete_series()
        if item.metric_name != "kri_http_request_duration_seconds_bucket"
    )
    malformed = (
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 10, 20),
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 10, 20),
            extra_labels={"le": "not-a-bound"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 2, 1),
            extra_labels={"le": "0.1"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 40, 90),
            extra_labels={"le": "0.5"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 50, 100),
            extra_labels={"le": "+Inf"},
        ),
    )
    report = analyzer().analyze(
        observation(metric_series=(*base, *malformed)), "analysis-hist-terminal"
    )
    assert statistic(report, "http_latency_p95_seconds") == pytest.approx(0.5)

    plateau = (
        *(
            item
            for item in complete_series()
            if item.metric_name != "kri_http_request_duration_seconds_bucket"
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 50, 100),
            extra_labels={"le": "0.1"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 50, 100),
            extra_labels={"le": "0.5"},
        ),
        series(
            "kri_http_request_duration_seconds_bucket",
            (0, 50, 100),
            extra_labels={"le": "+Inf"},
        ),
    )
    plateau_report = analyzer().analyze(
        observation(metric_series=plateau), "analysis-hist-plateau"
    )
    assert statistic(plateau_report, "http_latency_p95_seconds") == pytest.approx(0.095)


def test_recommendations_respect_configured_limit_and_reject_invalid_quantities() -> (
    None
):
    capped_resources = (
        ContainerResources(
            container_name="application",
            cpu_request="200m",
            cpu_limit="200m",
            memory_request="128Mi",
            memory_limit="128Mi",
        ),
    )
    capped_values = tuple(
        series(item.metric_name, (0, 1.25, 2.5))
        if item.metric_name == "container_cpu_usage_seconds_total"
        else series(
            item.metric_name,
            (150 * 1024 * 1024, 155 * 1024 * 1024, 160 * 1024 * 1024),
        )
        if item.metric_name == "container_memory_working_set_bytes"
        else item
        for item in complete_series()
    )
    report = analyzer().analyze(
        observation(resources=capped_resources, metric_series=capped_values),
        "analysis-capped",
    )
    assert {item.resource for item in report.recommendations} == {
        "cpu_limit",
        "memory_limit",
    }

    condition = report.conditions[0]
    stats = {item.statistic_id: item for item in report.statistics}
    engine = analyzer()
    assert (
        engine._cpu_recommendation(
            "cpu_limit", "invalid", None, 100, [condition], stats, {}
        )
        is None
    )
    assert (
        engine._memory_recommendation(
            "memory_limit", "invalid", None, 1, [condition], stats, {}
        )
        is None
    )
    assert (
        engine._cpu_recommendation(
            "cpu_request", "100m", "100m", 200, [condition], stats, {}
        )
        is None
    )
    assert (
        engine._memory_recommendation(
            "memory_request", "64Mi", "64Mi", 128 * 1024 * 1024, [condition], stats, {}
        )
        is None
    )
    condition_ids, statistic_ids, evidence_ids = engine._recommendation_refs(
        [condition], stats, None
    )
    assert condition_ids and statistic_ids and evidence_ids


def test_recommendation_orchestration_safely_skips_rejected_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = analyzer().analyze(observation(), "analysis-rejection-source")
    resources = workload().container_resources[0]
    resource_evidence = analyzer()._resource_evidence(resources)

    cpu_rejecting = analyzer()
    monkeypatch.setattr(cpu_rejecting, "_cpu_recommendation", lambda *args: None)
    cpu_result = cpu_rejecting._recommendations(
        list(report.conditions),
        list(report.statistics),
        resources,
        resource_evidence,
        [],
    )
    assert not {"cpu_limit", "cpu_request"}.intersection(
        item.resource for item in cpu_result
    )

    memory_rejecting = analyzer()
    monkeypatch.setattr(memory_rejecting, "_memory_recommendation", lambda *args: None)
    memory_result = memory_rejecting._recommendations(
        list(report.conditions),
        list(report.statistics),
        resources,
        resource_evidence,
        [],
    )
    assert not {"memory_limit", "memory_request"}.intersection(
        item.resource for item in memory_result
    )
