"""Offline M10 FastAPI orchestration, validation, and error-boundary tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from kri.analysis import AnalysisError, DeterministicAnalyzer
from kri.api import (
    ApiProblemError,
    ApiServices,
    _problem,
    build_services,
    create_app,
    create_application,
    run,
)
from kri.collectors import CollectorError
from kri.config import Settings
from kri.contracts import (
    AnalysisReport,
    AnalysisSufficiency,
    ContainerResources,
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    MissingData,
    OperationalEvidencePackage,
    PodObservation,
    RawMetricsSnapshot,
    WorkloadConfiguration,
    WorkloadIdentity,
    WorkloadMode,
    WorkloadSnapshot,
)
from kri.knowledge_index import KnowledgeIndexError
from kri.llm_input import (
    LLMInputBuilder,
    LLMInputError,
    LLMInputStore,
    LLMInputStoreError,
)
from kri.observations import (
    NORMALIZATION_SPECS,
    ObservationBuilder,
    ObservationError,
    ObservationStore,
    ObservationStoreError,
)
from kri.rag import RAGError
from kri.workload import (
    ExperimentStoreError,
    KubernetesCommandError,
    WorkloadError,
)

START = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(seconds=60)
NOW = END + timedelta(seconds=1)


@pytest.fixture(autouse=True)
def execute_api_calls_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep offline ASGI tests out of the sandbox's blocked executor shutdown."""

    async def call(function: Any, /, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr("kri.api.asyncio.to_thread", call)


class ApiClient:
    """Small synchronous facade over HTTPX's in-process async ASGI transport."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str) -> httpx.Response:
        return self.request("GET", path)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str) -> httpx.Response:
        return self.request("DELETE", path)


def identity() -> WorkloadIdentity:
    return WorkloadIdentity(
        cluster="kind-test",
        namespace="payments",
        deployment_name="kri-workload",
        deployment_uid="deployment-uid",
    )


def workload_snapshot() -> WorkloadSnapshot:
    return WorkloadSnapshot(
        observed_at=END,
        identity=identity(),
        deployment_resource_version="42",
        pods=(
            PodObservation(
                name="kri-workload-abc",
                uid="pod-uid",
                ready=True,
                restart_count=0,
            ),
        ),
        container_resources=(
            ContainerResources(
                container_name="application",
                cpu_request="50m",
                cpu_limit="100m",
                memory_request="64Mi",
                memory_limit="128Mi",
            ),
        ),
        events=(),
    )


def raw_metrics() -> RawMetricsSnapshot:
    return RawMetricsSnapshot(
        collected_at=NOW,
        interval_start=START,
        interval_end=END,
        identity=identity(),
        series=(),
        missing_data=tuple(
            MissingData(
                source="prometheus",
                field=metric_name,
                reason="offline API fixture has no series",
            )
            for metric_name in sorted(NORMALIZATION_SPECS)
        ),
    )


def workload_configuration() -> WorkloadConfiguration:
    return WorkloadConfiguration(
        cpu_request="50m",
        cpu_limit="100m",
        memory_request="64Mi",
        memory_limit="128Mi",
        replicas=1,
    )


def load_configuration() -> LoadConfiguration:
    return LoadConfiguration(
        workload_mode=WorkloadMode.MIXED,
        concurrency=2,
        request_rate=5,
        duration_seconds=60,
    )


def experiment(state: ExperimentState = ExperimentState.RUNNING) -> ExperimentRecord:
    terminal = state is not ExperimentState.RUNNING
    return ExperimentRecord(
        experiment_id="exp-api",
        workload_configuration=workload_configuration(),
        load_configuration=load_configuration(),
        start_timestamp=START,
        end_timestamp=END if terminal else None,
        lifecycle_state=state,
    )


class FakeWorkload:
    def __init__(self) -> None:
        self.deployments: list[WorkloadConfiguration] = []
        self.deleted = False
        self.started: list[
            tuple[WorkloadConfiguration, LoadConfiguration, str | None]
        ] = []
        self.error: WorkloadError | None = None

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    def deploy_application(self, configuration: WorkloadConfiguration) -> None:
        self._raise()
        self.deployments.append(configuration)

    def delete_application(self) -> None:
        self._raise()
        self.deleted = True

    def start_load(
        self,
        workload: WorkloadConfiguration,
        load: LoadConfiguration,
        experiment_id: str | None = None,
    ) -> ExperimentRecord:
        self._raise()
        self.started.append((workload, load, experiment_id))
        return experiment()

    def stop_load(self, experiment_id: str) -> ExperimentRecord:
        self._raise()
        assert experiment_id == "exp-api"
        return experiment(ExperimentState.STOPPED)

    def sync_load(self, experiment_id: str) -> ExperimentRecord:
        self._raise()
        assert experiment_id == "exp-api"
        return experiment()


class FakeKubernetesCollector:
    def __init__(self) -> None:
        self.error: CollectorError | None = None
        self.calls = 0

    def collect(self, deployment_name: str = "kri-workload") -> WorkloadSnapshot:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert deployment_name == "kri-workload"
        return workload_snapshot()


class FakePrometheusCollector:
    def __init__(self) -> None:
        self.calls: list[tuple[WorkloadSnapshot, datetime, datetime, int]] = []

    def collect(
        self,
        workload: WorkloadSnapshot,
        interval_start: datetime,
        interval_end: datetime,
        *,
        step_seconds: int = 5,
    ) -> RawMetricsSnapshot:
        self.calls.append((workload, interval_start, interval_end, step_seconds))
        return raw_metrics()


class FakeEvidenceRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[AnalysisReport, int]] = []

    def retrieve(
        self, analysis: AnalysisReport, limit_per_query: int = 5
    ) -> OperationalEvidencePackage:
        self.calls.append((analysis, limit_per_query))
        return OperationalEvidencePackage(
            analysis_id=analysis.analysis_id,
            observation_id=analysis.observation_id,
            analysis_source_digest_sha256=(
                analysis.provenance.observation_source_digest_sha256
            ),
            analysis_sufficiency=analysis.sufficiency,
            created_at=NOW,
            bundles=(),
        )


def service_graph(tmp_path: Path) -> tuple[ApiServices, FakeWorkload, Any, Any]:
    workload = FakeWorkload()
    kubernetes = FakeKubernetesCollector()
    prometheus = FakePrometheusCollector()
    observations = ObservationStore(tmp_path / "observations")
    services = ApiServices(
        workload=workload,
        kubernetes=kubernetes,
        prometheus=prometheus,
        observation_builder=ObservationBuilder(clock=lambda: NOW),
        observations=observations,
        analyzer=DeterministicAnalyzer(clock=lambda: NOW),
        evidence=FakeEvidenceRetriever(),
        llm_builder=LLMInputBuilder(clock=lambda: NOW),
        llm_inputs=LLMInputStore(tmp_path / "llm-inputs"),
    )
    return services, workload, kubernetes, prometheus


def interval_body() -> dict[str, object]:
    return {
        "interval_start": START.isoformat(),
        "interval_end": END.isoformat(),
        "step_seconds": 10,
    }


def test_all_api_success_routes_and_openapi(tmp_path: Path) -> None:
    services, workload, kubernetes, prometheus = service_graph(tmp_path)
    client = ApiClient(create_app(services))

    assert client.get("/healthz").json() == {
        "schema_version": "1.0",
        "status": "ok",
        "api_version": "v1",
    }
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/api/v1/llm-inputs" in openapi.json()["paths"]

    configuration = workload_configuration().model_dump(mode="json")
    deployed = client.put("/api/v1/workload", json=configuration)
    assert deployed.status_code == 200
    assert deployed.json()["operation"] == "deploy"
    assert workload.deployments == [workload_configuration()]
    assert client.get("/api/v1/workload").json()["identity"] == identity().model_dump()
    deleted = client.delete("/api/v1/workload")
    assert deleted.json()["resource"] == "deployment-and-service/kri-workload"
    assert workload.deleted is True

    started = client.post(
        "/api/v1/load-experiments",
        json={
            "workload": configuration,
            "load": load_configuration().model_dump(mode="json"),
            "experiment_id": "exp-api",
        },
    )
    assert started.status_code == 201
    assert started.json()["lifecycle_state"] == "running"
    assert client.get("/api/v1/load-experiments/exp-api").status_code == 200
    stopped = client.post("/api/v1/load-experiments/exp-api/stop")
    assert stopped.json()["lifecycle_state"] == "stopped"

    metrics = client.post("/api/v1/metrics/query", json=interval_body())
    assert metrics.status_code == 200
    assert len(metrics.json()["missing_data"]) == len(NORMALIZATION_SPECS)
    assert prometheus.calls[-1][3] == 10

    observation_request = {**interval_body(), "observation_id": "obs-api"}
    created = client.post("/api/v1/observations", json=observation_request)
    assert created.status_code == 201
    assert created.json()["observation_id"] == "obs-api"
    assert client.get("/api/v1/observations/obs-api").status_code == 200
    summary = client.get("/api/v1/observations/obs-api/summary")
    assert summary.json()["quality_status"] == "insufficient"

    analysis_response = client.post(
        "/api/v1/analyses",
        json={"observation_id": "obs-api", "analysis_id": "analysis-api"},
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert analysis["sufficiency"] == AnalysisSufficiency.INSUFFICIENT

    evidence_response = client.post(
        "/api/v1/rag/evidence",
        json={"analysis": analysis, "limit_per_query": 3},
    )
    assert evidence_response.status_code == 200
    evidence = evidence_response.json()
    assert evidence["bundles"] == []

    package_response = client.post(
        "/api/v1/llm-inputs",
        json={
            "analysis": analysis,
            "evidence": evidence,
            "package_id": "llm-api",
        },
    )
    assert package_response.status_code == 201
    assert package_response.json()["retrieval_status"] == "no_findings"
    invalid_package = client.post(
        "/api/v1/llm-inputs",
        json={
            "analysis": analysis,
            "evidence": evidence,
            "package_id": "INVALID",
        },
    )
    assert invalid_package.status_code == 422
    assert client.get("/api/v1/llm-inputs/llm-api").status_code == 200
    package_summary = client.get("/api/v1/llm-inputs/llm-api/summary")
    assert package_summary.json()["package_id"] == "llm-api"
    assert kubernetes.calls == 3


@pytest.mark.parametrize(
    "payload",
    [
        {**interval_body(), "interval_end": START.isoformat()},
        {
            **interval_body(),
            "interval_end": (START + timedelta(microseconds=500)).isoformat(),
        },
        {**interval_body(), "interval_start": "2026-11-01T12:00:00"},
        {**interval_body(), "step_seconds": 0},
    ],
)
def test_request_validation_is_versioned(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    services, _, _, _ = service_graph(tmp_path)
    response = ApiClient(create_app(services)).post(
        "/api/v1/metrics/query", json=payload
    )
    assert response.status_code == 422
    assert response.json()["schema_version"] == "1.0"
    assert response.json()["code"] == "request_validation_error"
    assert response.json()["details"]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/observations", {**interval_body(), "observation_id": "INVALID"}),
        (
            "/api/v1/load-experiments",
            {
                "workload": workload_configuration().model_dump(mode="json"),
                "load": load_configuration().model_dump(mode="json"),
                "experiment_id": "INVALID",
            },
        ),
        (
            "/api/v1/analyses",
            {"observation_id": "INVALID", "analysis_id": "INVALID"},
        ),
    ],
)
def test_safe_identifier_validation(
    tmp_path: Path, path: str, payload: dict[str, object]
) -> None:
    services, _, _, _ = service_graph(tmp_path)
    assert ApiClient(create_app(services)).post(path, json=payload).status_code == 422


def test_domain_error_handler_and_missing_artifacts(tmp_path: Path) -> None:
    services, _, kubernetes, _ = service_graph(tmp_path)
    kubernetes.error = CollectorError("kubectl unavailable")
    client = ApiClient(create_app(services))
    response = client.get("/api/v1/workload")
    assert response.status_code == 502
    assert response.json()["code"] == "external_dependency_error"

    missing = client.get("/api/v1/observations/missing")
    assert missing.status_code == 404
    assert missing.json()["code"] == "observation_not_found"
    missing_package = client.get("/api/v1/llm-inputs/missing")
    assert missing_package.status_code == 404
    assert missing_package.json()["code"] == "llm_input_not_found"
    invalid_path = client.get("/api/v1/observations/INVALID")
    assert invalid_path.status_code == 422
    assert invalid_path.json()["code"] == "request_validation_error"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (CollectorError("failed"), 502, "external_dependency_error"),
        (KubernetesCommandError("failed"), 502, "external_dependency_error"),
        (KnowledgeIndexError("failed"), 502, "external_dependency_error"),
        (RAGError("failed"), 502, "retrieval_error"),
        (
            ExperimentStoreError("experiment does not exist"),
            404,
            "experiment_not_found",
        ),
        (ExperimentStoreError("experiment already exists"), 409, "experiment_conflict"),
        (ExperimentStoreError("disk"), 500, "experiment_store_error"),
        (WorkloadError("already stopped"), 409, "workload_conflict"),
        (WorkloadError("failed"), 502, "workload_error"),
        (
            ObservationStoreError("observation does not exist"),
            404,
            "observation_not_found",
        ),
        (
            ObservationStoreError("observation already exists"),
            409,
            "observation_conflict",
        ),
        (ObservationStoreError("corrupt"), 500, "observation_store_error"),
        (ObservationError("identity"), 422, "observation_error"),
        (AnalysisError("invalid"), 422, "analysis_error"),
        (LLMInputError("mismatch"), 422, "llm_input_error"),
        (LLMInputStoreError("package does not exist"), 404, "llm_input_not_found"),
        (LLMInputStoreError("package already exists"), 409, "llm_input_conflict"),
        (LLMInputStoreError("corrupt"), 500, "llm_input_store_error"),
    ],
)
def test_domain_error_mapping(error: Exception, status_code: int, code: str) -> None:
    problem = _problem(error)
    assert problem.status_code == status_code
    assert problem.code == code
    assert problem.message == str(error)


def test_unknown_error_is_not_hidden() -> None:
    error = RuntimeError("unexpected")
    with pytest.raises(RuntimeError, match="unexpected") as caught:
        _problem(error)
    assert caught.value is error
    assert ApiProblemError(418, "teapot", "short").details == ()


def settings() -> Settings:
    return Settings(
        k8s_context="kind-test",
        k8s_namespace="payments",
        workload_image="kri-workload:local",
        prometheus_url="http://prometheus.test:9090",
        qdrant_url="http://qdrant.test:6333",
        qdrant_collection="kri_test",
        ollama_url="http://ollama.test:11434",
        ollama_model="unused",
    )


def test_production_factory_and_runner_are_lazy_and_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = build_services(
        settings(),
        results_directory=tmp_path / "results",
        knowledge_root=Path("knowledge"),
    )
    assert isinstance(built.observations, ObservationStore)
    assert isinstance(built.llm_inputs, LLMInputStore)

    monkeypatch.setattr("kri.api.load_settings", settings)
    monkeypatch.setattr("kri.api.build_services", lambda _: built)
    assert create_application().title == "Kubernetes Resource Intelligence API"

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        "kri.api.uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    run()
    assert calls == [
        (
            ("kri.api:create_application",),
            {"factory": True, "host": "127.0.0.1", "port": 8000},
        )
    ]
