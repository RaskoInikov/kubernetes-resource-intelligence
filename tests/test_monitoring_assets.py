"""Offline validation for disposable Prometheus assets and canonical queries."""

from pathlib import Path
from typing import Any

import pytest
import yaml

MANIFEST = Path("deploy/monitoring/prometheus.yaml")
QUERIES = Path("deploy/monitoring/queries.md")
MANAGED_BY = "kri-monitoring"


def _documents() -> list[dict[str, Any]]:
    return list(yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")))


def test_monitoring_resources_are_owned_bounded_and_hardened() -> None:
    documents = _documents()
    kinds = [document["kind"] for document in documents]

    assert kinds == [
        "Namespace",
        "ServiceAccount",
        "ClusterRole",
        "ClusterRoleBinding",
        "Role",
        "RoleBinding",
        "ConfigMap",
        "Deployment",
        "Service",
    ]
    assert all(
        document["metadata"]["labels"]["app.kubernetes.io/managed-by"] == MANAGED_BY
        for document in documents
    )
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert "--storage.tsdb.retention.time=6h" in container["args"]
    assert container["resources"]["limits"] == {"cpu": "500m", "memory": "512Mi"}
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert pod_spec["volumes"][1]["emptyDir"]["sizeLimit"] == "2Gi"


def test_prometheus_config_collects_only_required_sources() -> None:
    config_map = next(item for item in _documents() if item["kind"] == "ConfigMap")
    config = yaml.safe_load(config_map["data"]["prometheus.yml"])
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    cadvisor = jobs["kubernetes-cadvisor"]
    application = jobs["kri-workload"]
    cadvisor_regex = cadvisor["metric_relabel_configs"][0]["regex"]
    application_regex = application["metric_relabel_configs"][0]["regex"]

    assert config["global"]["scrape_interval"] == "5s"
    assert cadvisor["relabel_configs"][0]["replacement"].endswith("/metrics/cadvisor")
    for metric in [
        "cpu_usage_seconds_total",
        "cpu_cfs_periods_total",
        "cpu_cfs_throttled_periods_total",
        "cpu_cfs_throttled_seconds_total",
        "memory_working_set_bytes",
    ]:
        assert metric in cadvisor_regex
    for metric in [
        "requests_total",
        "request_errors_total",
        "request_duration_seconds_bucket",
        "request_duration_seconds_sum",
        "request_duration_seconds_count",
    ]:
        assert metric in application_regex
    assert application["kubernetes_sd_configs"][0]["namespaces"]["names"] == [
        "payments"
    ]


def test_monitoring_rbac_is_read_only_and_namespace_scoped() -> None:
    documents = _documents()
    cluster_role = next(item for item in documents if item["kind"] == "ClusterRole")
    role = next(item for item in documents if item["kind"] == "Role")

    assert role["metadata"]["namespace"] == "payments"
    assert role["rules"] == [
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]}
    ]
    resources = {
        resource for rule in cluster_role["rules"] for resource in rule["resources"]
    }
    assert resources == {"nodes", "nodes/proxy"}
    assert all(
        verb in {"get", "list", "watch"}
        for rule in cluster_role["rules"]
        for verb in rule["verbs"]
    )


def test_canonical_queries_cover_every_required_signal_without_zero_fill() -> None:
    queries = QUERIES.read_text(encoding="utf-8")

    for metric in [
        "container_cpu_usage_seconds_total",
        "container_cpu_cfs_periods_total",
        "container_cpu_cfs_throttled_periods_total",
        "container_cpu_cfs_throttled_seconds_total",
        "container_memory_working_set_bytes",
        "kri_http_requests_total",
        "kri_http_request_errors_total",
        "kri_http_request_duration_seconds_bucket",
    ]:
        assert metric in queries
    assert "or vector(0)" not in queries


def test_malformed_monitoring_yaml_is_rejected() -> None:
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load("invalid: [")
