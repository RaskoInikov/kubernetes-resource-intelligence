"""Offline command routing tests for the explicit workload CLI."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar

import pytest

from kri import cli
from kri.contracts import (
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    WorkloadConfiguration,
)


class FakeController:
    latest: ClassVar["FakeController"]

    def __init__(self, kubernetes: object, store: object, image: str) -> None:
        self.kubernetes = kubernetes
        self.store = store
        self.image = image
        self.calls: list[tuple[str, object]] = []
        FakeController.latest = self

    def deploy_application(self, configuration: WorkloadConfiguration) -> None:
        self.calls.append(("deploy", configuration))

    def delete_application(self) -> None:
        self.calls.append(("delete", None))

    def start_load(
        self,
        workload: WorkloadConfiguration,
        load: LoadConfiguration,
        experiment_id: str | None,
    ) -> ExperimentRecord:
        self.calls.append(("start", (workload, load, experiment_id)))
        return _record(experiment_id or "exp-generated")

    def stop_load(self, experiment_id: str) -> ExperimentRecord:
        self.calls.append(("stop", experiment_id))
        return _record(experiment_id)

    def sync_load(self, experiment_id: str) -> ExperimentRecord:
        self.calls.append(("status", experiment_id))
        return _record(experiment_id)


def _record(experiment_id: str) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=experiment_id,
        workload_configuration=WorkloadConfiguration(
            cpu_request="100m",
            cpu_limit="500m",
            memory_request="64Mi",
            memory_limit="128Mi",
            replicas=1,
        ),
        load_configuration=LoadConfiguration(
            workload_mode="cpu",
            concurrency=1,
            request_rate=1,
            duration_seconds=1,
        ),
        start_timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        lifecycle_state=ExperimentState.RUNNING,
    )


@pytest.fixture(autouse=True)
def fake_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        k8s_context="kind-test",
        k8s_namespace="payments",
        workload_image="kri:test",
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(
        cli, "KubectlClient", lambda context, namespace: (context, namespace)
    )
    monkeypatch.setattr(cli, "ExperimentStore", lambda path: path)
    monkeypatch.setattr(cli, "WorkloadController", FakeController)


WORKLOAD_ARGUMENTS = [
    "--cpu-request",
    "100m",
    "--cpu-limit",
    "500m",
    "--memory-request",
    "64Mi",
    "--memory-limit",
    "128Mi",
    "--replicas",
    "1",
]


def test_cli_routes_application_operations() -> None:
    assert cli.main(["deploy", *WORKLOAD_ARGUMENTS]) == 0
    operation, configuration = FakeController.latest.calls[0]
    assert operation == "deploy"
    assert isinstance(configuration, WorkloadConfiguration)

    assert cli.main(["delete"]) == 0
    assert FakeController.latest.calls == [("delete", None)]


def test_cli_routes_start_and_prints_record(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(
        [
            "start-load",
            *WORKLOAD_ARGUMENTS,
            "--mode",
            "mixed",
            "--concurrency",
            "2",
            "--request-rate",
            "3.5",
            "--duration-seconds",
            "10",
            "--experiment-id",
            "exp-cli",
        ]
    )

    assert result == 0
    operation, arguments = FakeController.latest.calls[0]
    assert operation == "start"
    assert isinstance(arguments, tuple)
    assert arguments[1].workload_mode.value == "mixed"
    assert '"experiment_id": "exp-cli"' in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command", "operation"), [("stop-load", "stop"), ("status", "status")]
)
def test_cli_routes_record_operations(
    command: str,
    operation: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([command, "exp-cli"]) == 0
    assert FakeController.latest.calls == [(operation, "exp-cli")]
    assert '"experiment_id": "exp-cli"' in capsys.readouterr().out
