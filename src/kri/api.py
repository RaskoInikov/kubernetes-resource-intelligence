"""M10 FastAPI orchestration over the existing M1-M9 component boundaries."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Protocol

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kri.analysis import AnalysisError, DeterministicAnalyzer
from kri.collectors import (
    CollectorError,
    KubectlReader,
    KubernetesCollector,
    PrometheusCollector,
)
from kri.config import Settings, load_settings
from kri.contracts import (
    EXPERIMENT_ID_PATTERN,
    OBSERVATION_ID_PATTERN,
    AnalysisCreateRequest,
    AnalysisReport,
    ApiErrorResponse,
    ApiHealthResponse,
    ApiOperationResponse,
    EvidenceCreateRequest,
    ExperimentRecord,
    LLMInputCreateRequest,
    LLMInputPackage,
    LLMInputSummary,
    LoadConfiguration,
    MetricsRangeRequest,
    ObservationCreateRequest,
    ObservationSnapshot,
    ObservationSummary,
    OperationalEvidencePackage,
    RawMetricsSnapshot,
    StartLoadRequest,
    WorkloadConfiguration,
    WorkloadSnapshot,
)
from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import (
    KnowledgeIndexError,
    KnowledgeInspectionAPI,
    QdrantHttpGateway,
)
from kri.llm_input import (
    LLMInputBuilder,
    LLMInputError,
    LLMInputStore,
    LLMInputStoreError,
)
from kri.observations import (
    ObservationBuilder,
    ObservationError,
    ObservationStore,
    ObservationStoreError,
)
from kri.rag import AnalysisEvidenceRetriever, RAGError
from kri.workload import (
    ExperimentStore,
    ExperimentStoreError,
    KubectlClient,
    KubernetesCommandError,
    WorkloadController,
    WorkloadError,
)

API_VERSION = "1.0.0"
ExperimentId = Annotated[str, ApiPath(pattern=EXPERIMENT_ID_PATTERN.pattern)]
ArtifactId = Annotated[str, ApiPath(pattern=OBSERVATION_ID_PATTERN.pattern)]


class WorkloadOperations(Protocol):
    def deploy_application(self, configuration: WorkloadConfiguration) -> None: ...

    def delete_application(self) -> None: ...

    def start_load(
        self,
        workload: WorkloadConfiguration,
        load: LoadConfiguration,
        experiment_id: str | None = None,
    ) -> ExperimentRecord: ...

    def stop_load(self, experiment_id: str) -> ExperimentRecord: ...

    def sync_load(self, experiment_id: str) -> ExperimentRecord: ...


class WorkloadCollection(Protocol):
    def collect(self, deployment_name: str = "kri-workload") -> WorkloadSnapshot: ...


class MetricsCollection(Protocol):
    def collect(
        self,
        workload: WorkloadSnapshot,
        interval_start: datetime,
        interval_end: datetime,
        *,
        step_seconds: int = 5,
    ) -> RawMetricsSnapshot: ...


class AnalysisOperations(Protocol):
    def analyze_saved(
        self,
        store: ObservationStore,
        observation_id: str,
        analysis_id: str | None = None,
    ) -> AnalysisReport: ...


class EvidenceOperations(Protocol):
    def retrieve(
        self, analysis: AnalysisReport, limit_per_query: int = 5
    ) -> OperationalEvidencePackage: ...


class LLMInputOperations(Protocol):
    def build(
        self,
        analysis: AnalysisReport,
        evidence: OperationalEvidencePackage,
        package_id: str | None = None,
    ) -> LLMInputPackage: ...


class LLMInputStorage(Protocol):
    def save(self, package: LLMInputPackage) -> Path: ...

    def load(self, package_id: str) -> LLMInputPackage: ...

    def inspect(self, package_id: str) -> LLMInputSummary: ...


@dataclass(frozen=True)
class ApiServices:
    """Injected M1-M9 service graph used by the HTTP boundary."""

    workload: WorkloadOperations
    kubernetes: WorkloadCollection
    prometheus: MetricsCollection
    observation_builder: ObservationBuilder
    observations: ObservationStore
    analyzer: AnalysisOperations
    evidence: EvidenceOperations
    llm_builder: LLMInputOperations
    llm_inputs: LLMInputStorage


class ApiProblemError(RuntimeError):
    """One intentionally mapped HTTP failure."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _problem(error: Exception) -> ApiProblemError:
    message = str(error) or error.__class__.__name__
    if isinstance(error, (CollectorError, KubernetesCommandError, KnowledgeIndexError)):
        return ApiProblemError(502, "external_dependency_error", message)
    if isinstance(error, RAGError):
        return ApiProblemError(502, "retrieval_error", message)
    if isinstance(error, ExperimentStoreError):
        if "does not exist" in message:
            return ApiProblemError(404, "experiment_not_found", message)
        if "already exists" in message:
            return ApiProblemError(409, "experiment_conflict", message)
        return ApiProblemError(500, "experiment_store_error", message)
    if isinstance(error, WorkloadError):
        if "already" in message:
            return ApiProblemError(409, "workload_conflict", message)
        return ApiProblemError(502, "workload_error", message)
    if isinstance(error, ObservationStoreError):
        if "does not exist" in message:
            return ApiProblemError(404, "observation_not_found", message)
        if "already exists" in message:
            return ApiProblemError(409, "observation_conflict", message)
        return ApiProblemError(500, "observation_store_error", message)
    if isinstance(error, ObservationError):
        return ApiProblemError(422, "observation_error", message)
    if isinstance(error, AnalysisError):
        return ApiProblemError(422, "analysis_error", message)
    if isinstance(error, LLMInputError):
        return ApiProblemError(422, "llm_input_error", message)
    if isinstance(error, LLMInputStoreError):
        if "does not exist" in message:
            return ApiProblemError(404, "llm_input_not_found", message)
        if "already exists" in message:
            return ApiProblemError(409, "llm_input_conflict", message)
        return ApiProblemError(500, "llm_input_store_error", message)
    raise error


def build_services(
    settings: Settings,
    results_directory: Path = Path("results"),
    knowledge_root: Path = Path("knowledge"),
) -> ApiServices:
    """Construct production services after settings have validated."""

    observations = ObservationStore(results_directory / "observations")
    repository = KnowledgeRepository(knowledge_root)
    knowledge = KnowledgeInspectionAPI(
        repository,
        QdrantHttpGateway(str(settings.qdrant_url), timeout_seconds=30),
        settings.qdrant_collection,
    )
    return ApiServices(
        workload=WorkloadController(
            KubectlClient(settings.k8s_context, settings.k8s_namespace),
            ExperimentStore(results_directory / "experiments"),
            settings.workload_image,
        ),
        kubernetes=KubernetesCollector(
            KubectlReader(settings.k8s_context, settings.k8s_namespace)
        ),
        prometheus=PrometheusCollector(str(settings.prometheus_url)),
        observation_builder=ObservationBuilder(),
        observations=observations,
        analyzer=DeterministicAnalyzer(),
        evidence=AnalysisEvidenceRetriever(knowledge),
        llm_builder=LLMInputBuilder(),
        llm_inputs=LLMInputStore(results_directory / "llm-inputs"),
    )


def create_app(services: ApiServices) -> FastAPI:
    """Create the testable M10 application around an injected service graph."""

    app = FastAPI(
        title="Kubernetes Resource Intelligence API",
        version=API_VERSION,
        description="Local versioned orchestration of the validated M1-M9 pipeline.",
    )

    @app.exception_handler(CollectorError)
    @app.exception_handler(WorkloadError)
    @app.exception_handler(ObservationStoreError)
    @app.exception_handler(ObservationError)
    @app.exception_handler(AnalysisError)
    @app.exception_handler(KnowledgeIndexError)
    @app.exception_handler(RAGError)
    @app.exception_handler(LLMInputError)
    @app.exception_handler(LLMInputStoreError)
    async def domain_error_handler(_: Request, error: Exception) -> JSONResponse:
        problem = _problem(error)
        payload = ApiErrorResponse(
            code=problem.code,
            message=problem.message,
            details=problem.details,
        )
        return JSONResponse(
            status_code=problem.status_code,
            content=payload.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = tuple(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        )
        payload = ApiErrorResponse(
            code="request_validation_error",
            message="request validation failed",
            details=details,
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.get("/healthz", response_model=ApiHealthResponse)
    async def health() -> ApiHealthResponse:
        return ApiHealthResponse()

    @app.put("/api/v1/workload", response_model=ApiOperationResponse)
    async def deploy_workload(
        configuration: WorkloadConfiguration,
    ) -> ApiOperationResponse:
        await asyncio.to_thread(services.workload.deploy_application, configuration)
        return ApiOperationResponse(
            operation="deploy", resource="deployment/kri-workload"
        )

    @app.delete("/api/v1/workload", response_model=ApiOperationResponse)
    async def delete_workload() -> ApiOperationResponse:
        await asyncio.to_thread(services.workload.delete_application)
        return ApiOperationResponse(
            operation="delete", resource="deployment-and-service/kri-workload"
        )

    @app.get("/api/v1/workload", response_model=WorkloadSnapshot)
    async def current_workload() -> WorkloadSnapshot:
        return await asyncio.to_thread(services.kubernetes.collect)

    @app.post(
        "/api/v1/load-experiments",
        response_model=ExperimentRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def start_load(request: StartLoadRequest) -> ExperimentRecord:
        return await asyncio.to_thread(
            services.workload.start_load,
            request.workload,
            request.load,
            request.experiment_id,
        )

    @app.post(
        "/api/v1/load-experiments/{experiment_id}/stop",
        response_model=ExperimentRecord,
    )
    async def stop_load(experiment_id: ExperimentId) -> ExperimentRecord:
        return await asyncio.to_thread(services.workload.stop_load, experiment_id)

    @app.get(
        "/api/v1/load-experiments/{experiment_id}",
        response_model=ExperimentRecord,
    )
    async def load_status(experiment_id: ExperimentId) -> ExperimentRecord:
        return await asyncio.to_thread(services.workload.sync_load, experiment_id)

    @app.post("/api/v1/metrics/query", response_model=RawMetricsSnapshot)
    async def live_metrics(request: MetricsRangeRequest) -> RawMetricsSnapshot:
        workload = await asyncio.to_thread(services.kubernetes.collect)
        return await asyncio.to_thread(
            services.prometheus.collect,
            workload,
            request.interval_start,
            request.interval_end,
            step_seconds=request.step_seconds,
        )

    @app.post(
        "/api/v1/observations",
        response_model=ObservationSnapshot,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_observation(
        request: ObservationCreateRequest,
    ) -> ObservationSnapshot:
        workload = await asyncio.to_thread(services.kubernetes.collect)
        metrics = await asyncio.to_thread(
            services.prometheus.collect,
            workload,
            request.interval_start,
            request.interval_end,
            step_seconds=request.step_seconds,
        )
        snapshot = await asyncio.to_thread(
            services.observation_builder.build,
            workload,
            metrics,
            request.observation_id,
        )
        await asyncio.to_thread(services.observations.save, snapshot)
        return snapshot

    @app.get(
        "/api/v1/observations/{observation_id}", response_model=ObservationSnapshot
    )
    async def get_observation(observation_id: ArtifactId) -> ObservationSnapshot:
        return await asyncio.to_thread(services.observations.load, observation_id)

    @app.get(
        "/api/v1/observations/{observation_id}/summary",
        response_model=ObservationSummary,
    )
    async def inspect_observation(observation_id: ArtifactId) -> ObservationSummary:
        return await asyncio.to_thread(services.observations.inspect, observation_id)

    @app.post("/api/v1/analyses", response_model=AnalysisReport)
    async def create_analysis(request: AnalysisCreateRequest) -> AnalysisReport:
        return await asyncio.to_thread(
            services.analyzer.analyze_saved,
            services.observations,
            request.observation_id,
            request.analysis_id,
        )

    @app.post("/api/v1/rag/evidence", response_model=OperationalEvidencePackage)
    async def create_evidence(
        request: EvidenceCreateRequest,
    ) -> OperationalEvidencePackage:
        return await asyncio.to_thread(
            services.evidence.retrieve, request.analysis, request.limit_per_query
        )

    @app.post(
        "/api/v1/llm-inputs",
        response_model=LLMInputPackage,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_llm_input(request: LLMInputCreateRequest) -> LLMInputPackage:
        package = await asyncio.to_thread(
            services.llm_builder.build,
            request.analysis,
            request.evidence,
            request.package_id,
        )
        await asyncio.to_thread(services.llm_inputs.save, package)
        return package

    @app.get("/api/v1/llm-inputs/{package_id}", response_model=LLMInputPackage)
    async def get_llm_input(package_id: ArtifactId) -> LLMInputPackage:
        return await asyncio.to_thread(services.llm_inputs.load, package_id)

    @app.get(
        "/api/v1/llm-inputs/{package_id}/summary",
        response_model=LLMInputSummary,
    )
    async def inspect_llm_input(package_id: ArtifactId) -> LLMInputSummary:
        return await asyncio.to_thread(services.llm_inputs.inspect, package_id)

    return app


def create_application() -> FastAPI:
    """Uvicorn factory that validates settings before constructing services."""

    return create_app(build_services(load_settings()))


def run() -> None:
    """Run the local-development API on loopback only."""

    uvicorn.run("kri.api:create_application", factory=True, host="127.0.0.1", port=8000)
