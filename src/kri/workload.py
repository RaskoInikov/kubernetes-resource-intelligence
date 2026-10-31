"""Safe manifest rendering and lifecycle control for M1 workloads."""

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from kri.contracts import (
    EXPERIMENT_ID_PATTERN,
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    WorkloadConfiguration,
)

APPLICATION_NAME = "kri-workload"
MANAGED_LABELS = {
    "app.kubernetes.io/name": APPLICATION_NAME,
    "app.kubernetes.io/managed-by": "kri-workload-controller",
}
DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")


class WorkloadError(RuntimeError):
    """Base error for workload lifecycle operations."""


class KubernetesCommandError(WorkloadError):
    """A scoped kubectl operation failed."""


class ExperimentStoreError(WorkloadError):
    """An experiment record could not be safely persisted."""


def _validate_reference(kind: str, name: str) -> None:
    fixed = {("deployment", APPLICATION_NAME), ("service", APPLICATION_NAME)}
    if (kind, name) in fixed:
        return
    if kind == "job" and name.startswith("kri-load-"):
        experiment_id = name.removeprefix("kri-load-")
        if EXPERIMENT_ID_PATTERN.fullmatch(experiment_id) is not None:
            return
    raise ValueError("resource is outside the M1 workload-controller boundary")


def _validate_resource(resource: dict[str, Any]) -> None:
    kind = resource.get("kind")
    metadata = resource.get("metadata")
    if not isinstance(kind, str) or not isinstance(metadata, dict):
        raise ValueError("resource kind and metadata are required")
    name = metadata.get("name")
    labels = metadata.get("labels")
    if not isinstance(name, str) or not isinstance(labels, dict):
        raise ValueError("resource name and labels are required")
    if "namespace" in metadata:
        raise ValueError("resource manifests cannot override the configured namespace")
    if (
        labels.get("app.kubernetes.io/managed-by")
        != MANAGED_LABELS["app.kubernetes.io/managed-by"]
    ):
        raise ValueError("resource is missing the controller ownership label")
    _validate_reference(kind.lower(), name)


class KubernetesClient(Protocol):
    """Narrow mutation/query boundary used by the controller."""

    def apply(self, resources: Sequence[dict[str, Any]]) -> None: ...

    def delete(self, kind: str, name: str) -> None: ...

    def get(self, kind: str, name: str) -> dict[str, Any]: ...


class KubectlClient:
    """Invoke kubectl with an explicit context and namespace on every call."""

    def __init__(self, context: str, namespace: str) -> None:
        if not context.strip():
            raise ValueError("Kubernetes context cannot be empty")
        if DNS_LABEL_PATTERN.fullmatch(namespace) is None:
            raise ValueError("Kubernetes namespace must be a DNS label")
        self._prefix = ["kubectl", "--context", context, "--namespace", namespace]

    def _run(self, arguments: Sequence[str], stdin: str | None = None) -> str:
        try:
            result = subprocess.run(
                [*self._prefix, *arguments],
                input=stdin,
                text=True,
                capture_output=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", None) or str(error)
            raise KubernetesCommandError(detail.strip()) from error
        return result.stdout

    def apply(self, resources: Sequence[dict[str, Any]]) -> None:
        for resource in resources:
            _validate_resource(resource)
        payload = {"apiVersion": "v1", "kind": "List", "items": list(resources)}
        self._run(["apply", "--filename", "-"], json.dumps(payload))

    def delete(self, kind: str, name: str) -> None:
        _validate_reference(kind, name)
        self._run(["delete", kind, name, "--ignore-not-found=true"])

    def get(self, kind: str, name: str) -> dict[str, Any]:
        _validate_reference(kind, name)
        output = self._run(["get", kind, name, "--output", "json"])
        value: object = json.loads(output)
        if not isinstance(value, dict):
            raise KubernetesCommandError("kubectl returned a non-object JSON response")
        return value


class ExperimentStore:
    """Versioned JSON artifact store with atomic record replacement."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, experiment_id: str) -> Path:
        if EXPERIMENT_ID_PATTERN.fullmatch(experiment_id) is None:
            raise ExperimentStoreError("invalid experiment ID")
        return self.directory / f"{experiment_id}.json"

    def create(self, record: ExperimentRecord) -> None:
        path = self._path(record.experiment_id)
        if path.exists():
            raise ExperimentStoreError(
                f"experiment already exists: {record.experiment_id}"
            )
        self._write(path, record)

    def save(self, record: ExperimentRecord) -> None:
        path = self._path(record.experiment_id)
        if not path.exists():
            raise ExperimentStoreError(
                f"experiment does not exist: {record.experiment_id}"
            )
        self._write(path, record)

    def load(self, experiment_id: str) -> ExperimentRecord:
        path = self._path(experiment_id)
        try:
            return ExperimentRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise ExperimentStoreError(
                f"experiment does not exist: {experiment_id}"
            ) from error

    def _write(self, path: Path, record: ExperimentRecord) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                record.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as error:
            raise ExperimentStoreError(str(error)) from error


def application_resources(
    configuration: WorkloadConfiguration,
    image: str,
) -> list[dict[str, Any]]:
    """Render the fixed-name disposable application resources."""

    resources = {
        "requests": {
            "cpu": configuration.cpu_request,
            "memory": configuration.memory_request,
        },
        "limits": {
            "cpu": configuration.cpu_limit,
            "memory": configuration.memory_limit,
        },
    }
    pod_labels = {**MANAGED_LABELS, "app.kubernetes.io/component": "application"}
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": APPLICATION_NAME, "labels": MANAGED_LABELS},
        "spec": {
            "replicas": configuration.replicas,
            "selector": {"matchLabels": {"app.kubernetes.io/name": APPLICATION_NAME}},
            "template": {
                "metadata": {
                    "labels": pod_labels,
                    "annotations": {
                        "prometheus.io/scrape": "true",
                        "prometheus.io/path": "/metrics",
                        "prometheus.io/port": "8080",
                    },
                },
                "spec": {
                    "automountServiceAccountToken": False,
                    "containers": [
                        {
                            "name": "application",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python", "-m", "kri_workload.app"],
                            "ports": [{"name": "http", "containerPort": 8080}],
                            "resources": resources,
                            "readinessProbe": {
                                "httpGet": {"path": "/healthz", "port": "http"},
                                "initialDelaySeconds": 1,
                                "periodSeconds": 2,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/healthz", "port": "http"},
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "runAsNonRoot": True,
                                "readOnlyRootFilesystem": True,
                            },
                        }
                    ],
                    "securityContext": {"runAsUser": 65532, "runAsGroup": 65532},
                },
            },
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": APPLICATION_NAME, "labels": MANAGED_LABELS},
        "spec": {
            "selector": {"app.kubernetes.io/name": APPLICATION_NAME},
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
    }
    return [deployment, service]


def load_job_resource(
    experiment_id: str,
    configuration: LoadConfiguration,
    image: str,
) -> dict[str, Any]:
    """Render one independently disposable load Job."""

    if EXPERIMENT_ID_PATTERN.fullmatch(experiment_id) is None:
        raise ValueError("invalid experiment ID")
    name = f"kri-load-{experiment_id}"
    labels = {
        **MANAGED_LABELS,
        "app.kubernetes.io/component": "load-generator",
        "kri.io/experiment-id": experiment_id,
    }
    environment = [
        {"name": "TARGET_URL", "value": f"http://{APPLICATION_NAME}:8080/work"},
        {"name": "WORKLOAD_MODE", "value": configuration.workload_mode.value},
        {"name": "CONCURRENCY", "value": str(configuration.concurrency)},
        {"name": "REQUEST_RATE", "value": str(configuration.request_rate)},
        {"name": "DURATION_SECONDS", "value": str(configuration.duration_seconds)},
    ]
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": configuration.duration_seconds + 60,
            "ttlSecondsAfterFinished": 300,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "automountServiceAccountToken": False,
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "load-generator",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python", "-m", "kri_workload.load"],
                            "env": environment,
                            "resources": {
                                "requests": {"cpu": "25m", "memory": "32Mi"},
                                "limits": {"cpu": "500m", "memory": "128Mi"},
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "runAsNonRoot": True,
                                "readOnlyRootFilesystem": True,
                            },
                        }
                    ],
                    "securityContext": {"runAsUser": 65532, "runAsGroup": 65532},
                },
            },
        },
    }


class WorkloadController:
    """Coordinate application and independent load lifecycles."""

    def __init__(
        self,
        kubernetes: KubernetesClient,
        store: ExperimentStore,
        image: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not image.strip():
            raise ValueError("workload image cannot be empty")
        self.kubernetes = kubernetes
        self.store = store
        self.image = image
        self.clock = clock

    def deploy_application(self, configuration: WorkloadConfiguration) -> None:
        self.kubernetes.apply(application_resources(configuration, self.image))

    def delete_application(self) -> None:
        self.kubernetes.delete("service", APPLICATION_NAME)
        self.kubernetes.delete("deployment", APPLICATION_NAME)

    def start_load(
        self,
        workload: WorkloadConfiguration,
        load: LoadConfiguration,
        experiment_id: str | None = None,
    ) -> ExperimentRecord:
        identifier = experiment_id or f"exp-{uuid4().hex[:12]}"
        record = ExperimentRecord(
            experiment_id=identifier,
            workload_configuration=workload,
            load_configuration=load,
            start_timestamp=self.clock(),
            lifecycle_state=ExperimentState.RUNNING,
        )
        self.store.create(record)
        try:
            self.kubernetes.apply([load_job_resource(identifier, load, self.image)])
        except KubernetesCommandError:
            self._finish(record, ExperimentState.FAILED)
            raise
        return record

    def stop_load(self, experiment_id: str) -> ExperimentRecord:
        record = self.store.load(experiment_id)
        if record.lifecycle_state is not ExperimentState.RUNNING:
            raise WorkloadError(f"experiment is already {record.lifecycle_state.value}")
        self.kubernetes.delete("job", f"kri-load-{experiment_id}")
        return self._finish(record, ExperimentState.STOPPED)

    def sync_load(self, experiment_id: str) -> ExperimentRecord:
        record = self.store.load(experiment_id)
        if record.lifecycle_state is not ExperimentState.RUNNING:
            return record
        job = self.kubernetes.get("job", f"kri-load-{experiment_id}")
        status = job.get("status", {})
        if not isinstance(status, dict):
            raise KubernetesCommandError("Job status is not an object")
        if status.get("succeeded", 0):
            return self._finish(record, ExperimentState.SUCCEEDED)
        if status.get("failed", 0) and not status.get("active", 0):
            return self._finish(record, ExperimentState.FAILED)
        return record

    def _finish(
        self,
        record: ExperimentRecord,
        state: ExperimentState,
    ) -> ExperimentRecord:
        finished = ExperimentRecord.model_validate(
            {
                **record.model_dump(),
                "end_timestamp": self.clock(),
                "lifecycle_state": state,
            }
        )
        self.store.save(finished)
        return finished
