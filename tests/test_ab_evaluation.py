"""Offline tests for the saved-artifact A/B report calculations."""

from datetime import UTC, datetime, timedelta

import pytest

from kri.contracts import MetricKind, MetricSample, NormalizedMetricSeries
from scripts.evaluate_ab_experiments import _counter_delta, _relative_delta

NOW = datetime(2026, 11, 2, tzinfo=UTC)


def counter(*values: float) -> NormalizedMetricSeries:
    return NormalizedMetricSeries(
        signal_name="http_requests_total",
        source_metric_name="kri_http_requests_total",
        metric_kind=MetricKind.COUNTER,
        unit="requests",
        aggregation_scope="pod_route_status",
        labels={"route": "/work", "status_code": "200"},
        samples=tuple(
            MetricSample(timestamp=NOW + timedelta(seconds=index * 5), value=value)
            for index, value in enumerate(values)
        ),
    )


def test_ab_report_math_uses_counter_and_relative_differences() -> None:
    assert _counter_delta(counter(10, 15, 24)) == 14
    assert _relative_delta(12.525, 9.03) == pytest.approx(0.3870431894)


def test_ab_report_math_rejects_incomplete_reset_and_zero_baseline() -> None:
    with pytest.raises(ValueError, match="two samples"):
        _counter_delta(counter(10))
    with pytest.raises(ValueError, match="counter reset"):
        _counter_delta(counter(10, 9))
    with pytest.raises(ValueError, match="zero baseline"):
        _relative_delta(1, 0)
