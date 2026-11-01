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
- Schema version
- Experiment ID
- Workload configuration
- Load configuration
- Start/end timestamps
- Lifecycle state: `running`, `stopped`, `succeeded`, or `failed`

Experiment IDs are lowercase DNS-label-safe identifiers. A running record has no
end timestamp; terminal records have a UTC end timestamp.

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

## EvidenceBundle
- Retrieval query
- Retrieved document/chunk IDs
- Supporting passages
- Retrieval scores and metadata

## LLMInputPackage
- Observation reference
- Deterministic findings
- Numerical recommendations
- Retrieved evidence
- Risks and uncertainty

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
