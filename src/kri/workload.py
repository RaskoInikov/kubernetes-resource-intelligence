"""Safe manifest rendering and lifecycle control for M1 workloads."""

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from kri.contracts import (
    EXPERIMENT_ID_PATTERN,
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    TerminationSource,
    WorkloadConfiguration,
)

APPLICATION_NAME = "kri-workload"
MANAGED_LABELS = {
    "app.kubernetes.io/name": APPLICATION_NAME,
    "app.kubernetes.io/managed-by": "kri-workload-controller",
}
DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")


def _kubernetes_timestamp(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise KubernetesCommandError(f"Job {field} is not a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise KubernetesCommandError(f"Job {field} is not a valid timestamp") from error
    if parsed.tzinfo is None:
        raise KubernetesCommandError(f"Job {field} has no timezone")
    return parsed.astimezone(UTC)


def _optional_status_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise KubernetesCommandError(f"Job condition {field} is not text")
    return value if value.strip() else None


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
        except KubernetesCommandError as error:
            self._finish(
                record,
                ExperimentState.FAILED,
                end_timestamp=self.clock(),
                reason="SubmissionFailed",
                message=str(error) or None,
                source=TerminationSource.CONTROLLER,
            )
            raise
        return record

    def stop_load(self, experiment_id: str) -> ExperimentRecord:
        record = self.store.load(experiment_id)
        if record.lifecycle_state is not ExperimentState.RUNNING:
            self.kubernetes.delete("job", f"kri-load-{experiment_id}")
            return record
        record = self.sync_load(experiment_id)
        if record.lifecycle_state is not ExperimentState.RUNNING:
            self.kubernetes.delete("job", f"kri-load-{experiment_id}")
            return record
        self.kubernetes.delete("job", f"kri-load-{experiment_id}")
        return self._finish(
            record,
            ExperimentState.STOPPED,
            end_timestamp=self.clock(),
            reason="UserStopped",
            message="Load Job deleted by an explicit stop request.",
            source=TerminationSource.CONTROLLER,
        )

    def sync_load(self, experiment_id: str) -> ExperimentRecord:
        record = self.store.load(experiment_id)
        if record.lifecycle_state is not ExperimentState.RUNNING:
            return record
        job = self.kubernetes.get("job", f"kri-load-{experiment_id}")
        status = job.get("status", {})
        if not isinstance(status, dict):
            raise KubernetesCommandError("Job status is not an object")
        metadata = job.get("metadata", {})
        if not isinstance(metadata, dict):
            raise KubernetesCommandError("Job metadata is not an object")
        uid = metadata.get("uid")
        if uid is not None and not isinstance(uid, str):
            raise KubernetesCommandError("Job UID is not text")
        if record.job_uid is not None and uid is not None and record.job_uid != uid:
            raise KubernetesCommandError("Job UID does not match experiment record")
        start_timestamp = _kubernetes_timestamp(status.get("startTime"), "startTime")
        conditions = status.get("conditions", [])
        if not isinstance(conditions, list):
            raise KubernetesCommandError("Job conditions are not a list")
        terminal: list[tuple[ExperimentState, dict[str, Any]]] = []
        for condition in conditions:
            if not isinstance(condition, dict):
                raise KubernetesCommandError("Job condition is not an object")
            if condition.get("status") != "True":
                continue
            condition_type = condition.get("type")
            if condition_type == "Complete":
                terminal.append((ExperimentState.SUCCEEDED, condition))
            elif condition_type == "Failed":
                terminal.append((ExperimentState.FAILED, condition))
        if len(terminal) > 1:
            raise KubernetesCommandError("Job has conflicting terminal conditions")

        updates = {
            "schema_version": "1.1",
            "job_uid": uid or record.job_uid,
            "job_start_timestamp": start_timestamp or record.job_start_timestamp,
        }
        if terminal:
            state, condition = terminal[0]
            if uid is None or start_timestamp is None:
                raise KubernetesCommandError(
                    "terminal Job has no UID or start timestamp"
                )
            condition_timestamp = _kubernetes_timestamp(
                condition.get("lastTransitionTime"),
                "condition.lastTransitionTime",
            )
            completion_timestamp = _kubernetes_timestamp(
                status.get("completionTime"), "completionTime"
            )
            end_timestamp = (
                completion_timestamp
                if state is ExperimentState.SUCCEEDED
                else condition_timestamp
            ) or condition_timestamp
            if end_timestamp is None:
                return self._save_running_metadata(record, updates)
            default_reason = (
                "Complete" if state is ExperimentState.SUCCEEDED else "Failed"
            )
            return self._finish(
                record,
                state,
                end_timestamp=end_timestamp,
                reason=_optional_status_text(condition.get("reason"), "reason")
                or default_reason,
                message=_optional_status_text(condition.get("message"), "message"),
                source=TerminationSource.KUBERNETES,
                updates=updates,
            )
        return self._save_running_metadata(record, updates)

    def _save_running_metadata(
        self,
        record: ExperimentRecord,
        updates: Mapping[str, object],
    ) -> ExperimentRecord:
        reconciled = ExperimentRecord.model_validate({**record.model_dump(), **updates})
        if reconciled != record:
            self.store.save(reconciled)
        return reconciled

    def _finish(
        self,
        record: ExperimentRecord,
        state: ExperimentState,
        *,
        end_timestamp: datetime,
        reason: str,
        message: str | None,
        source: TerminationSource,
        updates: Mapping[str, object] | None = None,
    ) -> ExperimentRecord:
        finished = ExperimentRecord.model_validate(
            {
                **record.model_dump(),
                **(updates or {}),
                "schema_version": "1.1",
                "end_timestamp": end_timestamp,
                "lifecycle_state": state,
                "termination_reason": reason,
                "termination_message": message,
                "termination_source": source,
            }
        )
        self.store.save(finished)
        return finished
