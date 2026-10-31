# Implementation Roadmap

Implement milestones sequentially.

M0 — Repository setup, contracts, documentation, verification.
M1 — Disposable application and workload control.
M2 — Prometheus monitoring infrastructure.
M3 — Kubernetes and Prometheus collectors.
M4 — Data normalization and observation storage.
M5 — Deterministic Python analyzer.
M6 — Canonical knowledge repository.
M7 — Qdrant indexing and knowledge inspection API.
M8 — RAG retrieval and evaluation.
M9 — Validated LLM input builder.
M10 — FastAPI integration.
M11 — React two-panel interface.

## M0 Acceptance Criteria

- The installable Python package uses a `src` layout and declares Python 3.12
  or newer plus bounded runtime and development dependencies.
- Local configuration is loaded from environment variables or an uncommitted
  `.env` file, uses the `KRI_` prefix, and rejects missing or malformed values.
- The repository has reserved locations for Python code, tests, deployment
  assets, knowledge, generated results, and the future frontend without
  implementing later milestones.
- A documented command runs formatting, linting, strict type checking, and
  offline tests with branch coverage.
- Configuration tests cover successful loading and validation failures without
  contacting Kubernetes, Prometheus, Qdrant, or Ollama.
- Product, architecture, contracts, roadmap, and progress documents are
  consistent about the first-phase boundary and M0 status.

## M1 Acceptance Criteria

- A disposable HTTP application can be built as a container and deployed to an
  explicitly configured, pre-existing Kubernetes context and namespace.
- CPU and memory requests and limits plus replica count are validated before a
  Deployment manifest is submitted; requests cannot exceed their limits.
- Load configuration is independent of incident labels and supports `cpu`,
  `memory`, and `mixed` behavior with validated concurrency, request rate, and
  duration.
- Load scheduling keeps no more than the configured concurrency in flight and
  does not extend shutdown to drain queued arrivals after the duration expires.
- Load runs as a separately managed Kubernetes Job. Starting or stopping load
  does not create, update, or delete the application Deployment or Service.
- Every experiment has a safe unique identifier and a versioned JSON record
  containing workload/load configuration, UTC timestamps, and lifecycle state.
- Kubernetes commands always include the configured context and namespace and
  mutate only fixed, project-owned resource names or a validated experiment Job.
- Offline tests verify contract rejection, rendered resource safety, independent
  lifecycle behavior, persistence, and command failures without a live cluster.
- A documented opt-in procedure distinguishes manifest/offline verification
  from real-cluster verification and requires explicit approval before mutation.

## M2 Acceptance Criteria

- The disposable application exposes Prometheus text metrics for HTTP request
  throughput, errors, and a request-duration histogram without counting its own
  metrics scrapes.
- Application Pods carry explicit scrape annotations and stable workload,
  component, namespace, pod, route, method, and status labels where applicable.
- A project-owned, disposable Prometheus deployment discovers only annotated
  application Pods in the configured workload namespace and scrapes kubelet
  cAdvisor through the Kubernetes API server.
- cAdvisor ingestion retains CPU usage, CPU CFS periods/throttled periods,
  throttled seconds, and memory working set; missing series are never synthesized.
- Prometheus uses bounded resources, six-hour retention, ephemeral storage,
  non-root execution, and narrowly scoped node-proxy/pod-discovery RBAC.
- Canonical PromQL is documented for CPU cores, CPU throttle ratio and seconds,
  memory working set bytes, HTTP requests/errors per second, and latency p95.
- Offline tests cover exposition success/error behavior, histogram semantics,
  scrape annotations/configuration, required series, queries, and malformed
  monitoring assets without contacting a cluster.
- Real-service verification is opt-in, separately reported, and must prove
  non-empty real series for every required signal before M2 is called
  cluster-verified.

## M3 Acceptance Criteria

- The Kubernetes collector performs only namespaced read operations with an
  explicit context and captures the Deployment UID/resourceVersion, Pod UIDs,
  container requests/limits, readiness, restarts, and related events.
- Kubernetes observations carry a UTC collection timestamp and explicit
  cluster, namespace, and Deployment identity; optional absent fields are
  reported as missing data rather than invented.
- The Prometheus collector uses the HTTP query API without mutating monitoring
  state and retrieves the raw M2 CPU, throttling, memory, HTTP, error, and
  latency source series over an explicit UTC interval.
- Prometheus selectors are restricted to the collected workload namespace,
  workload job, application container, and observed Pod names. Returned raw
  samples retain their labels, units, and source timestamps.
- Every expected source family has an explicit collected-or-missing outcome.
  Empty query results are valid missing data and are never replaced with zero.
- Transport failures, command failures, malformed external responses, invalid
  timestamps, and identity mismatches fail explicitly without producing a
  partial snapshot that appears complete.
- Offline tests cover successful collection, exact read-only commands and
  selectors, timestamp/identity preservation, missing data, and malformed or
  failed external responses without contacting Kubernetes or Prometheus.

## Completion Rules

Each milestone must:
- Implement its defined behavior.
- Include relevant tests.
- Pass project verification.
- Update documentation and progress.
- Preserve existing working components.

Do not implement future milestones automatically.

## Final Acceptance

The user can configure a disposable workload, generate real
Kubernetes metrics, inspect graphs, collect observations,
run deterministic analysis, retrieve RAG evidence, and inspect
the final LLM input package.

LLM inference and remediation are not included.
