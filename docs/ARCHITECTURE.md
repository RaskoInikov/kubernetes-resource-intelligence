# Architecture

## Pipeline

1. Kubernetes workload and load generator.
2. Prometheus metrics collection.
3. Kubernetes API configuration and events.
4. Data normalization and quality validation.
5. Versioned observation snapshot.
6. Deterministic Python analyzer.
7. Qdrant knowledge retrieval.
8. LLM input package.
9. FastAPI and React presentation.

## Responsibilities

### Workload Controller
Creates and controls disposable Kubernetes experiments.

In M1 it renders a fixed-name application Deployment and Service and a unique
load Job. It invokes `kubectl` with an explicit context and namespace, persists
versioned experiment records as JSON artifacts, and never creates namespaces.
Stopping a load experiment deletes only its Job; application removal is a
separate operation. The target application and load generator share a small,
buildable test image but run as separate Kubernetes workloads.

The load generator is rate-controlled but never queues beyond its configured
concurrency. When the target is throttled or slow, excess scheduled arrivals are
skipped and in-flight request timeouts are limited by the remaining configured
duration so executor shutdown cannot drain an accumulated backlog.

### Prometheus Collector
Retrieves real workload time series.

M2 establishes collection infrastructure but not the M3 Python collector. A
project-owned Prometheus discovers annotated `kri-workload` Pods and scrapes
kubelet cAdvisor through the API-server node proxy. It retains only the required
container CPU/throttling/working-set series and the application's HTTP counters
and latency histogram. Storage is an ephemeral six-hour TSDB; no missing value
is generated or replaced with zero.

In M3 the Python collector calls only Prometheus's read-only range-query API.
Queries are scoped to the explicit workload namespace/job, application
container, and Pod identities obtained from Kubernetes. It preserves raw sample
timestamps, values, labels, and units and reports empty expected families as
missing instead of synthesizing samples.

### Kubernetes Collector
Reads Deployment configuration, Pods, resources, and events.

In M3 it invokes only namespaced `kubectl get` operations with an explicit
context. The Deployment UID is the durable workload identity carried into both
collector snapshots; resourceVersion identifies the observed live revision.
Command or schema failures are explicit, while absent optional resource values,
Pod observations, or event timestamps are represented as missing data.

### Observation Builder
Normalizes and validates collected information.

In M4 it combines identity-matched Kubernetes and Prometheus snapshots into an
immutable versioned observation. Raw inputs remain embedded; a separate
deterministic normalized view maps source metrics to canonical signals and
stable workload scopes without calculating derived values. Structured quality
issues distinguish missing, insufficient, reset, malformed, and collision
conditions. Provenance hashes the canonical raw inputs.

The observation store writes one JSON artifact per safe observation ID using
atomic replacement of a temporary file, refuses overwrites, validates source
digests on load, exposes a bounded inspection summary, and deterministically
replays embedded inputs to detect artifact tampering or builder drift.

### Python Analyzer
Calculates statistics, findings, and bounded recommendations.

In M5 it first replay-validates a stored M4 observation, then calculates
per-Pod/container CPU, throttling, and memory statistics plus workload-level
HTTP context. Counter resets and insufficient samples suppress dependent values;
they are never repaired. Repeated range evaluations are coalesced for CPU peak
rates so a query step finer than scrape cadence does not inflate peaks. A
versioned policy applies explicit detection and severity thresholds and emits
only detected conditions, never negative findings from absent data.

Recommendations are deterministic, increase-only, rounded to Kubernetes units,
capped at twice the current resource, and always marked as requiring approval.
Every statistic, condition, and recommendation references exact series/resource
evidence. M5 does not mutate Kubernetes or use an LLM.
Reports explicitly retain finite-window, scrape-resolution, near-threshold, and
recommendation-constraint uncertainty.

### Knowledge Repository
Maintains readable documentation, runbooks, and incidents.

### Qdrant Retriever
Retrieves relevant knowledge with source references.

### LLM Input Builder
Constructs concise, traceable input for a future LLM.

### FastAPI
Exposes workload, monitoring, analysis, and knowledge APIs.

### React
Provides workload controls, live graphs, and analysis views.

## Storage

- Prometheus: time series.
- Kubernetes API: live configuration and state.
- JSON artifacts: reproducible observations and experiments.
- Markdown/JSON: canonical knowledge.
- Qdrant: embeddings and searchable knowledge payloads.

No ClickHouse, crawler, or additional database.

## Project Foundation

- Python code is an installable `src/kri` package targeting Python 3.12+.
- Process configuration comes from `KRI_` environment variables, with `.env`
  supported only as a local-development convenience.
- Configuration validation happens before a component contacts an external
  service.
- Python collectors, observation building, analysis, retrieval, API, and
  frontend behavior remain outside M2.
