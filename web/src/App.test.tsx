import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, type PipelineApi } from "./api";
import { App } from "./App";
import type {
  AnalysisReport,
  LLMInputPackage,
  LLMInputSummary,
  ObservationSnapshot,
  ObservationSummary,
  OperationalEvidencePackage,
  RawMetricsSnapshot,
} from "./types";

const observation = {
  observation_id: "obs-ui-test",
  created_at: "2026-11-01T10:02:00Z",
  quality_report: { status: "complete", issues: [] },
  normalized_series: [],
  provenance: { source_digest_sha256: "a".repeat(64) },
} as ObservationSnapshot;

afterEach(() => vi.useRealTimers());

const observationSummary = {
  observation_id: "obs-ui-test",
  created_at: "2026-11-01T10:02:00Z",
  identity: {
    cluster: "kind-test",
    namespace: "payments",
    deployment_name: "kri-workload",
    deployment_uid: "uid-1",
  },
  interval_start: "2026-11-01T10:00:00Z",
  interval_end: "2026-11-01T10:01:00Z",
  quality_status: "complete",
  issue_count: 0,
  normalized_series_count: 2,
  sample_count: 4,
} as ObservationSummary;

const analysis = {
  analysis_id: "analysis-ui-test",
  observation_id: "obs-ui-test",
  created_at: "2026-11-01T10:03:00Z",
  sufficiency: "sufficient",
  statistics: [],
  conditions: [
    {
      condition_id: "cpu-pressure",
      condition_type: "cpu_limit_pressure",
      severity: "warning",
      message: "CPU approaches its configured limit",
      observed_value: 0.9,
      threshold: 0.8,
    },
  ],
  recommendations: [
    {
      recommendation_id: "cpu-limit",
      resource: "cpu_limit",
      current_value: "100m",
      recommended_value: "160m",
      rationale: "Provide bounded headroom.",
      requires_approval: true,
    },
  ],
  risks_and_uncertainties: ["Finite observation window."],
} as AnalysisReport;

const evidence = {
  analysis_id: "analysis-ui-test",
  observation_id: "obs-ui-test",
  created_at: "2026-11-01T10:04:00Z",
  bundles: [
    {
      query_id: "query-1",
      query_kind: "recommendation",
      query: "CPU limit guidance",
      retrieval: {
        hits: [
          {
            score: 0.91,
            semantic_score: 0.9,
            lexical_match_ratio: 0.96,
            chunk: {
              chunk_id: "cpu-doc-chunk-1",
              document_id: "cpu-doc",
              document_title: "CPU limits",
              section: "Diagnosis",
              verification_status: "verified",
              text: "Confirm sustained throttling before changing a limit.",
              sources: [{ title: "Kubernetes docs", uri: "https://kubernetes.io/" }],
            },
          },
        ],
      },
    },
  ],
} as OperationalEvidencePackage;

const llmInput = {
  package_id: "llm-input-ui-test",
  analysis_id: "analysis-ui-test",
  observation_id: "obs-ui-test",
  created_at: "2026-11-01T10:05:00Z",
  sufficiency: "sufficient",
  retrieval_status: "retrieved",
  analysis_digest_sha256: "b".repeat(64),
  operational_evidence_digest_sha256: "c".repeat(64),
  statistics: [],
  conditions: [],
  recommendations: [],
  risks_and_uncertainties: [],
  retrieval_queries: [{}],
  retrieval_hits: [{}],
  evidence_excerpts: [{}],
} as LLMInputPackage;

const llmSummary = {
  package_id: "llm-input-ui-test",
  created_at: "2026-11-01T10:05:00Z",
  analysis_id: "analysis-ui-test",
  observation_id: "obs-ui-test",
  sufficiency: "sufficient",
  retrieval_status: "retrieved",
  statistic_count: 1,
  condition_count: 1,
  recommendation_count: 1,
  uncertainty_count: 1,
  query_count: 1,
  hit_reference_count: 1,
  excerpt_count: 1,
  package_sha256: "d".repeat(64),
} as LLMInputSummary;

function fakeApi(overrides: Partial<PipelineApi> = {}): PipelineApi {
  return {
    health: vi.fn().mockResolvedValue({ status: "ok", api_version: "v1" }),
    deployWorkload: vi.fn().mockResolvedValue(undefined),
    deleteWorkload: vi.fn().mockResolvedValue(undefined),
    getWorkload: vi.fn(),
    startLoad: vi.fn(),
    getLoad: vi.fn(),
    stopLoad: vi.fn().mockResolvedValue({
      schema_version: "1.1",
      experiment_id: "exp-ui-test",
      lifecycle_state: "stopped",
      start_timestamp: "2026-11-01T10:00:00Z",
      job_uid: "job-uid-1",
      job_start_timestamp: "2026-11-01T10:00:01Z",
      end_timestamp: "2026-11-01T10:01:00Z",
      termination_reason: "UserStopped",
      termination_message: "Load Job deleted by an explicit stop request.",
      termination_source: "controller",
    }),
    queryMetrics: vi.fn(),
    createObservation: vi.fn().mockResolvedValue(observation),
    getObservation: vi.fn().mockResolvedValue(observation),
    getObservationSummary: vi.fn().mockResolvedValue(observationSummary),
    analyze: vi.fn().mockResolvedValue(analysis),
    retrieveEvidence: vi.fn().mockResolvedValue(evidence),
    createLLMInput: vi.fn().mockResolvedValue(llmInput),
    getLLMInput: vi.fn().mockResolvedValue(llmInput),
    getLLMInputSummary: vi.fn().mockResolvedValue(llmSummary),
    ...overrides,
  };
}

describe("M11 pipeline interface", () => {
  it("polls running experiments and renders terminal provenance", async () => {
    vi.useFakeTimers();
    const running = {
      schema_version: "1.1",
      experiment_id: "exp-auto-sync",
      lifecycle_state: "running",
      start_timestamp: "2026-11-01T10:00:00Z",
      job_uid: null,
      job_start_timestamp: null,
      end_timestamp: null,
      termination_reason: null,
      termination_message: null,
      termination_source: null,
    } as const;
    const completed = {
      ...running,
      job_uid: "job-uid-1",
      job_start_timestamp: "2026-11-01T10:00:01Z",
      end_timestamp: "2026-11-01T10:01:00Z",
      lifecycle_state: "succeeded",
      termination_reason: "CompletionsReached",
      termination_message: "Job completed",
      termination_source: "kubernetes",
    } as const;
    const client = fakeApi({
      startLoad: vi.fn().mockResolvedValue(running),
      getLoad: vi.fn().mockResolvedValue(completed),
    });
    render(<App client={client} />);

    fireEvent.click(screen.getByRole("button", { name: "Start load" }));
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(2_000));

    expect(client.getLoad).toHaveBeenCalledWith("exp-auto-sync");
    expect(screen.getByTestId("experiment-status")).toHaveTextContent("succeeded");
    expect(screen.getByTestId("experiment-status")).toHaveTextContent(
      "CompletionsReached · kubernetes",
    );
    expect(screen.getByTestId("experiment-status")).toHaveTextContent(
      "2026-11-01T10:01:00Z",
    );
    vi.useRealTimers();
  });

  it("shows automatic experiment reconciliation failures", async () => {
    vi.useFakeTimers();
    const running = {
      schema_version: "1.1",
      experiment_id: "exp-auto-error",
      lifecycle_state: "running",
      start_timestamp: "2026-11-01T10:00:00Z",
      job_uid: null,
      job_start_timestamp: null,
      end_timestamp: null,
      termination_reason: null,
      termination_message: null,
      termination_source: null,
    } as const;
    const failure = new ApiError(
      "Refresh load",
      502,
      "external_dependency_error",
      "Job status unavailable",
    );
    const client = fakeApi({
      startLoad: vi.fn().mockResolvedValue(running),
      getLoad: vi.fn().mockRejectedValue(failure),
    });
    render(<App client={client} />);

    fireEvent.click(screen.getByRole("button", { name: "Start load" }));
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(2_000));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Refresh load: HTTP 502 · external_dependency_error: Job status unavailable",
    );
  });

  it("chains exact observation, analysis, evidence, and package contracts", async () => {
    const user = userEvent.setup();
    const client = fakeApi();
    render(<App client={client} />);
    await user.clear(screen.getByLabelText("Observation ID"));
    await user.type(screen.getByLabelText("Observation ID"), "obs-ui-test");

    await user.click(screen.getByRole("button", { name: "Collect observation" }));
    expect(await screen.findByText("4", { selector: "strong" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run M5 analysis" }));
    expect(await screen.findByText("CPU approaches its configured limit")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retrieve M8 evidence" }));
    expect(await screen.findByText("CPU limit guidance")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Package ID"));
    await user.type(screen.getByLabelText("Package ID"), "llm-input-ui-test");
    await user.click(screen.getByRole("button", { name: "Create M9 package" }));

    await waitFor(() => expect(client.retrieveEvidence).toHaveBeenCalledWith(analysis));
    expect(client.createLLMInput).toHaveBeenCalledWith(
      analysis,
      evidence,
      "llm-input-ui-test",
    );
    expect(await screen.findByText(/sha256 d{64}/)).toBeInTheDocument();
  });

  it("keeps stopping load independent from application deletion", async () => {
    const user = userEvent.setup();
    const client = fakeApi();
    render(<App client={client} />);
    await user.type(screen.getByLabelText("Experiment ID"), "exp-ui-test");
    await user.click(screen.getByRole("button", { name: "Stop load only" }));

    expect(client.stopLoad).toHaveBeenCalledWith("exp-ui-test");
    expect(client.deleteWorkload).not.toHaveBeenCalled();
    expect(await screen.findByText("stopped")).toBeInTheDocument();
  });

  it("renders timestamped metrics and reports missing data without zero fill", async () => {
    const user = userEvent.setup();
    const metrics = {
      collected_at: "2026-11-01T10:02:00Z",
      interval_start: "2026-11-01T10:00:00Z",
      interval_end: "2026-11-01T10:01:00Z",
      identity: observationSummary.identity,
      series: [
        {
          metric_name: "container_cpu_usage_seconds_total",
          labels: { pod: "kri-workload-a" },
          unit: "seconds",
          samples: [
            { timestamp: "2026-11-01T10:00:00Z", value: 1 },
            { timestamp: "2026-11-01T10:00:05Z", value: 2 },
          ],
        },
      ],
      missing_data: [
        { source: "prometheus", field: "kri_http_request_errors_total", reason: "no series returned" },
      ],
    } as RawMetricsSnapshot;
    render(<App client={fakeApi({ queryMetrics: vi.fn().mockResolvedValue(metrics) })} />);
    await user.click(screen.getByRole("button", { name: "Query live metrics" }));

    expect(await screen.findByText("Missing data — not zero")).toBeInTheDocument();
    expect(screen.getAllByText(/no series returned/)).not.toHaveLength(0);
    expect(screen.getByRole("img", { name: /container_cpu_usage_seconds_total trace/ })).toBeInTheDocument();
  });

  it("keeps analysis usable while RAG is disabled", async () => {
    const user = userEvent.setup();
    render(<App client={fakeApi()} />);
    await user.click(screen.getByLabelText("Enable RAG"));

    expect(screen.getByRole("button", { name: "Retrieve M8 evidence" })).toBeDisabled();
    expect(screen.getByText(/M8 and M9 are intentionally paused/)).toBeInTheDocument();
  });

  it("shows structured operation errors", async () => {
    const user = userEvent.setup();
    const failure = new ApiError(
      "Deploy workload",
      502,
      "external_dependency_error",
      "kubectl failed",
      ["context unavailable"],
    );
    render(<App client={fakeApi({ deployWorkload: vi.fn().mockRejectedValue(failure) })} />);
    await user.click(screen.getByRole("button", { name: "Deploy / update" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Deploy workload: HTTP 502 · external_dependency_error: kubectl failed — context unavailable",
    );
  });

  it("reports FastAPI startup failures immediately", async () => {
    const failure = new ApiError(
      "Connect to FastAPI",
      null,
      "network_error",
      "connection refused",
    );
    render(<App client={fakeApi({ health: vi.fn().mockRejectedValue(failure) })} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "FastAPI unavailable — Connect to FastAPI: network_error: connection refused",
    );
  });
});
