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
  containing workload/load configuration, controller and Kubernetes UTC
  timestamps, Job identity, lifecycle state, and terminal reason provenance.
- Reconciliation uses Kubernetes Job conditions and their timestamps, preserves
  exact failure reasons/messages, is idempotent for terminal records, and checks
  terminal state before an explicit stop deletes a Job.
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

## M4 Acceptance Criteria

- An observation builder accepts one Kubernetes snapshot and one raw metrics
  snapshot only when their immutable workload identities match.
- Raw source snapshots remain embedded and distinguishable from normalized
  series; normalization does not calculate rates, percentiles, statistics, or
  substitute missing samples.
- Normalized series use canonical signal names, metric kinds, units, stable
  workload label scopes, UTC timestamps, and deterministic ordering while
  preserving every source sample value.
- A versioned quality report classifies observations as `complete`, `degraded`,
  or `insufficient` and explicitly reports source missing data, absent or
  unreported metric families, insufficient counter samples, counter resets,
  malformed histogram bounds, and normalized-series collisions.
- Versioned provenance records source schema versions/timestamps, the builder
  version, and a deterministic SHA-256 digest of both raw inputs.
- Observation snapshots are stored as immutable JSON artifacts through atomic
  writes, reject unsafe IDs and overwrite attempts, and fail explicitly on
  missing, malformed, or source-digest-invalid artifacts.
- Stored observations can be inspected through a bounded summary and replayed
  deterministically from their embedded raw inputs; replay rejects normalized,
  quality, provenance, or raw-source tampering.
- Offline tests cover complete, degraded, insufficient, invalid-identity,
  normalization, persistence, inspection, corruption, and replay behavior
  without contacting Kubernetes or Prometheus.

## M5 Acceptance Criteria

- The deterministic analyzer consumes only replay-validated M4 observations and
  produces a versioned analysis report tied to the observation ID, workload
  identity, raw-source digest, analyzer version, and UTC creation timestamp.
- Per-Pod/container statistics include average and peak CPU cores, CPU request
  and limit utilization, CFS throttled-period ratio, throttled seconds/second,
  and mean/p95/max memory working set and request/limit utilization. Aggregate
  HTTP statistics include throughput, error ratio, mean latency, and histogram
  p95 for the `/work` route when their inputs are sufficient.
- Counter rates use positive deltas over real sample intervals. Reset or
  insufficient counters are excluded from dependent calculations rather than
  repaired, clamped, or interpreted as zero. CPU peaks coalesce repeated range
  evaluations so query steps finer than scrape cadence do not inflate rates.
- Conditions use versioned explicit thresholds: CPU throttling at 20%, CPU
  peak/limit at 90%, memory max/limit at 90%, and CPU-average or memory-p95
  request utilization at 120%. Missing inputs never produce a negative finding.
- Supporting evidence identifies the exact normalized series labels, interval,
  sample count, and configured resource fields used by every statistic,
  condition, and recommendation.
- Recommendations are deterministic, increase-only, require explicit approval,
  preserve request-at-or-below-limit invariants, round to Kubernetes units, and
  are capped at twice the current setting. Insufficient observations produce no
  recommendations.
- Reports distinguish sufficient, partial, and insufficient analysis and carry
  explicit risks/uncertainties derived from M4 quality issues and unavailable
  required calculations, finite windows, scrape resolution, decision-boundary
  proximity, and recommendation constraints.
- Offline tests cover threshold boundaries, per-container scope, histogram
  calculation, reset/missing data, insufficient suppression, recommendation
  rounding/caps, evidence traceability, deterministic saved-observation input,
  and malformed analysis contracts without external services.

## M6 Acceptance Criteria

- Canonical knowledge is stored as readable Markdown plus a versioned JSON
  manifest; generated embeddings and vector-database state are not canonical.
- The repository contains Kubernetes documentation, diagnostic runbooks, and
  historical incidents, with at least two documents of each type.
- Every document has a safe stable ID, semantic version, unique tags, concise
  summary, explicit verification status, and one or more source-provenance
  records with URI, publisher, source version, UTC access time, and notes.
- Verified documents identify the verifier and UTC verification time;
  unverified material cannot silently claim verified metadata.
- Manifest paths are repository-relative and contained beneath the knowledge
  root. Exact SHA-256 content digests, matching Markdown titles, unique IDs and
  paths, complete type coverage, and absence of unregistered Markdown are
  validated before documents are returned.
- A read-only Python repository loads, lists, retrieves, and summarizes
  documents deterministically and fails explicitly for missing, malformed,
  unsafe, duplicate, checksum-invalid, or incomplete repositories.
- Kubernetes reference material distinguishes scheduling requests from runtime
  limits. Runbooks preserve missing-data uncertainty and require post-change
  verification. Incidents distinguish recorded evidence from lessons learned.
- Offline tests cover successful loading and inspection plus contract, path,
  checksum, heading, registration, coverage, and verification failures without
  Kubernetes, Prometheus, Qdrant, or network access.

## M7 Acceptance Criteria

- A deterministic versioned chunker converts every validated canonical M6
  document into ordered, non-empty Markdown-section chunks with stable IDs,
  exact text digests, document metadata, verification status, and provenance.
- A versioned local pretrained semantic embedder produces fixed-size finite
  normalized vectors, records its exact model identity, and is shared by
  indexing and retrieval. Offline tests inject a deterministic model double and
  require no weights or network access.
- Qdrant point IDs and payloads are deterministic and include project ownership,
  repository/document/chunker/embedder versions, section/ordinal, tags, sources,
  verification status, exact chunk text, and content digest.
- Synchronization creates only the configured collection, validates vector size
  and cosine distance on an existing collection, upserts current points, and
  deletes only stale project-owned points. It fails rather than deleting or
  recreating an incompatible collection.
- The canonical manifest and Markdown remain authoritative; Qdrant is derived
  state that can be rebuilt and never updates M6 verification metadata.
- A read-only Python API lists canonical documents, reports collection/index
  metadata, scrolls indexed chunks with optional document scope, retrieves an
  exact chunk, and performs bounded retrieval over verified documents.
- Retrieval validates Qdrant payloads, preserves exact chunk/source provenance,
  returns finite scores in descending order, and explicitly fails on malformed
  responses, foreign ownership, missing chunks, or transport errors.
- Offline tests use a fake Qdrant gateway and cover deterministic chunking and
  embedding, collection creation/schema mismatch, idempotent sync, stale-owned
  cleanup without foreign deletion, inspection, filters, retrieval ordering,
  malformed payloads/responses, and transport failures without external
  services.

## M8 Acceptance Criteria

- Retrieval accepts a fully validated deterministic M5 analysis and never
  recalculates statistics, conditions, or recommendations.
- Every recommendation produces one deterministic operational query; detected
  condition types not represented by recommendations also produce grouped
  queries without duplicate per-Pod retrieval.
- Every evidence bundle retains the originating analysis/observation, condition,
  statistic, and analysis-evidence IDs plus the exact verified M7 chunks,
  scores, text digests, and source provenance.
- Operational retrieval uses deterministic query-intent document scoping and a
  fixed semantic/lexical rerank while retaining both component scores.
- Insufficient or finding-free analyses return an explicit empty package;
  missing Qdrant results remain empty and are not fabricated or replaced.
- A fixed semantic-versioned dataset contains independently reviewed, graded
  chunk judgments spanning CPU, memory, metric-quality, and historical-incident
  retrieval. Author and reviewer identities must be distinct.
- Evaluation validates dataset/repository/index/model compatibility and records
  a canonical dataset SHA-256 digest and exact returned IDs/scores.
- Per-case and aggregate Recall@k, MRR@k, and nDCG@k are calculated
  deterministically against explicit minimum thresholds; a failed threshold is
  reported as a failed evaluation rather than raised or suppressed.
- Offline tests inject deterministic retrieval responses and cover query
  construction, traceability, empty/missing results, malformed analyses and
  datasets, metric boundaries, compatibility failures, and evaluation pass/fail
  behavior without model downloads, Qdrant, Kubernetes, or Prometheus.

## M9 Acceptance Criteria

- The builder accepts only a fully validated M5 analysis and matching M8
  evidence package, and rejects identity, source-digest, sufficiency, finding,
  or reference mismatches before producing an artifact.
- Every M5 condition, recommendation, and risk/uncertainty is preserved exactly;
  numerical values and units are copied without rounding, formatting, or LLM
  interpretation.
- Included statistics and analysis evidence form the complete, minimal closure
  referenced by findings, including evidence referenced by those statistics.
- Retrieved knowledge remains traceable through query/source IDs, rank, final,
  semantic, and lexical scores, chunk/point IDs, text digests, document metadata,
  and canonical source provenance.
- Knowledge text is deterministic and concise: at most the top three hits per
  query are referenced, excerpts are deduplicated by chunk, at most twelve are
  included, and each is at most 600 characters. Retrieved and included counts
  expose all truncation.
- Finding-free and no-hit inputs produce explicit retrieval status rather than
  invented evidence. Findings without corresponding M8 bundles are rejected.
- Canonical SHA-256 digests bind both complete inputs. Persisted JSON artifacts
  are versioned, immutable, atomically written, integrity-checked on load, and
  available through a bounded inspection summary.
- Offline tests cover success, exact numerical and uncertainty preservation,
  closure and retrieval traceability, deterministic bounds, empty evidence,
  mismatches, malformed inputs, immutable persistence, corruption, and
  inspection without external services or model inference.

## M10 Acceptance Criteria

- A FastAPI application exposes versioned health, workload deployment/deletion,
  load start/stop/status, current workload, raw live metrics, observation
  creation/loading/inspection, deterministic analysis, RAG evidence, and M9
  package creation/loading/inspection routes with generated OpenAPI.
- Workload mutation routes call only the existing scoped M1 controller; read and
  analysis routes do not mutate Kubernetes, and stopping load remains separate
  from application deletion.
- Live metrics and observation creation require an ordered timezone-aware
  interval and bounded Prometheus step, return raw timestamped source samples,
  preserve missing-data records, and never calculate or substitute values.
- Observation creation collects identity-matched M3 inputs, builds one M4
  snapshot, persists it immutably, and reports overwrite conflicts explicitly.
- Analysis consumes only a replay-validated stored observation. RAG consumes an
  exact M5 report, and LLM-input creation consumes exact matching M5/M8
  contracts and persists through the M9 integrity store.
- Retrieval uses an already synchronized configured Qdrant collection; no read
  endpoint creates, synchronizes, deletes, or repairs vector state.
- HTTP errors distinguish request validation, missing artifacts, lifecycle or
  immutable conflicts, and external dependency failure without returning a
  successful partial result.
- Production service construction validates `KRI_` settings before external
  contact and scopes generated artifacts beneath the configured local results
  directories. No endpoint invokes an LLM or applies a recommendation.
- Offline FastAPI tests inject fakes and cover every success route, validation,
  error mapping, component arguments, persistence behavior, and OpenAPI without
  Kubernetes, Prometheus, Qdrant, model downloads, or network services.

## M11 Acceptance Criteria

- A small React and TypeScript application provides a responsive two-column
  interface with workload configuration and live metrics on the left and the
  explicit observation, deterministic-analysis, RAG, and LLM-input workflow on
  the right.
- Workload controls expose CPU and memory requests/limits, replicas, load mode,
  concurrency, request rate, duration, optional experiment identity, deploy,
  delete, load start/status/stop, and current-workload refresh without coupling
  load stop to application deletion.
- Live metrics use a user-controlled ordered UTC interval and bounded step,
  render readable timestamped traces for the required M2 signals, and display
  missing-data records without substituting zero.
- The analysis workflow explicitly creates or loads an immutable observation,
  runs M5 from its ID, optionally runs M8 from the exact returned M5 report,
  creates M9 from the exact matching M5/M8 contracts, and loads or inspects a
  saved package by ID. Disabled stages explain their prerequisites.
- Findings, bounded approval-required recommendations, uncertainties, evidence
  queries, retrieved chunk provenance/scores, package counts/digests, and
  expandable raw responses remain inspectable. The frontend performs no
  numerical analysis or resource mutation beyond explicit M10 controls.
- Loading state prevents duplicate actions. Structured M10 errors and network
  failures remain visible with the operation that failed, while a later
  successful action clears only the relevant error.
- The API base is configurable and defaults to the Vite same-origin development
  proxy. No frontend route synchronizes Qdrant, invokes an LLM, applies a
  recommendation, or introduces authentication or production deployment.
- Local commands resolve configuration from the repository-root `.env`
  independently of working directory. The documented startup sequence provides
  actionable read-only readiness checks for Prometheus, Qdrant, and the
  configured collection, while React reports FastAPI connectivity immediately.
- Offline component/API-client tests cover successful stage chaining, RAG-off
  behavior, workload/load independence, metric and missing-data rendering, and
  structured failure display. TypeScript checking, frontend tests, and a
  production build are part of `make verify`.

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
