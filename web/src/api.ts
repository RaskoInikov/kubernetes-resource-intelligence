import type {
  AnalysisReport,
  ExperimentRecord,
  LLMInputPackage,
  LLMInputSummary,
  LoadConfiguration,
  ObservationSnapshot,
  ObservationSummary,
  OperationalEvidencePackage,
  RawMetricsSnapshot,
  WorkloadConfiguration,
  WorkloadSnapshot,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly operation: string,
    readonly status: number | null,
    readonly code: string,
    message: string,
    readonly details: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface MetricsRange {
  interval_start: string;
  interval_end: string;
  step_seconds: number;
}

export interface PipelineApi {
  health(): Promise<{ status: "ok"; api_version: "v1" }>;
  deployWorkload(configuration: WorkloadConfiguration): Promise<void>;
  deleteWorkload(): Promise<void>;
  getWorkload(): Promise<WorkloadSnapshot>;
  startLoad(
    workload: WorkloadConfiguration,
    load: LoadConfiguration,
    experimentId?: string,
  ): Promise<ExperimentRecord>;
  getLoad(experimentId: string): Promise<ExperimentRecord>;
  stopLoad(experimentId: string): Promise<ExperimentRecord>;
  queryMetrics(range: MetricsRange): Promise<RawMetricsSnapshot>;
  createObservation(
    range: MetricsRange,
    observationId?: string,
  ): Promise<ObservationSnapshot>;
  getObservation(observationId: string): Promise<ObservationSnapshot>;
  getObservationSummary(observationId: string): Promise<ObservationSummary>;
  analyze(observationId: string, analysisId?: string): Promise<AnalysisReport>;
  retrieveEvidence(analysis: AnalysisReport): Promise<OperationalEvidencePackage>;
  createLLMInput(
    analysis: AnalysisReport,
    evidence: OperationalEvidencePackage,
    packageId?: string,
  ): Promise<LLMInputPackage>;
  getLLMInput(packageId: string): Promise<LLMInputPackage>;
  getLLMInputSummary(packageId: string): Promise<LLMInputSummary>;
}

const defaultBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

async function request<T>(
  operation: string,
  path: string,
  init: RequestInit = {},
  baseUrl = defaultBaseUrl,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch (error) {
    throw new ApiError(
      operation,
      null,
      "network_error",
      error instanceof Error ? error.message : "network request failed",
    );
  }
  if (!response.ok) {
    let body: { code?: string; message?: string; details?: string[] } = {};
    try {
      body = (await response.json()) as typeof body;
    } catch {
      body = {};
    }
    throw new ApiError(
      operation,
      response.status,
      body.code ?? "http_error",
      body.message ?? `${response.status} ${response.statusText}`,
      body.details ?? [],
    );
  }
  return (await response.json()) as T;
}

const json = (value: unknown): string => JSON.stringify(value);

export const api: PipelineApi = {
  health: () => request("Connect to FastAPI", "/healthz"),
  async deployWorkload(configuration) {
    await request("Deploy workload", "/api/v1/workload", {
      method: "PUT",
      body: json(configuration),
    });
  },
  async deleteWorkload() {
    await request("Delete workload", "/api/v1/workload", { method: "DELETE" });
  },
  getWorkload: () => request("Refresh workload", "/api/v1/workload"),
  startLoad: (workload, load, experimentId) =>
    request("Start load", "/api/v1/load-experiments", {
      method: "POST",
      body: json({
        workload,
        load,
        ...(experimentId ? { experiment_id: experimentId } : {}),
      }),
    }),
  getLoad: (experimentId) =>
    request("Refresh load", `/api/v1/load-experiments/${experimentId}`),
  stopLoad: (experimentId) =>
    request("Stop load", `/api/v1/load-experiments/${experimentId}/stop`, {
      method: "POST",
    }),
  queryMetrics: (range) =>
    request("Query metrics", "/api/v1/metrics/query", {
      method: "POST",
      body: json(range),
    }),
  createObservation: (range, observationId) =>
    request("Collect observation", "/api/v1/observations", {
      method: "POST",
      body: json({
        ...range,
        ...(observationId ? { observation_id: observationId } : {}),
      }),
    }),
  getObservation: (observationId) =>
    request("Load observation", `/api/v1/observations/${observationId}`),
  getObservationSummary: (observationId) =>
    request(
      "Inspect observation",
      `/api/v1/observations/${observationId}/summary`,
    ),
  analyze: (observationId, analysisId) =>
    request("Run analysis", "/api/v1/analyses", {
      method: "POST",
      body: json({
        observation_id: observationId,
        ...(analysisId ? { analysis_id: analysisId } : {}),
      }),
    }),
  retrieveEvidence: (analysis) =>
    request("Retrieve RAG evidence", "/api/v1/rag/evidence", {
      method: "POST",
      body: json({ analysis, limit_per_query: 5 }),
    }),
  createLLMInput: (analysis, evidence, packageId) =>
    request("Create LLM input", "/api/v1/llm-inputs", {
      method: "POST",
      body: json({
        analysis,
        evidence,
        ...(packageId ? { package_id: packageId } : {}),
      }),
    }),
  getLLMInput: (packageId) =>
    request("Load LLM input", `/api/v1/llm-inputs/${packageId}`),
  getLLMInputSummary: (packageId) =>
    request("Inspect LLM input", `/api/v1/llm-inputs/${packageId}/summary`),
};
