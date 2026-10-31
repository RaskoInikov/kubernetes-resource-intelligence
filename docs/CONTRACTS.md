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
- Cluster and workload identity
- Deployment UID and resourceVersion
- Pod identities
- Container resources
- Readiness and restarts
- Kubernetes events

## RawMetricsSnapshot
- Source and workload identity
- Observation interval
- Metric name, labels, units
- Timestamped samples

## ObservationSnapshot
- Schema version
- Workload snapshot
- Normalized time series
- Data quality report
- Provenance

## AnalysisReport
- Calculated statistics
- Data sufficiency
- Detected conditions
- Supporting observations
- Bounded recommendations
- Risks and uncertainties

## KnowledgeDocument
- Document ID and type
- Source and version
- Verification status
- Content and metadata

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
