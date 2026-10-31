"""Offline tests for M1 Kubernetes resource and lifecycle boundaries."""

import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from kri.contracts import (
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    WorkloadConfiguration,
    WorkloadMode,
)
from kri.workload import (
    APPLICATION_NAME,
    ExperimentStore,
    ExperimentStoreError,
    KubectlClient,
    KubernetesCommandError,
    WorkloadController,
    WorkloadError,
    application_resources,
    load_job_resource,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def workload() -> WorkloadConfiguration:
    return WorkloadConfiguration(
        cpu_request="100m",
        cpu_limit="500m",
        memory_request="64Mi",
        memory_limit="256Mi",
        replicas=2,
    )


def load() -> LoadConfiguration:
    return LoadConfiguration(
        workload_mode=WorkloadMode.CPU,
        concurrency=3,
        request_rate=12.5,
        duration_seconds=20,
    )


class FakeKubernetes:
    def __init__(self) -> None:
        self.applied: list[list[dict[str, Any]]] = []
        self.deleted: list[tuple[str, str]] = []
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.apply_error: KubernetesCommandError | None = None

    def apply(self, resources: Sequence[dict[str, Any]]) -> None:
        if self.apply_error is not None:
            raise self.apply_error
        self.applied.append(list(resources))

    def delete(self, kind: str, name: str) -> None:
        self.deleted.append((kind, name))

    def get(self, kind: str, name: str) -> dict[str, Any]:
        return self.objects[(kind, name)]


def test_application_resources_are_scoped_and_hardened() -> None:
    deployment, service = application_resources(workload(), "kri:test")
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    assert deployment["metadata"]["name"] == APPLICATION_NAME
    assert deployment["spec"]["replicas"] == 2
    assert container["resources"] == {
        "requests": {"cpu": "100m", "memory": "64Mi"},
        "limits": {"cpu": "500m", "memory": "256Mi"},
    }
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert (
        deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
    )
    assert service["kind"] == "Service"
    assert "namespace" not in deployment["metadata"]


def test_load_job_is_independent_and_bounded() -> None:
    job = load_job_resource("exp-test-1", load(), "kri:test")
    spec = job["spec"]
    container = spec["template"]["spec"]["containers"][0]
    environment = {item["name"]: item["value"] for item in container["env"]}

    assert job["metadata"]["name"] == "kri-load-exp-test-1"
    assert spec["activeDeadlineSeconds"] == 80
    assert environment["WORKLOAD_MODE"] == "cpu"
    assert environment["REQUEST_RATE"] == "12.5"
    assert spec["template"]["spec"]["restartPolicy"] == "Never"
    assert all(item["kind"] != "Deployment" for item in [job])

    with pytest.raises(ValueError, match="invalid experiment ID"):
        load_job_resource("BAD", load(), "kri:test")


def test_kubectl_client_always_scopes_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs.get("input")))
        output = '{"status":{"succeeded":1}}' if "get" in command else "ok"
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    client = KubectlClient("kind-test", "payments")
    client.apply(application_resources(workload(), "kri:test"))
    client.delete("job", "kri-load-exp-test")
    result = client.get("job", "kri-load-exp-test")

    assert result["status"]["succeeded"] == 1
    assert len(calls) == 3
    assert all(
        command[:5] == ["kubectl", "--context", "kind-test", "--namespace", "payments"]
        for command, _ in calls
    )
    assert json.loads(calls[0][1] or "{}")["kind"] == "List"


def test_kubectl_client_rejects_resources_outside_boundary() -> None:
    client = KubectlClient("kind-test", "payments")
    with pytest.raises(ValueError, match="outside"):
        client.delete("namespace", "payments")
    with pytest.raises(ValueError, match="outside"):
        client.delete("job", "kri-load-BAD")
    with pytest.raises(ValueError, match="outside"):
        client.apply(
            [
                {
                    "kind": "ConfigMap",
                    "metadata": {
                        "name": "unsafe",
                        "labels": {
                            "app.kubernetes.io/managed-by": "kri-workload-controller"
                        },
                    },
                }
            ]
        )
    with pytest.raises(ValueError, match="override"):
        resource = application_resources(workload(), "kri:test")[0]
        resource["metadata"]["namespace"] = "other"
        client.apply([resource])
    with pytest.raises(ValueError, match="kind and metadata"):
        client.apply([{}])
    with pytest.raises(ValueError, match="name and labels"):
        client.apply([{"kind": "Service", "metadata": {}}])
    with pytest.raises(ValueError, match="ownership"):
        client.apply(
            [{"kind": "Service", "metadata": {"name": APPLICATION_NAME, "labels": {}}}]
        )


@pytest.mark.parametrize(("context", "namespace"), [("", "safe"), ("kind", "BAD_NAME")])
def test_kubectl_client_rejects_unsafe_target(context: str, namespace: str) -> None:
    with pytest.raises(ValueError):
        KubectlClient(context, namespace)


def test_kubectl_failures_are_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "kubectl", stderr="denied")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(KubernetesCommandError, match="denied"):
        KubectlClient("kind-test", "payments").delete("job", "kri-load-exp-safe")

    def missing(*args: object, **kwargs: object) -> None:
        raise OSError("missing kubectl")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(KubernetesCommandError, match="missing kubectl"):
        KubectlClient("kind-test", "payments").delete("job", "kri-load-exp-safe")


def test_kubectl_rejects_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "[]", ""),
    )
    with pytest.raises(KubernetesCommandError, match="non-object"):
        KubectlClient("kind-test", "payments").get("job", "kri-load-exp-safe")


def test_experiment_store_round_trip_and_guards(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    record = ExperimentRecord(
        experiment_id="exp-test-1",
        workload_configuration=workload(),
        load_configuration=load(),
        start_timestamp=NOW,
        lifecycle_state=ExperimentState.RUNNING,
    )
    store.create(record)

    assert store.load("exp-test-1") == record
    assert (
        json.loads((store.directory / "exp-test-1.json").read_text())["schema_version"]
        == "1.0"
    )
    with pytest.raises(ExperimentStoreError, match="already exists"):
        store.create(record)
    with pytest.raises(ExperimentStoreError, match="invalid experiment ID"):
        store.load("../unsafe")
    with pytest.raises(ExperimentStoreError, match="does not exist"):
        store.load("exp-missing")
    with pytest.raises(ExperimentStoreError, match="does not exist"):
        store.save(record.model_copy(update={"experiment_id": "exp-other"}))


def test_experiment_store_wraps_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = ExperimentRecord(
        experiment_id="exp-write",
        workload_configuration=workload(),
        load_configuration=load(),
        start_timestamp=NOW,
        lifecycle_state=ExperimentState.RUNNING,
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "write_text", fail)
    with pytest.raises(ExperimentStoreError, match="disk unavailable"):
        ExperimentStore(tmp_path).create(record)


def test_controller_keeps_application_and_load_lifecycles_independent(
    tmp_path: Path,
) -> None:
    kubernetes = FakeKubernetes()
    store = ExperimentStore(tmp_path)
    controller = WorkloadController(kubernetes, store, "kri:test", clock=lambda: NOW)

    controller.deploy_application(workload())
    record = controller.start_load(workload(), load(), "exp-test-1")
    stopped = controller.stop_load("exp-test-1")
    controller.delete_application()

    assert [resource["kind"] for resource in kubernetes.applied[0]] == [
        "Deployment",
        "Service",
    ]
    assert [resource["kind"] for resource in kubernetes.applied[1]] == ["Job"]
    assert record.lifecycle_state is ExperimentState.RUNNING
    assert stopped.lifecycle_state is ExperimentState.STOPPED
    assert stopped.end_timestamp == NOW
    assert kubernetes.deleted == [
        ("job", "kri-load-exp-test-1"),
        ("service", APPLICATION_NAME),
        ("deployment", APPLICATION_NAME),
    ]


def test_controller_records_apply_failure(tmp_path: Path) -> None:
    kubernetes = FakeKubernetes()
    kubernetes.apply_error = KubernetesCommandError("denied")
    store = ExperimentStore(tmp_path)
    controller = WorkloadController(kubernetes, store, "kri:test", clock=lambda: NOW)

    with pytest.raises(KubernetesCommandError, match="denied"):
        controller.start_load(workload(), load(), "exp-failed")

    assert store.load("exp-failed").lifecycle_state is ExperimentState.FAILED


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"succeeded": 1}, ExperimentState.SUCCEEDED),
        ({"failed": 1}, ExperimentState.FAILED),
        ({"failed": 1, "active": 1}, ExperimentState.RUNNING),
        ({}, ExperimentState.RUNNING),
    ],
)
def test_controller_syncs_job_state(
    tmp_path: Path,
    status: dict[str, int],
    expected: ExperimentState,
) -> None:
    kubernetes = FakeKubernetes()
    store = ExperimentStore(tmp_path)
    controller = WorkloadController(
        kubernetes,
        store,
        "kri:test",
        clock=lambda: NOW + timedelta(seconds=30),
    )
    record = ExperimentRecord(
        experiment_id="exp-sync",
        workload_configuration=workload(),
        load_configuration=load(),
        start_timestamp=NOW,
        lifecycle_state=ExperimentState.RUNNING,
    )
    store.create(record)
    kubernetes.objects[("job", "kri-load-exp-sync")] = {"status": status}

    synced = controller.sync_load("exp-sync")

    assert synced.lifecycle_state is expected
    if expected is ExperimentState.RUNNING:
        assert synced.end_timestamp is None
    else:
        assert synced.end_timestamp is not None


def test_controller_rejects_invalid_or_terminal_operations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="image"):
        WorkloadController(FakeKubernetes(), ExperimentStore(tmp_path), " ")

    kubernetes = FakeKubernetes()
    store = ExperimentStore(tmp_path)
    controller = WorkloadController(kubernetes, store, "kri:test", clock=lambda: NOW)
    running = controller.start_load(workload(), load(), "exp-terminal")
    stopped = controller.stop_load(running.experiment_id)
    with pytest.raises(WorkloadError, match="already stopped"):
        controller.stop_load(stopped.experiment_id)
    assert controller.sync_load(stopped.experiment_id) == stopped

    store.create(
        running.model_copy(
            update={"experiment_id": "exp-bad-status"},
        )
    )
    kubernetes.objects[("job", "kri-load-exp-bad-status")] = {"status": []}
    with pytest.raises(KubernetesCommandError, match="status is not an object"):
        controller.sync_load("exp-bad-status")
