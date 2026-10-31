"""Capture and validate real M3 collector snapshots for one observation window."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from kri.collectors import (
    APPLICATION_NAME,
    METRIC_SPECS,
    KubectlReader,
    KubernetesCollector,
    PrometheusCollector,
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-missing-metric", action="append", default=[])
    arguments = parser.parse_args()

    workload = KubernetesCollector(
        KubectlReader(arguments.context, arguments.namespace)
    ).collect(APPLICATION_NAME)
    metrics = PrometheusCollector(arguments.prometheus_url).collect(
        workload,
        arguments.start,
        arguments.end,
    )

    if workload.identity.cluster != arguments.context:
        raise RuntimeError("Kubernetes snapshot has the wrong cluster identity")
    if workload.identity.namespace != arguments.namespace:
        raise RuntimeError("Kubernetes snapshot has the wrong namespace identity")
    if len(workload.pods) != 2 or any(
        pod.ready is not True or pod.restart_count != 0 for pod in workload.pods
    ):
        raise RuntimeError("expected two ready Pods with zero restarts")
    application = next(
        (
            item
            for item in workload.container_resources
            if item.container_name == "application"
        ),
        None,
    )
    if application is None or application.model_dump() != {
        "container_name": "application",
        "cpu_request": "50m",
        "cpu_limit": "100m",
        "memory_request": "64Mi",
        "memory_limit": "192Mi",
    }:
        raise RuntimeError("application resources differ from the approved values")

    expected = {name for name, _, _ in METRIC_SPECS}
    expected_missing = set(arguments.expect_missing_metric)
    actual = {item.metric_name for item in metrics.series}
    actual_missing = {item.field for item in metrics.missing_data}
    if actual != expected - expected_missing:
        raise RuntimeError(f"unexpected collected metric families: {sorted(actual)}")
    if actual_missing != expected_missing:
        raise RuntimeError(
            f"unexpected missing metric families: {sorted(actual_missing)}"
        )
    if metrics.identity != workload.identity:
        raise RuntimeError("collector snapshots do not share workload identity")

    artifact = {
        "schema_version": "1.0",
        "kind": "m3_real_service_verification",
        "workload_snapshot": workload.model_dump(mode="json"),
        "raw_metrics_snapshot": metrics.model_dump(mode="json"),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "deployment_uid": workload.identity.deployment_uid,
                "deployment_resource_version": workload.deployment_resource_version,
                "pods": [pod.name for pod in workload.pods],
                "events": len(workload.events),
                "kubernetes_missing": [item.field for item in workload.missing_data],
                "metric_families": sorted(actual),
                "metric_series": len(metrics.series),
                "metric_samples": sum(len(series.samples) for series in metrics.series),
                "prometheus_missing": sorted(actual_missing),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
