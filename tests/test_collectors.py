"""Offline tests for read-only M3 collectors."""

import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from kri.collectors import (
    METRIC_SPECS,
    POD_SELECTOR,
    CollectorError,
    KubectlReader,
    KubernetesCollector,
    PrometheusCollector,
    _http_json,
)
from kri.contracts import (
    KubernetesEvent,
    MetricSample,
    MetricSeries,
    MissingData,
    PodObservation,
    RawMetricsSnapshot,
    WorkloadIdentity,
    WorkloadSnapshot,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def deployment() -> dict[str, Any]:
    return {
        "metadata": {
            "name": "kri-workload",
            "uid": "deployment-uid",
            "resourceVersion": "42",
        },
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "application",
                            "resources": {
                                "requests": {"cpu": "50m", "memory": "64Mi"},
                                "limits": {"cpu": "100m", "memory": "192Mi"},
                            },
                        }
                    ]
                }
            }
        },
    }


def pods() -> dict[str, Any]:
    return {
        "items": [
            {
                "metadata": {"name": "kri-workload-abc", "uid": "pod-uid"},
                "status": {
                    "containerStatuses": [
                        {"name": "sidecar", "ready": True, "restartCount": 0},
                        {
                            "name": "application",
                            "ready": True,
                            "restartCount": 2,
                        },
                    ]
                },
            }
        ]
    }


def events() -> dict[str, Any]:
    return {
        "items": [
            {
                "type": "Normal",
                "reason": "Started",
                "message": "Container started",
                "lastTimestamp": "2026-10-31T11:59:00Z",
                "involvedObject": {
                    "kind": "Pod",
                    "name": "kri-workload-abc",
                    "uid": "pod-uid",
                },
            },
            {
                "type": "Normal",
                "reason": "Unrelated",
                "message": "Ignored",
                "eventTime": "2026-10-31T11:59:30+00:00",
                "involvedObject": {
                    "kind": "Pod",
                    "name": "other",
                    "uid": "other-uid",
                },
            },
        ]
    }


class FakeReader:
    context = "kind-test"
    namespace = "payments"

    def __init__(
        self,
        deployment_value: dict[str, Any] | None = None,
        pod_value: dict[str, Any] | None = None,
        event_value: dict[str, Any] | None = None,
    ) -> None:
        self.values = {
            "deployment": deployment_value or deployment(),
            "pods": pod_value or pods(),
            "events": event_value or events(),
        }
        self.calls: list[tuple[str, str | None, str | None]] = []

    def get(
        self,
        resource: str,
        name: str | None = None,
        *,
        label_selector: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((resource, name, label_selector))
        return self.values[resource]


def workload_snapshot(*, with_pods: bool = True) -> WorkloadSnapshot:
    observed_pods = (
        (
            PodObservation(
                name="kri-workload-abc",
                uid="pod-uid",
                ready=True,
                restart_count=0,
            ),
        )
        if with_pods
        else ()
    )
    return WorkloadSnapshot(
        observed_at=NOW,
        identity=WorkloadIdentity(
            cluster="kind-test",
            namespace="payments",
            deployment_name="kri-workload",
            deployment_uid="deployment-uid",
        ),
        deployment_resource_version="42",
        pods=observed_pods,
        container_resources=(),
        events=(),
    )


def test_kubernetes_collector_preserves_identity_resources_state_and_events() -> None:
    reader = FakeReader()

    snapshot = KubernetesCollector(reader, clock=lambda: NOW).collect()

    assert snapshot.observed_at == NOW
    assert snapshot.identity.deployment_uid == "deployment-uid"
    assert snapshot.deployment_resource_version == "42"
    assert snapshot.pods[0].model_dump() == {
        "name": "kri-workload-abc",
        "uid": "pod-uid",
        "ready": True,
        "restart_count": 2,
    }
    assert snapshot.container_resources[0].cpu_limit == "100m"
    assert snapshot.events[0].timestamp == NOW - timedelta(minutes=1)
    assert snapshot.missing_data == ()
    assert reader.calls == [
        ("deployment", "kri-workload", None),
        ("pods", None, POD_SELECTOR),
        ("events", None, None),
    ]


def test_kubernetes_collector_reports_missing_optional_data() -> None:
    value = deployment()
    value["spec"]["template"]["spec"]["containers"][0]["resources"] = {"requests": {}}
    related_without_time = {
        "items": [
            {
                "type": "Warning",
                "reason": "NoTime",
                "message": "Timestamp absent",
                "involvedObject": {
                    "kind": "Deployment",
                    "name": "kri-workload",
                    "uid": "deployment-uid",
                },
            }
        ]
    }
    reader = FakeReader(value, {"items": []}, related_without_time)

    snapshot = KubernetesCollector(reader, clock=lambda: NOW).collect()

    assert snapshot.pods == ()
    assert snapshot.events[0].timestamp is None
    fields = {item.field for item in snapshot.missing_data}
    assert fields == {
        "containers.application.requests.cpu",
        "containers.application.limits.cpu",
        "containers.application.requests.memory",
        "containers.application.limits.memory",
        "pods",
        "events.kri-workload.timestamp",
    }


def test_kubernetes_collector_reports_absent_resources_and_events() -> None:
    value = deployment()
    del value["spec"]["template"]["spec"]["containers"][0]["resources"]

    snapshot = KubernetesCollector(
        FakeReader(value, event_value={"items": []}), clock=lambda: NOW
    ).collect()

    fields = {item.field for item in snapshot.missing_data}
    assert "containers.application.resources" in fields
    assert "events" in fields


def test_kubernetes_collector_does_not_invent_absent_container_status() -> None:
    pod_value = {
        "items": [
            {
                "metadata": {"name": "kri-workload-abc", "uid": "pod-uid"},
                "status": {"containerStatuses": []},
            }
        ]
    }

    snapshot = KubernetesCollector(
        FakeReader(pod_value=pod_value), clock=lambda: NOW
    ).collect()

    assert snapshot.pods[0].ready is None
    assert snapshot.pods[0].restart_count is None
    assert "pods.kri-workload-abc.containerStatuses.application" in {
        item.field for item in snapshot.missing_data
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(metadata=[]), "metadata"),
        (lambda value: value["metadata"].update(uid=""), "uid"),
        (
            lambda value: value["metadata"].update(name="different"),
            "different Deployment",
        ),
        (lambda value: value.update(spec=[]), "spec"),
        (
            lambda value: value["spec"]["template"]["spec"].update(containers=[]),
            "no container",
        ),
        (
            lambda value: value["spec"]["template"]["spec"]["containers"][0].update(
                resources={"requests": [], "limits": {}}
            ),
            "requests/limits",
        ),
    ],
)
def test_kubernetes_collector_rejects_malformed_deployment(
    mutate: Any, message: str
) -> None:
    value = deployment()
    mutate(value)

    with pytest.raises(CollectorError, match=message):
        KubernetesCollector(FakeReader(value), clock=lambda: NOW).collect()


@pytest.mark.parametrize(
    "pod_value",
    [
        {"items": "bad"},
        {"items": ["bad"]},
        {"items": [{"metadata": {}, "status": []}]},
        {
            "items": [
                {
                    "metadata": {"name": "pod", "uid": "uid"},
                    "status": {"containerStatuses": {}},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {"name": "pod", "uid": "uid"},
                    "status": {"containerStatuses": ["bad"]},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {"name": "pod", "uid": "uid"},
                    "status": {
                        "containerStatuses": [
                            {
                                "name": "application",
                                "ready": False,
                                "restartCount": -1,
                            }
                        ]
                    },
                }
            ]
        },
    ],
)
def test_kubernetes_collector_rejects_malformed_pods(
    pod_value: dict[str, Any],
) -> None:
    with pytest.raises(CollectorError):
        KubernetesCollector(
            FakeReader(pod_value=pod_value), clock=lambda: NOW
        ).collect()


@pytest.mark.parametrize("timestamp", [17, "not-a-date"])
def test_kubernetes_collector_rejects_invalid_event_timestamp(
    timestamp: object,
) -> None:
    value = events()
    value["items"][0]["lastTimestamp"] = timestamp
    with pytest.raises(CollectorError, match="timestamp"):
        KubernetesCollector(FakeReader(event_value=value), clock=lambda: NOW).collect()


def test_kubernetes_collector_rejects_naive_clock() -> None:
    with pytest.raises(CollectorError, match="naive"):
        KubernetesCollector(FakeReader(), clock=lambda: datetime(2026, 1, 1)).collect()


def test_kubectl_reader_builds_only_explicit_read_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout='{"items": []}')

    monkeypatch.setattr(subprocess, "run", run)
    reader = KubectlReader("kind-test", "payments")

    assert reader.get("pods", label_selector="app=test") == {"items": []}
    assert reader.get("deployment", "kri-workload") == {"items": []}
    assert calls == [
        [
            "kubectl",
            "--context",
            "kind-test",
            "--namespace",
            "payments",
            "get",
            "pods",
            "--selector",
            "app=test",
            "--output",
            "json",
        ],
        [
            "kubectl",
            "--context",
            "kind-test",
            "--namespace",
            "payments",
            "get",
            "deployment",
            "kri-workload",
            "--output",
            "json",
        ],
    ]
    with pytest.raises(ValueError, match="boundary"):
        reader.get("secrets")


@pytest.mark.parametrize("context,namespace", [("", "payments"), ("kind-test", " ")])
def test_kubectl_reader_rejects_empty_scope(context: str, namespace: str) -> None:
    with pytest.raises(ValueError):
        KubectlReader(context, namespace)


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CalledProcessError(1, ["kubectl"], stderr="denied"),
        OSError("missing"),
    ],
)
def test_kubectl_reader_wraps_command_failures(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(CollectorError):
        KubectlReader("kind-test", "payments").get("events")


def test_kubectl_reader_rejects_invalid_json_and_non_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = iter(["not-json", "[]"])

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, stdout=next(outputs))

    monkeypatch.setattr(subprocess, "run", run)
    reader = KubectlReader("kind-test", "payments")
    with pytest.raises(CollectorError):
        reader.get("events")
    with pytest.raises(CollectorError, match="non-object"):
        reader.get("events")


class PrometheusResponses:
    def __init__(self, empty_metric: str | None = None) -> None:
        self.empty_metric = empty_metric
        self.urls: list[str] = []

    def __call__(self, url: str) -> Mapping[str, Any]:
        self.urls.append(url)
        query = parse_qs(urlparse(url).query)["query"][0]
        metric = query.split("{", 1)[0]
        if metric == self.empty_metric:
            result: list[dict[str, Any]] = []
        else:
            labels = {
                "__name__": metric,
                "namespace": "payments",
                "pod": "kri-workload-abc",
            }
            if metric.startswith("kri_"):
                labels["job"] = "kri-workload"
            result = [{"metric": labels, "values": [[NOW.timestamp(), "3.5"]]}]
        return {"status": "success", "data": {"resultType": "matrix", "result": result}}


def test_prometheus_collector_preserves_raw_series_timestamps_units_and_scope() -> None:
    responses = PrometheusResponses()
    start = NOW - timedelta(minutes=1)

    snapshot = PrometheusCollector(
        "http://prometheus.test:9090/", responses, clock=lambda: NOW
    ).collect(workload_snapshot(), start, NOW)

    assert snapshot.identity.deployment_uid == "deployment-uid"
    assert snapshot.collected_at == NOW
    assert len(snapshot.series) == len(METRIC_SPECS)
    assert snapshot.series[0].samples[0].timestamp == NOW
    assert snapshot.series[0].samples[0].value == 3.5
    assert snapshot.series[0].unit == "cpu_seconds"
    assert snapshot.missing_data == ()
    assert all("/api/v1/query_range?" in url for url in responses.urls)
    decoded_queries = [
        parse_qs(urlparse(url).query)["query"][0] for url in responses.urls
    ]
    assert all('namespace="payments"' in query for query in decoded_queries)
    assert all('pod=~"kri-workload-abc"' in query for query in decoded_queries)
    assert all(
        'job="kri-workload"' in query
        for query in decoded_queries
        if query.startswith("kri_")
    )
    assert all(
        'container="application"' in query
        for query in decoded_queries
        if query.startswith("container_")
    )
    assert all(parse_qs(urlparse(url).query)["step"] == ["5"] for url in responses.urls)


def test_prometheus_collector_reports_empty_family_without_zero_sample() -> None:
    responses = PrometheusResponses("kri_http_request_errors_total")

    snapshot = PrometheusCollector(
        "http://prometheus.test", responses, clock=lambda: NOW
    ).collect(workload_snapshot(), NOW - timedelta(seconds=30), NOW)

    assert all(
        series.metric_name != "kri_http_request_errors_total"
        for series in snapshot.series
    )
    assert snapshot.missing_data == (
        MissingData(
            source="prometheus",
            field="kri_http_request_errors_total",
            reason="query returned no series",
        ),
    )


def test_prometheus_collector_uses_prometheus_millisecond_precision() -> None:
    snapshot = PrometheusCollector(
        "http://prometheus.test", PrometheusResponses(), clock=lambda: NOW
    ).collect(
        workload_snapshot(),
        NOW + timedelta(microseconds=267),
        NOW + timedelta(seconds=5, microseconds=987),
    )

    assert snapshot.interval_start == NOW
    assert snapshot.interval_end == NOW + timedelta(seconds=5)


def test_prometheus_collector_reports_all_metrics_missing_without_pods() -> None:
    def should_not_run(_: str) -> Mapping[str, Any]:
        raise AssertionError("transport must not be called without Pod identity")

    snapshot = PrometheusCollector(
        "http://prometheus.test", should_not_run, clock=lambda: NOW
    ).collect(workload_snapshot(with_pods=False), NOW - timedelta(seconds=5), NOW)

    assert snapshot.series == ()
    assert {item.field for item in snapshot.missing_data} == {
        metric for metric, _, _ in METRIC_SPECS
    }


@pytest.mark.parametrize(
    "start,end,step",
    [
        (datetime(2026, 1, 1), NOW, 5),
        (NOW, NOW, 5),
        (NOW - timedelta(seconds=1), NOW, 0),
        (
            NOW + timedelta(microseconds=100),
            NOW + timedelta(microseconds=900),
            5,
        ),
    ],
)
def test_prometheus_collector_rejects_invalid_interval(
    start: datetime, end: datetime, step: int
) -> None:
    with pytest.raises(ValueError):
        PrometheusCollector("http://prometheus.test").collect(
            workload_snapshot(), start, end, step_seconds=step
        )


def test_prometheus_collector_rejects_invalid_url_and_naive_clock() -> None:
    with pytest.raises(ValueError, match="HTTP"):
        PrometheusCollector("prometheus.test")
    with pytest.raises(CollectorError, match="naive"):
        PrometheusCollector(
            "http://prometheus.test",
            PrometheusResponses(),
            clock=lambda: datetime(2026, 1, 1),
        ).collect(workload_snapshot(), NOW - timedelta(seconds=1), NOW)


@pytest.mark.parametrize(
    "response",
    [
        {"status": "error"},
        {"status": "success", "data": []},
        {"status": "success", "data": {"resultType": "vector", "result": []}},
        {
            "status": "success",
            "data": {"resultType": "matrix", "result": "bad"},
        },
        {
            "status": "success",
            "data": {"resultType": "matrix", "result": ["bad"]},
        },
    ],
)
def test_prometheus_collector_rejects_malformed_query_response(
    response: Mapping[str, Any],
) -> None:
    with pytest.raises(CollectorError):
        PrometheusCollector(
            "http://prometheus.test", lambda _: response, clock=lambda: NOW
        ).collect(workload_snapshot(), NOW - timedelta(seconds=1), NOW)


def metric_response(labels: object, values: object) -> Mapping[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [{"metric": labels, "values": values}],
        },
    }


@pytest.mark.parametrize(
    "labels,values",
    [
        ([], [[NOW.timestamp(), "1"]]),
        ({1: "value"}, [[NOW.timestamp(), "1"]]),
        (
            {
                "__name__": "wrong",
                "namespace": "payments",
                "pod": "kri-workload-abc",
            },
            [[NOW.timestamp(), "1"]],
        ),
        (
            {
                "namespace": "wrong",
                "pod": "kri-workload-abc",
            },
            [[NOW.timestamp(), "1"]],
        ),
        ({"namespace": "payments", "pod": "unknown"}, [[NOW.timestamp(), "1"]]),
        (
            {
                "namespace": "payments",
                "pod": "kri-workload-abc",
                "job": "wrong",
            },
            [[NOW.timestamp(), "1"]],
        ),
        ({"namespace": "payments", "pod": "kri-workload-abc"}, []),
        ({"namespace": "payments", "pod": "kri-workload-abc"}, ["bad"]),
        ({"namespace": "payments", "pod": "kri-workload-abc"}, [["bad", "1"]]),
        (
            {"namespace": "payments", "pod": "kri-workload-abc"},
            [[NOW.timestamp(), "NaN"]],
        ),
    ],
)
def test_prometheus_collector_rejects_malformed_or_mismatched_series(
    labels: object, values: object
) -> None:
    with pytest.raises(CollectorError):
        PrometheusCollector(
            "http://prometheus.test",
            lambda _: metric_response(labels, values),
            clock=lambda: NOW,
        ).collect(workload_snapshot(), NOW - timedelta(seconds=1), NOW)


def test_http_transport_parses_object_and_wraps_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    monkeypatch.setattr(
        "kri.collectors.urlopen", lambda *_args, **_kwargs: Response(b"{}")
    )
    assert _http_json("http://prometheus.test") == {}

    monkeypatch.setattr(
        "kri.collectors.urlopen", lambda *_args, **_kwargs: Response(b"[]")
    )
    with pytest.raises(CollectorError, match="non-object"):
        _http_json("http://prometheus.test")

    def fail(*_: object, **__: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr("kri.collectors.urlopen", fail)
    with pytest.raises(CollectorError, match="offline"):
        _http_json("http://prometheus.test")


def test_observation_contracts_reject_naive_and_invalid_timestamps() -> None:
    with pytest.raises(ValidationError, match="event timestamp"):
        KubernetesEvent(
            event_type="Normal",
            reason="Started",
            message="started",
            involved_kind="Pod",
            involved_name="pod",
            timestamp=datetime(2026, 1, 1),
        )
    with pytest.raises(ValidationError, match="observation timestamp"):
        WorkloadSnapshot.model_validate(
            {
                **workload_snapshot().model_dump(),
                "observed_at": datetime(2026, 1, 1),
            }
        )
    with pytest.raises(ValidationError, match="sample timestamp"):
        MetricSample(timestamp=datetime(2026, 1, 1), value=1)
    raw = {
        "collected_at": NOW,
        "interval_start": NOW - timedelta(seconds=1),
        "interval_end": NOW,
        "identity": workload_snapshot().identity,
        "series": (),
    }
    with pytest.raises(ValidationError, match="metrics timestamps"):
        RawMetricsSnapshot.model_validate({**raw, "collected_at": datetime(2026, 1, 1)})
    with pytest.raises(ValidationError, match="interval end"):
        RawMetricsSnapshot.model_validate({**raw, "interval_start": NOW})


@pytest.mark.parametrize(
    ("timestamps", "message"),
    [
        ([NOW - timedelta(seconds=2)], "outside"),
        ([NOW, NOW], "strictly increasing"),
    ],
)
def test_metrics_snapshot_rejects_out_of_range_or_unordered_samples(
    timestamps: list[datetime], message: str
) -> None:
    series = MetricSeries(
        metric_name="metric",
        labels={},
        unit="count",
        samples=tuple(MetricSample(timestamp=value, value=1) for value in timestamps),
    )
    with pytest.raises(ValidationError, match=message):
        RawMetricsSnapshot(
            collected_at=NOW,
            interval_start=NOW - timedelta(seconds=1),
            interval_end=NOW,
            identity=workload_snapshot().identity,
            series=(series,),
        )
