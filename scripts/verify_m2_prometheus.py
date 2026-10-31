"""Capture and validate real M2 Prometheus samples for an experiment interval."""

import argparse
import json
import math
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SELECTORS = {
    "cpu_usage": (
        'container_cpu_usage_seconds_total{namespace="payments",'
        'pod=~"kri-workload-.*",container="application"}'
    ),
    "cpu_periods": (
        'container_cpu_cfs_periods_total{namespace="payments",'
        'pod=~"kri-workload-.*",container="application"}'
    ),
    "cpu_throttled_periods": (
        'container_cpu_cfs_throttled_periods_total{namespace="payments",'
        'pod=~"kri-workload-.*",container="application"}'
    ),
    "cpu_throttled_seconds": (
        'container_cpu_cfs_throttled_seconds_total{namespace="payments",'
        'pod=~"kri-workload-.*",container="application"}'
    ),
    "memory_working_set": (
        'container_memory_working_set_bytes{namespace="payments",'
        'pod=~"kri-workload-.*",container="application"}'
    ),
    "http_requests": ('kri_http_requests_total{namespace="payments",route="/work"}'),
    "http_errors": (
        'kri_http_request_errors_total{namespace="payments",route="/work"}'
    ),
    "http_latency_bucket": (
        'kri_http_request_duration_seconds_bucket{namespace="payments",route="/work"}'
    ),
    "http_latency_sum": (
        'kri_http_request_duration_seconds_sum{namespace="payments",route="/work"}'
    ),
    "http_latency_count": (
        'kri_http_request_duration_seconds_count{namespace="payments",route="/work"}'
    ),
}

DERIVED_QUERIES = {
    "cpu_cores": f"sum(rate({SELECTORS['cpu_usage']}[1m]))",
    "throttled_seconds_per_second": (
        f"sum(rate({SELECTORS['cpu_throttled_seconds']}[1m]))"
    ),
    "throttled_period_ratio": (
        f"sum(rate({SELECTORS['cpu_throttled_periods']}[1m]))"
        f" / sum(rate({SELECTORS['cpu_periods']}[1m]))"
    ),
    "memory_working_set_bytes": f"sum({SELECTORS['memory_working_set']})",
    "http_requests_per_second": f"sum(rate({SELECTORS['http_requests']}[1m]))",
    "http_error_total": f"sum({SELECTORS['http_errors']})",
    "http_latency_p95_seconds": (
        "histogram_quantile(0.95, sum by(le) "
        f"(rate({SELECTORS['http_latency_bucket']}[1m])))"
    ),
}


def _request(base_url: str, path: str, parameters: dict[str, str]) -> dict[str, Any]:
    url = f"{base_url}{path}?{urllib.parse.urlencode(parameters)}"
    with urllib.request.urlopen(url, timeout=10) as response:
        payload: dict[str, Any] = json.load(response)
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("experiment timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _series_delta(result: list[dict[str, Any]]) -> float:
    return sum(
        float(series["values"][-1][1]) - float(series["values"][0][1])
        for series in result
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:19090")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    record = json.loads(arguments.record.read_text(encoding="utf-8"))
    started = _parse_utc(record["start_timestamp"])
    ended = _parse_utc(record["end_timestamp"])
    collected = datetime.now(UTC)
    range_results: dict[str, Any] = {}
    freshness: dict[str, float] = {}

    for name, selector in SELECTORS.items():
        response = _request(
            arguments.base_url,
            "/api/v1/query_range",
            {
                "query": selector,
                "start": str(started.timestamp()),
                "end": str(ended.timestamp()),
                "step": "5",
            },
        )
        result = response["data"]["result"]
        if not result or any(not series["values"] for series in result):
            raise RuntimeError(f"missing samples for {name}")
        for series in result:
            timestamps = [float(sample[0]) for sample in series["values"]]
            if timestamps != sorted(set(timestamps)):
                raise RuntimeError(f"timestamps are not strictly increasing for {name}")
            if (
                timestamps[0] < started.timestamp()
                or timestamps[-1] > ended.timestamp()
            ):
                raise RuntimeError(f"sample outside experiment interval for {name}")
        range_results[name] = response["data"]

        timestamp_response = _request(
            arguments.base_url,
            "/api/v1/query",
            {"query": f"max(timestamp({selector}))"},
        )
        timestamp_result = timestamp_response["data"]["result"]
        if not timestamp_result:
            raise RuntimeError(f"missing source timestamp for {name}")
        source_timestamp = float(timestamp_result[0]["value"][1])
        age = collected.timestamp() - source_timestamp
        if not 0 <= age <= 15:
            raise RuntimeError(f"stale source samples for {name}: {age:.3f}s")
        freshness[name] = age

    for name in [
        "cpu_usage",
        "cpu_periods",
        "cpu_throttled_periods",
        "cpu_throttled_seconds",
        "http_requests",
        "http_latency_count",
    ]:
        result = range_results[name]["result"]
        if _series_delta(result) <= 0:
            raise RuntimeError(f"counter did not increase for {name}")

    memory_values = [
        float(sample[1])
        for series in range_results["memory_working_set"]["result"]
        for sample in series["values"]
    ]
    if not memory_values or min(memory_values) <= 0:
        raise RuntimeError("memory working set was not positive")

    error_series = range_results["http_errors"]["result"]
    error_total = sum(float(series["values"][-1][1]) for series in error_series)
    if error_total < 5:
        raise RuntimeError("controlled HTTP errors were not collected")

    derived: dict[str, Any] = {}
    for name, query in DERIVED_QUERIES.items():
        response = _request(arguments.base_url, "/api/v1/query", {"query": query})
        result = response["data"]["result"]
        if not result:
            raise RuntimeError(f"missing derived result for {name}")
        value = float(result[0]["value"][1])
        if not math.isfinite(value) or value < 0:
            raise RuntimeError(f"invalid derived result for {name}: {value}")
        derived[name] = {"timestamp": result[0]["value"][0], "value": value}

    artifact = {
        "schema_version": "1.0",
        "kind": "m2_real_service_verification",
        "prometheus_base_url": arguments.base_url,
        "experiment_id": record["experiment_id"],
        "experiment_start_timestamp": record["start_timestamp"],
        "experiment_end_timestamp": record["end_timestamp"],
        "collected_at": collected.isoformat().replace("+00:00", "Z"),
        "source_sample_age_seconds": freshness,
        "derived_results": derived,
        "range_results": range_results,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value["value"] for key, value in derived.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
