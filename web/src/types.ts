export type JsonObject = Record<string, unknown>;

export interface WorkloadConfiguration {
  schema_version: "1.0";
  cpu_request: string;
  cpu_limit: string;
  memory_request: string;
  memory_limit: string;
  replicas: number;
}

export interface LoadConfiguration {
  schema_version: "1.0";
  workload_mode: "cpu" | "memory" | "mixed";
  concurrency: number;
  request_rate: number;
  duration_seconds: number;
}

export interface WorkloadIdentity {
  cluster: string;
  namespace: string;
  deployment_name: string;
  deployment_uid: string;
}

export interface MissingData {
  source: "kubernetes" | "prometheus";
  field: string;
  reason: string;
}

export interface WorkloadSnapshot extends JsonObject {
  observed_at: string;
  identity: WorkloadIdentity;
  deployment_resource_version: string;
  pods: Array<{ name: string; ready: boolean | null; restart_count: number | null }>;
  container_resources: Array<Record<string, string | null>>;
  missing_data: MissingData[];
}

export interface ExperimentRecord extends JsonObject {
  schema_version: "1.0" | "1.1";
  experiment_id: string;
  lifecycle_state: "running" | "stopped" | "succeeded" | "failed";
  start_timestamp: string;
  job_uid: string | null;
  job_start_timestamp: string | null;
  end_timestamp: string | null;
  termination_reason: string | null;
  termination_message: string | null;
  termination_source: "kubernetes" | "controller" | null;
}

export interface MetricSample {
  timestamp: string;
  value: number;
}

export interface MetricSeries {
  metric_name: string;
  labels: Record<string, string>;
  unit: string;
  samples: MetricSample[];
}

export interface RawMetricsSnapshot extends JsonObject {
  collected_at: string;
  interval_start: string;
  interval_end: string;
  identity: WorkloadIdentity;
  series: MetricSeries[];
  missing_data: MissingData[];
}

export interface ObservationSnapshot extends JsonObject {
  observation_id: string;
  created_at: string;
  quality_report: { status: string; issues: Array<Record<string, unknown>> };
  normalized_series: unknown[];
  provenance: { source_digest_sha256: string };
}

export interface ObservationSummary extends JsonObject {
  observation_id: string;
  created_at: string;
  identity: WorkloadIdentity;
  interval_start: string;
  interval_end: string;
  quality_status: string;
  issue_count: number;
  normalized_series_count: number;
  sample_count: number;
}

export interface CalculatedStatistic extends JsonObject {
  statistic_id: string;
  name: string;
  value: number;
  unit: string;
  aggregation_scope: string;
}

export interface DetectedCondition extends JsonObject {
  condition_id: string;
  condition_type: string;
  severity: "warning" | "critical";
  message: string;
  observed_value: number;
  threshold: number;
}

export interface ResourceRecommendation extends JsonObject {
  recommendation_id: string;
  resource: string;
  current_value: string;
  recommended_value: string;
  rationale: string;
  requires_approval: true;
}

export interface AnalysisReport extends JsonObject {
  analysis_id: string;
  observation_id: string;
  created_at: string;
  sufficiency: string;
  statistics: CalculatedStatistic[];
  conditions: DetectedCondition[];
  recommendations: ResourceRecommendation[];
  risks_and_uncertainties: string[];
}

export interface RetrievalHit {
  score: number;
  semantic_score: number | null;
  lexical_match_ratio: number | null;
  chunk: {
    chunk_id: string;
    document_id: string;
    document_title: string;
    section: string;
    verification_status: string;
    text: string;
    sources: Array<{ title: string; uri: string }>;
  };
}

export interface EvidenceBundle {
  query_id: string;
  query_kind: string;
  query: string;
  retrieval: { hits: RetrievalHit[] };
}

export interface OperationalEvidencePackage extends JsonObject {
  analysis_id: string;
  observation_id: string;
  created_at: string;
  bundles: EvidenceBundle[];
}

export interface LLMInputPackage extends JsonObject {
  package_id: string;
  analysis_id: string;
  observation_id: string;
  created_at: string;
  sufficiency: string;
  retrieval_status: string;
  analysis_digest_sha256: string;
  operational_evidence_digest_sha256: string;
  statistics: CalculatedStatistic[];
  conditions: DetectedCondition[];
  recommendations: ResourceRecommendation[];
  risks_and_uncertainties: string[];
  retrieval_queries: unknown[];
  retrieval_hits: unknown[];
  evidence_excerpts: unknown[];
}

export interface LLMInputSummary extends JsonObject {
  package_id: string;
  created_at: string;
  analysis_id: string;
  observation_id: string;
  sufficiency: string;
  retrieval_status: string;
  statistic_count: number;
  condition_count: number;
  recommendation_count: number;
  uncertainty_count: number;
  query_count: number;
  hit_reference_count: number;
  excerpt_count: number;
  package_sha256: string;
}
