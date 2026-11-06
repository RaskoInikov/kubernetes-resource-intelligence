# Data Contracts

All persisted contracts must be versioned.

## WorkloadConfiguration
- Schema version
- CPU request and limit
- Memory request and limit
- Replica count

CPU and memory requests must not exceed their corresponding limits. Quantities
use Kubernetes CPU (`m` or cores) and binary memory (`Ki`, `Mi`, `Gi`) units.

## LoadConfiguration
- Schema version
- Workload mode: `cpu`, `memory`, or `mixed`
- Positive integer concurrency
- Positive request rate in requests per second
- Positive duration in seconds

The generator keeps at most `concurrency` requests in flight. Scheduled arrivals
are skipped while all workers are occupied rather than accumulated in an
unbounded queue. It stops scheduling at the configured duration, and each
request timeout is capped by the remaining experiment time.

## ExperimentRecord
- Schema version (`1.1` for lifecycle-provenance fields; retained `1.0`
  artifacts remain readable)
- Experiment ID
- Workload configuration
- Load configuration
- Controller submission timestamp, Kubernetes Job start timestamp, and terminal
  timestamp
- Lifecycle state: `running`, `stopped`, `succeeded`, or `failed`
- Kubernetes Job UID
- Terminal reason, optional terminal message, and termination source

Experiment IDs are lowercase DNS-label-safe identifiers. A running record has no
end timestamp or termination fields. Version 1.1 terminal records have a UTC end
timestamp, non-empty reason, and source (`kubernetes` or `controller`). Successful
and failed Job timestamps and reasons come from Job status conditions, with
`completionTime` preferred for success. Explicit stop and submission failure use
the controller clock and stable reasons `UserStopped` and `SubmissionFailed`.
The submission timestamp is immutable; `job_start_timestamp` records Kubernetes
`status.startTime` when it becomes available.

## WorkloadSnapshot
- Schema version and UTC observation timestamp
- Cluster, namespace, Deployment name, and Deployment UID identity
- Deployment UID and resourceVersion
- Pod identities
- Container resources
- Readiness and restarts
- Kubernetes events
- Explicit missing-data entries for absent optional observations

## RawMetricsSnapshot
- Schema version, Prometheus source, and workload identity
- UTC collection timestamp and observation interval
- Metric name, labels, units
- Timestamped samples
- Explicit missing-data entries for expected source families with no series

M2 source series and units are:

- `container_cpu_usage_seconds_total`: cumulative CPU seconds per container.
- `container_cpu_cfs_periods_total`: cumulative CFS periods per container.
- `container_cpu_cfs_throttled_periods_total`: cumulative throttled CFS periods.
- `container_cpu_cfs_throttled_seconds_total`: cumulative throttled seconds.
- `container_memory_working_set_bytes`: working-set bytes per container.
- `kri_http_requests_total`: cumulative requests by method, route, and status.
- `kri_http_request_errors_total`: cumulative HTTP 4xx/5xx requests.
- `kri_http_request_duration_seconds`: request-duration histogram in seconds.

Prometheus-derived rates remain derived values, not raw observations. M2 stores
the source series in Prometheus; M3 will retrieve them into this snapshot contract.

M3 collectors never manufacture samples. A missing-data entry identifies the
source, field or metric family, and reason. Collector transport/protocol errors
fail the collection; a successful empty Prometheus result is recorded as
missing data. Raw metric values are finite numbers and sample timestamps are UTC.
Prometheus range evaluation timestamps and stored interval boundaries use the
service's millisecond precision so legitimate boundary samples remain inside
their declared interval.

## ObservationSnapshot
- Schema version, safe observation ID, and UTC creation timestamp
- Embedded raw `WorkloadSnapshot` and `RawMetricsSnapshot`
- Deterministically ordered normalized time series with canonical signal name,
  source metric, metric kind, unit, aggregation scope, stable labels, and the
  unchanged source samples
- Versioned data quality report with `complete`, `degraded`, or `insufficient`
  status and structured severity/code/source/field/message issues
- Versioned provenance with source schema versions/timestamps, builder version,
  and a SHA-256 digest of the canonical raw inputs

Normalization is structural. It removes incidental scrape/runtime labels from
the normalized view but preserves them in the embedded raw snapshot. It does
not calculate rates, aggregate Pods or containers, repair counters, interpolate
gaps, or replace missing values. Replay rebuilds the normalized series, quality
report, and provenance from the embedded raw inputs and requires an exact match.

## AnalysisReport
- Schema version, safe analysis ID, observation ID, workload identity, and UTC
  creation timestamp
- Analyzer version, policy version, and source observation digest
- Data sufficiency: `sufficient`, `partial`, or `insufficient`
- Deterministic statistics with value, unit, aggregation scope, labels, and
  evidence IDs
- Detected resource conditions with severity, explicit threshold/comparison,
  statistic IDs, and evidence IDs
- Evidence records identifying normalized signal labels/sample intervals or
  Kubernetes resource fields
- Increase-only bounded recommendations with current/recommended/lower/upper
  Kubernetes quantities, condition/statistic/evidence IDs, rationale, and an
  explicit-approval requirement
- Risks and uncertainties, including M4 quality issues and unavailable required
  calculations

M5 uses policy version `1.1`: CPU throttling is detected at a throttled-period
ratio of 0.20, CPU limit saturation at peak/limit 0.90, memory limit pressure at
max/limit 0.90, and request mismatch at CPU-average/request or
memory-p95/request 1.20. Critical severity begins at throttling 0.50, limit
utilization 1.0, and request utilization 1.50; lower detected values are
warnings. CPU counter peaks coalesce repeated range evaluations and exclude the
first potentially partial update when later update intervals are available.
Recommendations never decrease a resource and never exceed twice its current
value. CPU recommendations round upward to 10m and memory recommendations to
1Mi. Resource statistics remain per Pod/container; only HTTP statistics
aggregate across Pods. Risks identify finite observation windows, limited
scrape resolution, findings within 5% of a decision boundary, and headroom
targets constrained by current limits. Recommendations also state that their
effects remain unvalidated until an approved post-change experiment.

## KnowledgeDocument
- Schema version, DNS-safe document ID, type, title, and semantic version
- Type: `kubernetes_documentation`, `diagnostic_runbook`, or
  `historical_incident`
- Verification status: `verified`, `needs_review`, or `deprecated`
- Verifier identity and UTC verification timestamp for verified documents
- Stable unique tags, concise summary, and complete Markdown content
- One or more explicit provenance records containing source ID/type, title,
  publisher, URI, source version, UTC access time, and verification notes

## KnowledgeRepositoryManifest
- Schema version, semantic repository version, and UTC release timestamp
- Deterministically ordered document entries containing all KnowledgeDocument
  metadata plus a repository-relative Markdown path and SHA-256 content digest
- Unique document IDs, paths, source IDs, and tags
- At least one registered document of every required M6 type

The M6 repository accepts only paths contained beneath its configured root,
requires `.md` files with a matching top-level title, validates exact content
digests, rejects unregistered Markdown, and never edits source documents while
loading or inspecting them. A `verified` entry must name its verifier and UTC
verification time. `needs_review` material cannot claim verification metadata.

## KnowledgeChunk
- Schema version, deterministic chunk ID and Qdrant point UUID
- Repository version, document ID/type/title/version, verification status, tags,
  and source provenance
- Section heading, zero-based ordinal, exact non-empty text, and SHA-256 digest
- Chunker version, embedder version, exact pretrained model name, and fixed
  vector dimension

## KnowledgeIndexSummary
- Collection name, repository version, index schema/chunker/embedder versions,
  and exact pretrained model name
- Vector dimension and distance metric
- Canonical document count, generated chunk count, upserted point count, and
  stale project-owned point deletion count

## KnowledgeIndexStatus
- Configured collection name and existence
- Existing collection vector dimension, distance metric, and point count
- No synthetic schema metadata when the collection is absent

## KnowledgeRetrievalResult
- Non-empty query and bounded result limit
- Repository, collection, index schema, and embedder versions
- Ordered hits with score, exact chunk identity/text/digest, document metadata,
  verification status, tags, section, and source provenance
- M8-reranked hits additionally retain the original semantic score and lexical
  match ratio; either both component scores are present or neither is

M7 retrieval returns only `verified` documents unless a future explicit
contract broadens that policy. Scores must be finite and non-increasing. Qdrant
payloads are validated back into KnowledgeChunk contracts; malformed or foreign
payloads never become retrieval evidence.

## OperationalEvidenceBundle
- Stable query ID and query kind (`recommendation` or `condition`)
- Source recommendation or condition-type identity
- Originating analysis/observation, condition, statistic, and analysis-evidence
  IDs
- Exact validated M7 retrieval result, including query, scores, chunks, source
  provenance, repository version, index schema, and embedding model

## OperationalEvidencePackage
- Retrieval schema/retriever version and UTC creation timestamp
- Analysis identity, observation identity, analysis source digest, and
  sufficiency
- Deterministically ordered evidence bundles; analyses without findings produce
  an explicit empty package rather than invented evidence

## RetrievalEvaluationDataset
- Semantic dataset version, repository version, index schema, embedding model,
  UTC review time, author, independent reviewer, and review notes
- Fixed, uniquely identified queries with bounded `k` and one or more graded
  relevant chunk judgments
- Author and reviewer identities must differ; duplicate cases or judgments are
  invalid

## RetrievalEvaluationReport
- Dataset version and canonical SHA-256 digest plus repository/index/model
  identity and UTC evaluation timestamp
- Per-case returned chunk IDs/scores, relevant retrieved IDs, Recall@k, MRR@k,
  and nDCG@k; each hit retains final, semantic, and lexical scores
- Aggregate mean metrics, explicit minimum thresholds, and pass/fail status

## LLMInputPackage
- Schema/builder version, safe package ID, and UTC creation timestamp
- Exact workload, analysis, and observation identity plus analyzer/policy and
  retrieval versions
- Canonical SHA-256 digests of the complete M5 analysis and M8 evidence inputs
- Exact M5 sufficiency, conditions, recommendations, risks, and uncertainties
- Minimal referenced statistics and analysis evidence with original numerical
  values, units, labels, intervals, and evidence IDs
- Explicit retrieval status: `retrieved`, `no_hits`, or `no_findings`
- Deterministic M8 query references with originating finding IDs and retrieved
  versus included hit counts
- Bounded ranked hit references with final/semantic/lexical scores and selected
  excerpt status
- Deduplicated bounded knowledge excerpts with chunk/point/document identity,
  exact text digest, source provenance, query IDs, and explicit truncation
- Fixed machine-readable instructions forbidding numerical invention,
  autonomous remediation, and presentation of uncertainty as confirmed fact

## LLMInputArtifact
- Exact `LLMInputPackage`
- Canonical SHA-256 digest of the complete package

Loading rejects any package-content change, including altered numbers,
references, risks, uncertainty, or evidence text. Persistence refuses overwrite
and inspection returns counts and identities rather than the full LLM payload.

## M12 Inference Contracts

### InferenceRunArtifact

- Safe run ID, schema/prompt/adapter versions, UTC requested/start/end times,
  and terminal status
- Exact M9 package ID and digest plus canonical digest of the complete input
- Ollama endpoint identity, exact Qwen3 model name and locally reported digest,
  context limit, and complete bounded inference options
- Exact rendered-message digest, raw response, response digest, token/timing
  metadata when reported, and explicit transport/model failure
- Parsed candidate as a distinct optional value; parse failure never changes
  the raw response or becomes an accepted explanation
- Explicit RAG mode (`on` or `off`) and a canonical prompt digest. RAG-off keeps
  the complete M9 deterministic analysis but excludes knowledge excerpts from
  the rendered prompt.

### LLMOutputCandidate and ValidationReport

- Candidate schema version and source run/package identities
- Explanation sections tied to exact M5 condition/recommendation IDs
- Structured numerical claims with value, unit, and statistic/evidence ID
- Structured citations to supplied analysis evidence or M8 knowledge chunks
- Explicit uncertainty references and a statement that resource changes require
  approval
- Validator version, validated source digests, UTC validation time, pass/fail
  status, and deterministically ordered issues
- Issues identify unsupported IDs, values, units, recommendations, citations,
  missing uncertainty, schema violations, and source mismatch without rewriting
  the candidate
- Accepted output exists only when the complete report passes and retains the
  candidate and validation-report digests

M12 records Ollama's exact lowercase 64-character model digest from
`/api/tags`. Generated prose cannot contain undeclared numbers: every numerical
claim must be structured and exactly match its referenced M5 statistic value
and unit. Condition and recommendation citations must exactly cover their M5
analysis evidence; knowledge citations are allowed only for supplied M9 chunks
in RAG-on mode. Every M9 uncertainty ID and source text must be preserved.

Accepted, rejected, malformed, interrupted, and dependency-failed attempts are
stored as immutable digest envelopes. Rejected candidates remain inspectable;
only an accepted status can carry an `AcceptedLLMOutput` digest binding.

## M13 Quality-Evaluation Contracts

Prompt 1.5 raw output is a compact positional response. Exact schema array
bounds prevent merged or omitted findings, and printable digit-free regular
expressions bound the summary to 120 characters and each explanation to 72
characters. RAG-off permits no knowledge chunk IDs; RAG-on IDs are limited to
chunks in the source M9 package. The adapter copies deterministic M9 fields into
the candidate and never changes generated prose or chunk choices. Complete JSON
returned at Ollama's token boundary remains eligible for ordinary parsing and
validation; truncated JSON still fails as `ollama_incomplete`. Historical M13
dataset 1.0.0 replay remains pinned to prompt 1.4.

`LLMQualityDataset` records a semantic version, canonical digest, distinct
author/reviewer identities, review timestamps, leakage notes, source package
identities, fixed model/prompt/options/trial count, and reviewed labels for
facts, findings, uncertainties, recommendations, citations, exclusions, and
provenance.

`LLMQualityEvaluationReport` retains every planned trial, source and inference
artifact digest, status/failure, UTC interval, latency, validation issues, and
available deterministic scores. Failed output remains in the trial and pair
counts while unavailable candidate metrics stay explicitly missing. Aggregate
comparisons record RAG-on/off means, paired differences, standard deviation,
comparable/missing pair counts, direction, and improved, regressed, or
inconclusive outcome.

## Planned M14–M17 Contracts

The following contracts remain planned. Their concrete schema versions are
introduced by their owning milestones without changing historical artifacts.

### LLMQualityDataset and EvaluationReport

- Semantic dataset version, canonical digest, author, independent reviewer,
  review timestamp, case provenance, exclusion rules, and leakage notes
- Cases identify source M5 analysis, paired RAG-on/RAG-off M9 inputs, expected
  facts/uncertainties/recommendations, allowed citations, trial count, and fixed
  model/prompt settings
- Trial records retain pair/configuration IDs, M9/M12 artifact digests, UTC
  times, status/failure, latency, and every scoring denominator
- Per-trial and aggregate validation success, supported numerical claims,
  unsupported-claim rate, citation precision/recall, finding/uncertainty
  coverage, recommendation consistency, and generation latency
- Paired absolute/relative differences, variability, sample and failure counts,
  thresholds, and improved/regressed/inconclusive outcomes per dimension

### RecommendationEffectivenessPlan and Report

- Plan/policy version, safe plan ID, source analysis/recommendation/evidence
  identities and digests, creator and UTC time
- Cluster/context, namespace, workload/image identity, exact baseline and
  candidate configurations, intended differences, repeated load plan,
  observation windows, stop conditions, rollback, cleanup, and artifact roots
- Exact proposed Kubernetes mutations and separate explicit-approval record;
  no model-generated value is accepted
- Trial references bind lifecycle-reconciled ExperimentRecords and immutable
  Observations with roles, repetitions, timestamps, and source digests
- Report records comparability/quality checks, confounders, per-trial and
  aggregate throughput, p95 latency, throttling, CPU, memory, errors,
  readiness/restarts, target attainment, absolute/relative effects and
  variability
- Versioned guardrails yield `effective`, `ineffective`, `harmful`, or
  `inconclusive`; rollback and cleanup status are separate from the outcome

### ArtifactCatalog and LineageGraph

- Catalog schema/build version, safe catalog ID, UTC build time, configured-root
  identities, source scan digest, and deterministic entry ordering
- Entries contain artifact type/schema, stable ID, UTC times, status, workload
  and experiment identities when applicable, content/source digests, and a safe
  root-relative locator
- Structured issues retain unsupported, invalid, corrupt, duplicate, orphaned,
  drifted, or unsafe artifacts instead of silently omitting them
- Lineage nodes reference catalog entries; directed edges contain an explicit
  relationship type, parent ID, expected parent digest, and validation status
- Graph validation rejects cycles and reports broken or incompatible links;
  filenames and timestamps alone never establish a relationship
- List/query contracts use bounded page size, opaque or stable continuation,
  deterministic filters/sort, total-count semantics, and bounded summaries

### BackendOperation and AcceptanceReport

- Operation schema/version, safe operation and idempotency IDs, operation type,
  queued/running/succeeded/failed/cancelled status, UTC lifecycle timestamps,
  progress, input digests, result artifact references, and structured failure
- Bounded-concurrency, timeout, cancellation, retry, and restart-reconciliation
  metadata; terminal state and immutable result references cannot be rewritten
- Acceptance report schema/suite version, environment and dependency identities,
  UTC interval, exact commands/checks, offline/real/retained evidence class,
  artifact digests, pass/fail/skip result, limitations, cleanup status, and
  overall backend-acceptance decision
- A skipped, failed, or inconclusive mandatory M12–M17 check cannot produce an
  accepted backend decision

## M10 HTTP Requests
- Every route is under `/api/v1`; `/healthz` is the unversioned process-health
  exception.
- Workload deployment accepts `WorkloadConfiguration`; starting load accepts
  exact workload/load contracts plus an optional safe experiment ID.
- Live-metrics and observation requests contain a schema version, ordered UTC
  interval spanning at least Prometheus's one-millisecond precision, and a step
  from 1 through 60 seconds. Observation creation additionally accepts an
  optional safe observation ID.
- Analysis creation references one stored observation and an optional safe
  analysis ID.
- RAG creation carries one complete validated `AnalysisReport` and a result
  limit from 1 through 20; no server-side implicit analysis lookup occurs.
- LLM-input creation carries the complete M5 report, matching M8 evidence, and
  an optional safe package ID.

Successful API bodies reuse the existing M1-M9 contracts. Mutation
acknowledgements and errors are structured, versioned objects. Validation
failures use HTTP 422, missing immutable artifacts use 404, artifact/lifecycle
conflicts use 409, and external Kubernetes/Prometheus/Qdrant failures use 502.
No endpoint converts absent samples to zero or a recommendation into an applied
resource change.

## Invariants

- Store timestamps in UTC.
- Preserve explicit metric units and aggregation scope.
- Never substitute missing values with zero.
- Keep raw observations separate from derived statistics.
- Never mix aggregate usage with per-container limits.
- Preserve historical workload identities.
- Never promote unverified LLM results to confirmed knowledge.
- Never treat an unregistered, checksum-invalid, or `needs_review` knowledge
  document as canonical verified evidence.
- Never treat Qdrant state as canonical, delete foreign points during sync, or
  return unverified/malformed payloads as retrieved evidence.
- Never detach retrieved operational evidence from the deterministic finding
  that requested it or tune evaluation judgments from the system's own results.
- Never let the LLM input builder recalculate deterministic values, suppress a
  reported uncertainty, invent missing retrieval evidence, or hide bounded
  evidence omissions.
- Never treat raw or merely parseable LLM output as validated, repair a failed
  candidate silently, or allow an LLM value to become a Kubernetes mutation.
- Never compare RAG configurations with different deterministic inputs or hide
  invalid trials from evaluation denominators.
- Never report a recommendation as effective from incomparable, missing, or
  unstable experiment evidence.
- Never infer lineage from filenames, let a derived catalog replace an owning
  artifact, or expose a path outside configured artifact roots.
