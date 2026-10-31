"""Read-only Kubernetes and Prometheus collectors for M3."""

import json
import math
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from kri.contracts import (
    ContainerResources,
    KubernetesEvent,
    MetricSample,
    MetricSeries,
    MissingData,
    PodObservation,
    RawMetricsSnapshot,
    WorkloadIdentity,
    WorkloadSnapshot,
)

APPLICATION_NAME = "kri-workload"
APPLICATION_CONTAINER = "application"
POD_SELECTOR = (
    "app.kubernetes.io/name=kri-workload,app.kubernetes.io/component=application"
)


class CollectorError(RuntimeError):
    """An external source failed or returned an invalid response."""


class KubernetesReader(Protocol):
    """Narrow read-only Kubernetes boundary."""

    context: str
    namespace: str

    def get(
        self,
        resource: str,
        name: str | None = None,
        *,
        label_selector: str | None = None,
    ) -> dict[str, Any]: ...


class KubectlReader:
    """Run only namespaced ``kubectl get`` commands."""

    _RESOURCES = frozenset({"deployment", "pods", "events"})

    def __init__(self, context: str, namespace: str) -> None:
        if not context.strip() or not namespace.strip():
            raise ValueError("Kubernetes context and namespace cannot be empty")
        self.context = context
        self.namespace = namespace

    def get(
        self,
        resource: str,
        name: str | None = None,
        *,
        label_selector: str | None = None,
    ) -> dict[str, Any]:
        if resource not in self._RESOURCES:
            raise ValueError("resource is outside the M3 read-only boundary")
        arguments = [
            "kubectl",
            "--context",
            self.context,
            "--namespace",
            self.namespace,
            "get",
            resource,
        ]
        if name is not None:
            arguments.append(name)
        if label_selector is not None:
            arguments.extend(["--selector", label_selector])
        arguments.extend(["--output", "json"])
        try:
            result = subprocess.run(
                arguments,
                text=True,
                capture_output=True,
                check=True,
            )
            value: object = json.loads(result.stdout)
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
            detail = getattr(error, "stderr", None) or str(error)
            raise CollectorError(str(detail).strip()) from error
        if not isinstance(value, dict):
            raise CollectorError("kubectl returned a non-object JSON response")
        return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CollectorError(f"Kubernetes response field {field!r} is not an object")
    return value


def _items(value: Mapping[str, Any], field: str = "items") -> list[Mapping[str, Any]]:
    raw_items = value.get(field)
    if not isinstance(raw_items, list):
        raise CollectorError(f"Kubernetes response field {field!r} is not a list")
    if not all(isinstance(item, dict) for item in raw_items):
        raise CollectorError(f"Kubernetes response field {field!r} has invalid items")
    return raw_items


def _required_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise CollectorError(f"Kubernetes response is missing {field!r}")
    return item


def _optional_quantity(
    values: Mapping[str, Any],
    key: str,
    field: str,
    missing: list[MissingData],
) -> str | None:
    value = values.get(key)
    if isinstance(value, str) and value:
        return value
    missing.append(MissingData(source="kubernetes", field=field, reason="not reported"))
    return None


class KubernetesCollector:
    """Collect an identity-bound raw workload snapshot from Kubernetes."""

    def __init__(
        self,
        reader: KubernetesReader,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.reader = reader
        self.clock = clock

    def collect(self, deployment_name: str = APPLICATION_NAME) -> WorkloadSnapshot:
        deployment = self.reader.get("deployment", deployment_name)
        pod_list = self.reader.get("pods", label_selector=POD_SELECTOR)
        event_list = self.reader.get("events")
        observed_at = self.clock()
        if observed_at.tzinfo is None:
            raise CollectorError("collector clock returned a naive timestamp")

        metadata = _mapping(deployment.get("metadata"), "metadata")
        uid = _required_string(metadata, "uid")
        resource_version = _required_string(metadata, "resourceVersion")
        actual_name = _required_string(metadata, "name")
        if actual_name != deployment_name:
            raise CollectorError("Kubernetes returned a different Deployment identity")
        identity = WorkloadIdentity(
            cluster=self.reader.context,
            namespace=self.reader.namespace,
            deployment_name=actual_name,
            deployment_uid=uid,
        )

        missing: list[MissingData] = []
        containers = self._containers(deployment, missing)
        pods = self._pods(pod_list, missing)
        if not pods:
            missing.append(
                MissingData(
                    source="kubernetes",
                    field="pods",
                    reason="no matching Pods were reported",
                )
            )
        events = self._events(event_list, identity, pods, missing)
        if not events:
            missing.append(
                MissingData(
                    source="kubernetes",
                    field="events",
                    reason="no related events were reported",
                )
            )
        return WorkloadSnapshot(
            observed_at=observed_at,
            identity=identity,
            deployment_resource_version=resource_version,
            pods=tuple(pods),
            container_resources=tuple(containers),
            events=tuple(events),
            missing_data=tuple(missing),
        )

    def _containers(
        self,
        deployment: Mapping[str, Any],
        missing: list[MissingData],
    ) -> list[ContainerResources]:
        spec = _mapping(deployment.get("spec"), "spec")
        template = _mapping(spec.get("template"), "spec.template")
        pod_spec = _mapping(template.get("spec"), "spec.template.spec")
        raw_containers = pod_spec.get("containers")
        if not isinstance(raw_containers, list) or not raw_containers:
            raise CollectorError("Deployment has no container specifications")
        result: list[ContainerResources] = []
        for raw in raw_containers:
            container = _mapping(raw, "container")
            name = _required_string(container, "name")
            resources = container.get("resources")
            if not isinstance(resources, dict):
                resources = {}
                missing.append(
                    MissingData(
                        source="kubernetes",
                        field=f"containers.{name}.resources",
                        reason="not reported",
                    )
                )
            requests = resources.get("requests", {})
            limits = resources.get("limits", {})
            if not isinstance(requests, dict) or not isinstance(limits, dict):
                raise CollectorError("container resources requests/limits are invalid")
            result.append(
                ContainerResources(
                    container_name=name,
                    cpu_request=_optional_quantity(
                        requests, "cpu", f"containers.{name}.requests.cpu", missing
                    ),
                    cpu_limit=_optional_quantity(
                        limits, "cpu", f"containers.{name}.limits.cpu", missing
                    ),
                    memory_request=_optional_quantity(
                        requests,
                        "memory",
                        f"containers.{name}.requests.memory",
                        missing,
                    ),
                    memory_limit=_optional_quantity(
                        limits, "memory", f"containers.{name}.limits.memory", missing
                    ),
                )
            )
        return result

    def _pods(
        self,
        pod_list: Mapping[str, Any],
        missing: list[MissingData],
    ) -> list[PodObservation]:
        result: list[PodObservation] = []
        for pod in _items(pod_list):
            metadata = _mapping(pod.get("metadata"), "pod.metadata")
            status = _mapping(pod.get("status"), "pod.status")
            statuses = status.get("containerStatuses", [])
            if not isinstance(statuses, list):
                raise CollectorError("Pod containerStatuses is not a list")
            ready: bool | None = None
            restart_count: int | None = None
            for raw_status in statuses:
                item = _mapping(raw_status, "pod.containerStatus")
                if item.get("name") == APPLICATION_CONTAINER:
                    ready = item.get("ready") is True
                    count = item.get("restartCount")
                    if not isinstance(count, int) or count < 0:
                        raise CollectorError("Pod restartCount is invalid")
                    restart_count = count
            pod_name = _required_string(metadata, "name")
            if ready is None:
                missing.append(
                    MissingData(
                        source="kubernetes",
                        field=f"pods.{pod_name}.containerStatuses.application",
                        reason="not reported",
                    )
                )
            result.append(
                PodObservation(
                    name=pod_name,
                    uid=_required_string(metadata, "uid"),
                    ready=ready,
                    restart_count=restart_count,
                )
            )
        return result

    def _events(
        self,
        event_list: Mapping[str, Any],
        identity: WorkloadIdentity,
        pods: Sequence[PodObservation],
        missing: list[MissingData],
    ) -> list[KubernetesEvent]:
        related = {identity.deployment_uid, *(pod.uid for pod in pods)}
        result: list[KubernetesEvent] = []
        for event in _items(event_list):
            involved = _mapping(event.get("involvedObject"), "event.involvedObject")
            if involved.get("uid") not in related:
                continue
            timestamp_value = (
                event.get("eventTime")
                or event.get("lastTimestamp")
                or event.get("firstTimestamp")
            )
            timestamp: datetime | None = None
            if timestamp_value is None:
                name = str(involved.get("name", "unknown"))
                missing.append(
                    MissingData(
                        source="kubernetes",
                        field=f"events.{name}.timestamp",
                        reason="not reported",
                    )
                )
            elif isinstance(timestamp_value, str):
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_value.replace("Z", "+00:00")
                    )
                except ValueError as error:
                    raise CollectorError(
                        "Kubernetes event timestamp is invalid"
                    ) from error
            else:
                raise CollectorError("Kubernetes event timestamp is invalid")
            result.append(
                KubernetesEvent(
                    event_type=_required_string(event, "type"),
                    reason=_required_string(event, "reason"),
                    message=_required_string(event, "message"),
                    involved_kind=_required_string(involved, "kind"),
                    involved_name=_required_string(involved, "name"),
                    timestamp=timestamp,
                )
            )
        return result


PrometheusTransport = Callable[[str], Mapping[str, Any]]


def _http_json(url: str) -> Mapping[str, Any]:
    try:
        with urlopen(url, timeout=15) as response:
            value: object = json.loads(response.read())
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise CollectorError(str(error)) from error
    if not isinstance(value, dict):
        raise CollectorError("Prometheus returned a non-object JSON response")
    return value


METRIC_SPECS: tuple[tuple[str, str, str], ...] = (
    ("container_cpu_usage_seconds_total", "cpu_seconds", "cadvisor"),
    ("container_cpu_cfs_periods_total", "periods", "cadvisor"),
    ("container_cpu_cfs_throttled_periods_total", "periods", "cadvisor"),
    ("container_cpu_cfs_throttled_seconds_total", "seconds", "cadvisor"),
    ("container_memory_working_set_bytes", "bytes", "cadvisor"),
    ("kri_http_requests_total", "requests", "application"),
    ("kri_http_request_errors_total", "errors", "application"),
    ("kri_http_request_duration_seconds_bucket", "observations", "application"),
    ("kri_http_request_duration_seconds_sum", "seconds", "application"),
    ("kri_http_request_duration_seconds_count", "observations", "application"),
)


def _prometheus_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _prometheus_timestamp(value: datetime) -> datetime:
    """Match Prometheus's millisecond precision for range evaluation times."""

    milliseconds = math.floor(value.timestamp() * 1000)
    return datetime.fromtimestamp(milliseconds / 1000, UTC)


class PrometheusCollector:
    """Retrieve raw M2 source series through read-only range queries."""

    def __init__(
        self,
        base_url: str,
        transport: PrometheusTransport = _http_json,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Prometheus URL must be HTTP or HTTPS")
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.clock = clock

    def collect(
        self,
        workload: WorkloadSnapshot,
        interval_start: datetime,
        interval_end: datetime,
        *,
        step_seconds: int = 5,
    ) -> RawMetricsSnapshot:
        if (
            interval_start.tzinfo is None
            or interval_end.tzinfo is None
            or interval_end <= interval_start
        ):
            raise ValueError("metrics interval must be ordered and timezone-aware")
        if step_seconds < 1:
            raise ValueError("Prometheus query step must be positive")
        interval_start = _prometheus_timestamp(interval_start)
        interval_end = _prometheus_timestamp(interval_end)
        if interval_end <= interval_start:
            raise ValueError("metrics interval is shorter than Prometheus precision")
        pod_names = tuple(pod.name for pod in workload.pods)
        if not pod_names:
            missing_without_pods = tuple(
                MissingData(
                    source="prometheus",
                    field=metric,
                    reason="no observed Pods available for an identity-scoped query",
                )
                for metric, _, _ in METRIC_SPECS
            )
            return self._snapshot(
                workload,
                interval_start,
                interval_end,
                (),
                missing_without_pods,
            )

        series: list[MetricSeries] = []
        missing: list[MissingData] = []
        for metric_name, unit, source_kind in METRIC_SPECS:
            selector = self._selector(
                metric_name, source_kind, workload.identity, pod_names
            )
            result = self._query_range(
                selector, interval_start, interval_end, step_seconds
            )
            if not result:
                missing.append(
                    MissingData(
                        source="prometheus",
                        field=metric_name,
                        reason="query returned no series",
                    )
                )
                continue
            series.extend(
                self._parse_series(
                    result,
                    metric_name,
                    unit,
                    workload.identity,
                    pod_names,
                )
            )
        return self._snapshot(
            workload,
            interval_start,
            interval_end,
            tuple(series),
            tuple(missing),
        )

    def _snapshot(
        self,
        workload: WorkloadSnapshot,
        interval_start: datetime,
        interval_end: datetime,
        series: tuple[MetricSeries, ...],
        missing: tuple[MissingData, ...],
    ) -> RawMetricsSnapshot:
        collected_at = self.clock()
        if collected_at.tzinfo is None:
            raise CollectorError("collector clock returned a naive timestamp")
        return RawMetricsSnapshot(
            collected_at=collected_at,
            interval_start=interval_start,
            interval_end=interval_end,
            identity=workload.identity,
            series=series,
            missing_data=missing,
        )

    def _selector(
        self,
        metric_name: str,
        source_kind: str,
        identity: WorkloadIdentity,
        pod_names: Sequence[str],
    ) -> str:
        pod_pattern = "|".join(
            re.escape(name).replace(r"\-", "-") for name in pod_names
        )
        labels = [
            f'namespace="{_prometheus_escape(identity.namespace)}"',
            f'pod=~"{_prometheus_escape(pod_pattern)}"',
        ]
        if source_kind == "cadvisor":
            labels.extend([f'container="{APPLICATION_CONTAINER}"', 'image!=""'])
        else:
            labels.append(f'job="{_prometheus_escape(identity.deployment_name)}"')
        return f"{metric_name}{{{','.join(labels)}}}"

    def _query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> list[Mapping[str, Any]]:
        parameters = urlencode(
            {
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step_seconds,
            }
        )
        response = self.transport(f"{self.base_url}/api/v1/query_range?{parameters}")
        if response.get("status") != "success":
            raise CollectorError("Prometheus query failed")
        data = response.get("data")
        if not isinstance(data, dict) or data.get("resultType") != "matrix":
            raise CollectorError("Prometheus returned an invalid range-query response")
        result = data.get("result")
        if not isinstance(result, list) or not all(
            isinstance(item, dict) for item in result
        ):
            raise CollectorError("Prometheus returned invalid range-query series")
        return result

    def _parse_series(
        self,
        values: Sequence[Mapping[str, Any]],
        expected_metric: str,
        unit: str,
        identity: WorkloadIdentity,
        pod_names: Sequence[str],
    ) -> list[MetricSeries]:
        result: list[MetricSeries] = []
        for value in values:
            raw_labels = value.get("metric")
            raw_samples = value.get("values")
            if not isinstance(raw_labels, dict) or not all(
                isinstance(key, str) and isinstance(item, str)
                for key, item in raw_labels.items()
            ):
                raise CollectorError("Prometheus returned invalid series labels")
            labels = dict(raw_labels)
            if labels.get("__name__", expected_metric) != expected_metric:
                raise CollectorError("Prometheus returned a different metric identity")
            if labels.get("namespace") != identity.namespace:
                raise CollectorError(
                    "Prometheus returned a different namespace identity"
                )
            if labels.get("pod") not in pod_names:
                raise CollectorError("Prometheus returned an unknown Pod identity")
            if expected_metric.startswith("kri_") and (
                labels.get("job") != identity.deployment_name
            ):
                raise CollectorError(
                    "Prometheus returned a different workload identity"
                )
            if not isinstance(raw_samples, list) or not raw_samples:
                raise CollectorError("Prometheus returned a series without samples")
            samples: list[MetricSample] = []
            for raw_sample in raw_samples:
                if not isinstance(raw_sample, list) or len(raw_sample) != 2:
                    raise CollectorError("Prometheus returned an invalid sample")
                try:
                    timestamp = float(raw_sample[0])
                    sample_value = float(raw_sample[1])
                except (TypeError, ValueError) as error:
                    raise CollectorError(
                        "Prometheus returned a non-numeric sample"
                    ) from error
                if not math.isfinite(timestamp) or not math.isfinite(sample_value):
                    raise CollectorError("Prometheus returned a non-finite sample")
                samples.append(
                    MetricSample(
                        timestamp=datetime.fromtimestamp(timestamp, UTC),
                        value=sample_value,
                    )
                )
            result.append(
                MetricSeries(
                    metric_name=expected_metric,
                    labels=labels,
                    unit=unit,
                    samples=tuple(samples),
                )
            )
        return result
