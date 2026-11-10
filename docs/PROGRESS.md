# Project Progress

## Current milestone
M14 — Evidence-based recommendation effectiveness (offline implementation
complete; V4 real-cluster evaluation inconclusive and valid acceptance pending)

## Completed
- M14 adds schema-1.0 digest envelopes for a preflight plan and outcome report,
  a separate approval record, digest-bound repeated trial manifests, explicit
  performance/efficiency objectives and regression guardrails, per-trial
  optional measurements, uncertainty and confounder retention, variation,
  evidence references, and separate rollback/cleanup verification.
- The existing A/B evaluator now has a read-only M14 mode. It verifies artifact
  containment and digests, terminal lifecycle, workload/load/configuration
  identity, observation windows, repetitions, and measurement sufficiency. It
  classifies sufficient evidence as effective, ineffective, or harmful and
  forces missing, incomparable, corrupted, or confounded evidence to
  inconclusive. It contains no Kubernetes mutation path and refuses report
  overwrite.
- M13 adds a versioned, digest-bound quality dataset with distinct author and
  reviewer roles, leakage notes, two retained finding-bearing incident cases,
  fixed Qwen3 identity/options, two repetitions, reviewed facts,
  uncertainties, recommendations, citation judgments, exclusions, and
  provenance.
- Prompt 1.5 uses a minimal semantic projection, compact positional prose,
  dynamically exact arrays, and printable digit-free regex length bounds. The
  adapter preserves the raw response, rejects count/chunk-ID mismatches, and
  attaches only immutable M9 identities, numerical claims, analysis citations,
  recommendation values, and uncertainty source text before independent M12
  validation. Prompt 1.4 remains replayable for dataset 1.0.0.
- The deterministic paired evaluator records all trial/input/output digests,
  statuses, failures, validation issues, latency, metric numerators and
  denominators, missing candidate scores, paired differences, variability, and
  improved/regressed/inconclusive outcomes. Immutable replay uses the same
  retained M12 artifacts without contacting Ollama.
- Git repository initialized.
- Initial architecture and project requirements defined.
- Installable Python 3.12+ package and `src` repository layout created.
- Runtime and development dependencies declared with bounded major versions.
- Environment-based configuration added with required-value and URL validation.
- Offline configuration tests cover successful and failure behavior.
- Ruff, mypy, pytest, branch coverage, and aggregate verification commands added.
- M0 acceptance criteria and developer setup documented.
- Versioned workload, load, and experiment lifecycle contracts implemented.
- Hardened disposable HTTP application and rate-controlled load image added.
- Configurable Deployment and Service rendering implemented.
- Independent per-experiment load Jobs and atomic JSON records implemented.
- Scoped `kubectl` controller and explicit workload CLI implemented.
- M1 safety boundary, acceptance criteria, and operator workflow documented.
- Thread-safe Prometheus HTTP counters, error counters, and latency histogram
  added to the disposable application at `/metrics`.
- Workload Pods annotated for direct per-Pod scraping.
- Project-owned disposable Prometheus, read-only discovery RBAC, cAdvisor metric
  filtering, bounded resources, and six-hour ephemeral retention added.
- Canonical PromQL added for CPU, throttling, memory, throughput, errors, and
  latency without missing-value substitution.
- M2 acceptance criteria, source-series units, architecture, and operator
  procedure documented.
- Versioned raw Kubernetes and Prometheus snapshot contracts added with a
  shared Deployment UID identity and UTC observation timestamps.
- Read-only Kubernetes collection added for Deployment resourceVersion,
  container requests/limits, Pod identity/readiness/restarts, and related
  events using explicit context and namespace on every command.
- Read-only Prometheus range collection added for all M2 source series, scoped
  to the observed namespace, workload, application container, and Pod names.
- Structured missing-data reporting added for absent Kubernetes observations,
  absent Pod status, missing events, and empty expected Prometheus families;
  no missing observation is converted to zero.
- External command/transport, response-schema, timestamp ordering/range, and
  identity mismatches now fail explicitly.
- Versioned observation, normalized-series, quality-report, provenance, and
  inspection-summary contracts added.
- Deterministic structural normalization maps all ten M2 source metrics to
  canonical signals, kinds, units, aggregation scopes, and stable labels while
  retaining unchanged samples and embedded raw inputs.
- Quality classification now distinguishes complete, degraded, and insufficient
  observations with explicit source-missing, family coverage, counter sample,
  counter reset, histogram bound, unit, label, unknown-series, and collision
  findings.
- SHA-256 raw-source provenance, atomic immutable JSON storage, bounded
  inspection, digest validation, and exact deterministic replay added.
- Versioned analysis contracts added for sufficiency, statistics, detected
  conditions, source evidence, provenance, risks, and bounded recommendations.
- Replay-validated deterministic analysis now calculates per-Pod/container CPU,
  throttling, and memory statistics and workload-level HTTP throughput, error,
  mean-latency, and histogram-p95 statistics without fabricating missing values.
- Policy version 1.1 detects CPU throttling, CPU and memory limit pressure, and
  request mismatch at documented inclusive thresholds with exact evidence links.
- Recommendations are increase-only, Kubernetes-unit rounded, capped at twice
  current resources and applicable configured limits, and explicitly require
  approval. Insufficient evidence suppresses conditions and recommendations.
- Canonical M6 knowledge now contains two Kubernetes references, two diagnostic
  runbooks, and two historical project incidents as readable Markdown.
- A semantic-versioned JSON manifest records stable IDs, document versions,
  verification state, verifier and UTC time, sorted tags, explicit source
  provenance, repository-relative paths, and SHA-256 content digests.
- The read-only knowledge repository validates manifest contracts, type
  coverage, deterministic ordering, path containment, checksums, Markdown
  titles, and registration completeness before loading, retrieval, or bounded
  inspection.
- A versioned deterministic Markdown chunker produces stable, bounded chunks
  with UUID point IDs, exact text digests, document metadata, verification
  state, and source provenance.
- Production indexing and retrieval share the local pretrained
  `sentence-transformers/all-MiniLM-L6-v2` model through FastEmbed and validate
  its normalized 384-dimensional cosine vectors. Offline tests inject a
  deterministic model double and never download weights.
- Explicit Qdrant synchronization creates or validates only the configured
  collection, upserts current derived points, and deletes only stale points
  bearing the project ownership marker.
- A read-only Python inspection API lists canonical documents, reports index
  metadata, inspects bounded document-scoped chunks, resolves exact chunks, and
  returns bounded verified-only retrieval results with validated payloads.
- Analysis-grounded retrieval creates one query per recommendation and groups
  remaining condition types, retaining every originating M5 condition,
  statistic, and measurement-evidence reference with the retrieved chunks.
- Operational queries use deterministic reference/runbook/incident intent
  scoping and an 85% semantic/15% exact-term rerank over 20 candidates while
  preserving the semantic, lexical, and final scores.
- A fixed six-case, independently reviewed graded dataset covers CPU, memory,
  missing-data, and historical-incident retrieval with a canonical digest and
  explicit Recall@5, MRR@5, and nDCG@5 thresholds.
- A versioned M9 builder validates paired M5/M8 identity, source digest,
  sufficiency, finding coverage, and every referenced condition, statistic, and
  measurement-evidence ID before constructing an LLM handoff.
- M9 preserves exact M5 conditions, recommendations, numerical values, units,
  risks, and uncertainties while selecting only their complete transitive
  statistic/evidence closure; it performs no analysis or numerical formatting.
- Retrieval input is bounded to three ranked hits per query, twelve
  deduplicated 600-character excerpts, and fifty queries. Counts, component
  scores, chunk/point IDs, content digests, and canonical source provenance
  retain explicit traceability and expose omissions.
- Canonical digests bind the complete M5 and M8 inputs. Immutable atomic JSON
  storage adds a package digest, rejects overwrite and corruption, and exposes
  a bounded inspection summary.
- A versioned FastAPI application now exposes explicit workload and load
  controls, current Kubernetes state, raw live Prometheus metrics, immutable
  observation creation/loading/inspection, deterministic analysis, RAG
  evidence, and persisted LLM-input creation/loading/inspection.
- M10 composes the existing service boundaries through injected protocols and
  offloads blocking Kubernetes, Prometheus, filesystem, embedding, and Qdrant
  work from the event loop. Production construction validates settings first;
  offline tests replace every external boundary.
- Structured API failures distinguish request validation, missing artifacts,
  lifecycle or immutable conflicts, invalid analysis/input, and external
  dependency failures. Qdrant synchronization and LLM inference remain outside
  all API read and analysis routes.
- The documentation roadmap now extends through M18. M12–M17 are a mandatory
  backend gate covering local Qwen3 inference and independent validation,
  paired RAG evaluation, recommendation-effectiveness experiments, artifact
  lineage, complete FastAPI orchestration, and real-service backend acceptance;
  M18 is the final production-oriented React UI. Planned contracts and safety
  boundaries preserve all completed M0–M11 responsibilities and artifacts.
- M12 adds versioned contracts for explicit RAG mode, bounded inference
  options, numerical claims, citations, problem/recommendation explanations,
  preserved uncertainties, validation issues, accepted-output bindings,
  failures, immutable run envelopes, and bounded inspection summaries.
- The local inference runner consumes only a digest-valid M9 artifact, pins the
  configured Qwen3 model to Ollama's exact `/api/tags` digest, renders and
  digests deterministic messages, uses non-streaming JSON generation, and
  records options, UTC timing, raw response, Ollama counters, candidate,
  validation, and terminal status without contacting Kubernetes, Prometheus,
  or Qdrant.
- RAG-on and RAG-off rendering are explicit. Both retain identical M9
  deterministic findings; off mode excludes knowledge excerpts, while on mode
  requires at least one excerpt. Exact mode, source digest, prompt digest,
  model digest, seed, temperature, context, and output bound support future M13
  paired evaluation without implementing its dataset or scoring.
- The independent validator never repairs output. It requires complete ordered
  condition/recommendation/uncertainty coverage, exact numerical values and
  units, exact M5 evidence citations, valid RAG-on knowledge citations, exact
  recommendation quantities, unique claims/citations, and no undeclared
  numbers or unfilled prose sentinels. Only a passing report can create an
  accepted-output digest binding.
- Accepted, rejected, malformed, incomplete, timed-out, and dependency-failed
  runs persist immutably and refuse overwrite or digest drift. Offline tests
  cover successful on/off runs plus model mismatch, missing model/evidence,
  transport/schema/timeout equivalents, malformed output, altered claims,
  unknown and duplicate citations, missing uncertainty, invalid lifecycle
  states, artifact corruption, and store failures.

## Verification

- `make verify`: passed for M0 on 2026-10-31.
- M1 `make verify`: passed on 2026-10-31 with Ruff formatting/linting,
  strict mypy, and 49 offline pytest cases at 100% branch coverage.
- `kri-workload --help` passed from the editable installation.
- `docker build --tag kri-workload:local deploy/workload` passed, followed by
  a network-disabled, read-only container smoke test.
- Real-service M1 verification passed on 2026-10-31 against context
  `kind-kube-optimizer`, namespace `payments`, using image ID
  `sha256:37a4aa85a58f...` and experiment `exp-m1-verify-20261031`.
- The application reached 2/2 ready replicas with zero restarts. During the
  mixed 10 requests/second load, per-pod CPU ticks and received bytes increased,
  while the Job and its persisted lifecycle record remained `running`.
- Job-only stop transitioned the record to `stopped` after 31 seconds and left
  the Deployment and Service UIDs/resourceVersions unchanged at 2/2 ready.
- Cleanup removed every M1-owned Deployment, Service, Job, and Pod. The existing
  `checkout` Deployment remained 3/3 ready.
- M2 offline verification passed on 2026-10-31 with 56 pytest cases and 100%
  branch coverage for the `kri` package; runtime and monitoring asset tests also
  passed.
- Rebuilt `kri-workload:local` image ID `sha256:4a3b066ee57a...` passed a
  read-only, network-disabled metrics smoke test.
- The pinned Prometheus `promtool` accepted the embedded configuration, and all
  nine Kubernetes resources passed a client dry-run against the kind cluster.
- Real-service M2 verification passed on 2026-10-31 against context
  `kind-kube-optimizer` with experiment `exp-m2-verify-20261031` and rebuilt
  workload image ID `sha256:4a3b066ee57a...`.
- Prometheus discovered two application targets and one cAdvisor target, all
  healthy. The 91.5-second experiment produced fresh, timestamped per-container
  CPU usage, CFS periods/throttling, memory working set, HTTP request/error, and
  latency histogram series at five-second evaluation steps.
- Verified aggregate values included 0.107 CPU cores, 80.1% throttled CFS
  periods, 27,656,192 working-set bytes, 4.2 requests/second, five controlled
  HTTP errors, and 0.887-second latency p95 at collection time.
- All range timestamps were strictly increasing and inside the recorded UTC
  experiment interval. Source samples were 0.84–3.99 seconds old when captured.
- Job-only stop preserved the 2/2-ready application. Cleanup removed all
  M1/M2-owned Kubernetes resources while the unrelated `checkout` and
  `kic-monitoring` workloads remained intact.
- M3 offline verification passed on 2026-10-31 with fake Kubernetes and
  Prometheus responses. Tests verified exact read-only command/query scope,
  raw identity/timestamp/unit preservation, successful and missing-data paths,
  and malformed or failed external responses without contacting live services.
- M3 `make verify` passed in the project virtual environment with Ruff, strict
  mypy, and 110 offline pytest cases at 100% statement and branch coverage.
- Real-service M3 verification passed on 2026-10-31 against context
  `kind-kube-optimizer`, namespace `payments`, with Deployment UID
  `7d67cc31-fd04-47b0-8014-e3a13346b6af` and resourceVersion `1104738`.
- Kubernetes collection returned the two expected ready, zero-restart Pods,
  exact approved application resources, and 13 related events with no missing
  Kubernetes observations.
- A pre-error range collected 66 series and 528 raw samples across nine source
  families while reporting only `kri_http_request_errors_total` as missing.
  No zero-valued replacement was created.
- After exactly five controlled HTTP 400 responses, a second range collected
  all ten source families in 68 series and 1,360 samples. The raw error counter
  total was five; sample timestamps ran from `17:07:29Z` through `17:09:04Z`
  inside the recorded UTC interval.
- Real verification exposed and fixed two M3 defects: Prometheus millisecond
  boundary precision and application selection using the real M2
  `job="kri-workload"` label instead of a nonexistent `workload` label.
- Cleanup removed all disposable M1/M2/M3 resources. The unrelated `checkout`
  Deployment remained 3/3 and the existing `kic-monitoring` Prometheus remained
  1/1.
- The M1 load generator shutdown defect found during M3 verification is fixed.
  Scheduling now admits at most the configured concurrency, discards arrivals
  while saturated, caps request timeouts by the remaining duration, and never
  drains an accumulated executor queue after the deadline.
- An offline overload regression test uses a 10,000 requests/second target with
  two deliberately slow workers and verifies that only two requests are
  admitted and shutdown remains duration-bounded.
- M4 offline verification passed on 2026-10-31 with complete, degraded,
  insufficient, identity-mismatch, corruption, filesystem-failure, inspection,
  and replay cases. The full suite passed with 123 tests at 100% statement and
  branch coverage, plus Ruff and strict mypy.
- The retained real M3 post-error evidence replayed locally into
  `obs-m3-verify-20261031`: quality `complete`, 68 normalized series, 1,360
  unchanged samples, zero issues, and an exact successful store replay. No live
  service was contacted for M4 verification.
- M5 `make verify` passed in the project virtual environment on 2026-10-31 with
  Ruff, strict mypy, and 140 offline pytest cases at 100% statement and branch
  coverage.
- M5 tests cover threshold boundaries, per-container scoping, reset and missing
  counters, malformed histograms and contracts, sufficient/partial/insufficient
  outcomes, deterministic saved input, evidence references, and recommendation
  rounding, caps, invariant preservation, and rejection paths.
- The retained real M4 observation was replayed locally into analysis
  `analysis-m3-verify-20261031`: sufficient, 26 statistics, seven conditions,
  72 evidence records, and three approval-required recommendations. Analyzer
  policy 1.1 recommends CPU limit `100m` to `160m`, CPU request `50m` to `100m`,
  and memory request `64Mi` to `97Mi`. It records six finite-window,
  scrape-resolution, constrained-headroom, and near-threshold uncertainties. No
  live service or cluster mutation was used.
- Real-artifact replay exposed and fixed false duplicate-scope warnings caused
  by indexing HTTP series as resource series; a regression test now restricts
  duplicate suppression to CPU, throttling, and memory signals.
- M5 review on 2026-11-01 found that five-second query evaluations repeated
  slower scrape values and inflated adjacent CPU peaks about threefold. Policy
  1.1 coalesces repeated evaluations and excludes the first partial update,
  correcting Pod peaks from 334m/286m to 126m/95m and the CPU-limit adjustment
  from 200m to 160m.
- The same review replaced the raw-ratio severity shortcut with explicit
  condition-specific critical thresholds, corrected request-versus-limit
  recommendation rationale, and reports limits that prevent the intended 25%
  headroom. Full verification passed with 142 tests and 100% statement and
  branch coverage, plus Ruff and strict mypy.
- M6 `make verify` passed in the project virtual environment on 2026-11-01 with
  Ruff, strict mypy, and 170 offline pytest cases at 100% statement and branch
  coverage.
- M6 tests verify the canonical six-document corpus plus missing/malformed
  manifests, unsafe or escaping paths, duplicate IDs and paths, checksum and
  heading drift, invalid UTF-8, unregistered Markdown, incomplete type coverage,
  invalid provenance, and inconsistent verification metadata. No external
  service was contacted.
- M7 `make verify` passed in the project virtual environment on 2026-11-01 with
  Ruff, strict mypy, and 212 offline pytest cases at 100% statement and branch
  coverage.
- M7 tests cover deterministic chunking and embeddings, collection creation and
  schema rejection, idempotent synchronization, stale-owned deletion without
  foreign deletion, pagination, inspection and retrieval filters, exact payload
  validation, malformed Qdrant responses, and transport failures. No external
  service is contacted by the offline suite.
- Real M7 verification passed on 2026-11-01 against an isolated Qdrant 1.19.1
  container using image digest `sha256:12364fe851b...`, a tmpfs data directory,
  localhost port 16333, and collection `kri_m7_verify_20261101`.
- The real MiniLM model indexed all six canonical documents as 26
  384-dimensional cosine points. Direct Qdrant inspection confirmed the 2.0
  ownership/schema payload, exact model name, provenance, text digest, and
  green collection state.
- A second synchronization retained the same 26 point UUIDs, created no extra
  points, and deleted no stale points. Document and chunk inspection returned
  six documents and 26 validated chunks.
- The CPU-limit query ranked the canonical Kubernetes requests-and-limits
  behavior first with score 0.7911. The memory-working-set query ranked the
  memory-sizing procedure first with score 0.5240. All returned hits retained
  verified status and source provenance.
- The isolated container and its tmpfs storage were removed after verification;
  only the downloaded MiniLM model cache remains locally.
- M8 `make verify` passed in the project virtual environment on 2026-11-01 with
  Ruff, strict mypy, and 224 offline pytest cases at 100% statement and branch
  coverage. Offline retrieval tests use deterministic doubles and contact no
  model service or Qdrant instance.
- Real M8 verification used the retained M5 analysis and an isolated Qdrant
  1.19.1 tmpfs-backed container with collection `kri_m8_verify_20261101`. It
  produced three recommendation evidence bundles with exact M5 reference IDs.
- The fixed dataset initially exposed insufficient ranking quality; judgments
  and thresholds were left unchanged. After deterministic intent scoping and
  traceable reranking, the final run passed with mean Recall@5 0.8917, MRR@5
  0.9167, and nDCG@5 0.8704 against thresholds 0.50, 0.80, and 0.70.
- The evaluation used dataset digest
  `1e8d153027cd6447dde11e5b6fde62d173c0867f5a8a8db284346a942da4fc17`.
  The isolated container and tmpfs state were removed after verification.
- M9 `make verify` passed in the project virtual environment on 2026-11-01 with
  Ruff, strict mypy, and 242 offline pytest cases at 100% statement and branch
  coverage. The 18 M9 tests cover exact value/uncertainty preservation,
  transitive closure, retrieval bounds and deduplication, empty/no-hit states,
  source mismatch and dangling-reference rejection, immutable persistence,
  corruption, filesystem failures, and inspection without external services or
  model inference.
- Real M5→M8→M9 verification passed on 2026-11-01 by replaying retained
  observation `obs-m3-verify-20261031` against isolated collection
  `kri_m9_pipeline_20261101` in a Qdrant 1.19.1 tmpfs-backed container. The
  observation remained complete with 68 normalized series, 1,360 samples, zero
  quality issues, and source digest
  `426cb9c29df1c669bc9bdc6bb88d7b264264512a423b847af835576729a9445e`.
- Fresh M5 analysis `analysis-m9-pipeline-20261101` reproduced 26 statistics,
  seven conditions, three recommendations, and six explicit uncertainties.
  Real M8 indexed 26 MiniLM chunks, returned five hits for each of three
  recommendation queries, and passed the fixed evaluation with Recall@5
  0.8917, MRR@5 0.9167, and nDCG@5 0.8704.
- M9 package `llm-input-m9-pipeline-20261101` persisted and reloaded exactly.
  Inspection reported seven selected statistics, seven conditions, three
  recommendations, six uncertainties, three queries, nine ranked hit
  references, and five deduplicated excerpts. Package digest
  `9a2af625745edc2779de8a30fce3f4ea5080ba680c2553a6a1d5df575e3c89ef`
  validated on load. Generated artifacts remain under
  `results/m9-verification/`; the isolated container and tmpfs state were
  removed after verification.
- M10 `make verify` passed in the project virtual environment on 2026-11-01
  with Ruff, strict mypy, and 271 offline pytest cases at 100% statement and
  branch coverage. Twenty-nine M10 tests exercise every success route through
  in-process ASGI requests, OpenAPI, exact component arguments, observation and
  package persistence, safe-ID and interval validation, all documented error
  mappings, production service construction, and the loopback runner without
  Kubernetes, Prometheus, Qdrant, model downloads, or network services.
- Real M10 verification passed on 2026-11-01 through a Uvicorn server on
  loopback using retained observation `obs-m3-verify-20261031` and isolated
  collection `kri_m10_api_20261101` in a Qdrant 1.19.1 tmpfs-backed container.
  Explicit M7 synchronization indexed all six canonical documents into 26
  MiniLM points; a second synchronization retained stable point IDs and
  deleted no stale points.
- HTTP health and every required M5→M8→M9 OpenAPI route were present. The API
  loaded the complete 68-series, 1,360-sample real observation with source
  digest `426cb9c29df1c669bc9bdc6bb88d7b264264512a423b847af835576729a9445e`,
  reproduced 26 statistics, seven conditions, three recommendations, and six
  uncertainties, then returned five verified knowledge hits for each of three
  evidence queries.
- Package `llm-input-m10-api-20261101` was created with HTTP 201, loaded and
  inspected with HTTP 200, and matched its creation response exactly. Its
  three queries, nine bounded hit references, five excerpts, explicit
  timestamps, identity, uncertainties, and input digests persisted under
  package digest
  `a65c88b48f1d3b88f585b43aafa0a66f06298e44c566346ced14eba500e50288`.
  Exact API responses remain under `results/m10-verification/`; the isolated
  Qdrant container, tmpfs state, and loopback API process were removed.
- M11 adds a local Vite, React, and strict TypeScript application under `web/`.
  Its responsive two-column interface exposes every explicit M10 workload/load
  control, timestamped raw metric traces and missing-data records on the left,
  and visible M4→M5→M8→M9 stage handoffs on the right.
- The frontend passes complete M5 and M8 responses forward unchanged, clears
  stale downstream state when an upstream stage changes, explains disabled
  prerequisites, prevents duplicate operations, and displays structured HTTP
  or network failures with expandable raw contracts. Findings,
  approval-required recommendations, uncertainties, retrieval component
  scores/provenance, and M9 counts/digests remain inspectable.
- M11 remains a same-origin local development client through the Vite proxy,
  with optional `VITE_API_BASE_URL`. It has no persistent browser store and no
  routes for Qdrant synchronization, LLM inference, recommendation application,
  authentication, or production deployment.
- M11 offline verification passed on 2026-11-01 with strict TypeScript, eight
  Vitest/API-client component tests, and a Vite production build. Tests cover
  exact M4→M9 chaining, load-stop/application-delete independence, timestamped
  metric and missing-data rendering, RAG-off behavior, structured operation
  errors, and immediate FastAPI connection failure. The 163.35 kB JavaScript
  bundle is 51.67 kB gzip. `npm audit` reported zero
  vulnerabilities after upgrading the development test runner to Vitest
  4.1.12.
- M11 local startup now resolves `.env` from the repository root even when
  `kri-api` or another settings consumer starts elsewhere. A regression test
  changes to an unrelated directory before loading the root file, while normal
  process environment variables retain precedence.
- `make dev-check` performs read-only Prometheus readiness, Qdrant readiness,
  and configured-collection probes and aggregates service-specific URLs and
  recovery instructions. `make sync-knowledge` remains the separate explicit
  Qdrant mutation; `make dev-api` requires the preflight, and the React header
  independently reports FastAPI liveness. The documented four-terminal local
  procedure pins the verified Qdrant image and distinguishes its HTTP port 6333
  from the obsolete example's gRPC port 6334.
- Post-fix `make verify` passed on 2026-11-01 with Ruff, strict mypy, 279 Python
  tests at 100% statement and branch coverage, eight Vitest tests, strict
  TypeScript, and a Vite production build. No Kubernetes, Prometheus, or Qdrant
  mutation was performed during verification.
- The retained A/B resource experiments were evaluated offline on 2026-11-02
  by integrity-checking and replaying observations `obs-ui-20261102154751` and
  `obs-ui-20261102161957` through the M5 analyzer. A reproducible script and
  digest-pinned report compare throughput, histogram p95, CPU use, throttling,
  response-code errors, and Kubernetes stability without querying live
  services or changing the saved artifacts.
- Candidate B raised `/work` throughput from 9.030 to 12.525 requests/second
  (+38.70%) and reduced p95 from 888.179 to 592.416 milliseconds (-33.30%),
  while aggregate average CPU rose from 143.300 to 223.855 mCPU (+56.21%). Mean
  throttled-period ratio changed only from 84.97% to 84.50%; B therefore
  remains throttled and reached only 62.62% of the configured 20 requests/second
  target.
- Both snapshots show 2/2 ready Pods, zero restarts, no interval warning events,
  and only HTTP 200 `/work` counters. Both remain degraded because the dedicated
  error counter is absent, and both experiment records remain `running` without
  end timestamps. The report consequently treats the status-derived 0% error
  rate as observed but not independently verified and does not claim lifecycle
  completion or client-side stability.
- Post-report `make verify` passed on 2026-11-02 from the project virtual
  environment with Ruff, strict mypy, 281 Python tests at 100% statement and
  branch coverage, eight Vitest tests, strict TypeScript, and a Vite production
  build. No Kubernetes, Prometheus, Qdrant, or saved-artifact mutation was
  performed.
- Experiment records now default to lifecycle schema 1.1 while retaining
  read compatibility with schema 1.0. New fields preserve Kubernetes Job UID
  and actual start time plus terminal reason, message, and controller/Kubernetes
  provenance; terminal validation rejects incomplete or contradictory records.
- Job reconciliation now uses `Complete`/`Failed` conditions, prefers
  `completionTime` for success, uses the failed-condition transition time for
  failure, rejects invalid timestamps and Job UID reuse, and waits rather than
  inventing an end time when authoritative terminal time is absent. Submission
  failure and explicit stop retain stable controller-owned reasons.
- Explicit stop reconciles before deletion, preserves Jobs that already
  succeeded or failed, and is idempotent for persisted terminal records.
  Automatic Job TTL deletion was removed so unattended Jobs retain their
  terminal evidence until explicit cleanup.
- M11 now polls running experiments every two seconds, stops at terminal state,
  and displays submission/start/end timestamps, Job UID, final state, reason,
  provenance, and condition message. Poll failures remain visible without
  fabricating a state. The reproducible A/B evaluator prefers the actual Job
  start timestamp when schema 1.1 provides it.
- Post-reconciliation `make verify` passed on 2026-11-02 with Ruff, strict
  mypy, 303 Python tests at 100% statement and branch coverage, ten Vitest
  tests, strict TypeScript, and a Vite production build. Verification was fully
  offline and performed no Kubernetes or external-service mutation.
- Real lifecycle verification passed on 2026-11-03 against context
  `kind-kube-optimizer`, namespace `payments`, with the single approved
  experiment `exp-lifecycle-real-20261103`. The bounded mixed load used
  concurrency 2, target 5 requests/second, duration 20 seconds, and an
  80-second Job deadline. Only its Job was created and subsequently deleted.
- Reconciliation persisted Job UID
  `c4d5e35b-509a-4578-8348-dde960e5c9af`, Kubernetes start
  `2026-11-03T06:21:16Z`, completion `2026-11-03T06:21:40Z`, state
  `succeeded`, reason `CompletionsReached`, exact condition message, and
  `kubernetes` provenance. The load Pod exited 0 with reason `Completed`, zero
  restarts, and phase `Succeeded`.
- Repeated terminal GET through the M11-facing FastAPI endpoint left the record
  byte-for-byte stable at SHA-256
  `93dfd4dea7b4200e5267cfa2128d0c691bce26614a9042e27dc36af352195754`.
  Terminal stop deleted the Job while returning the unchanged `succeeded`
  record, demonstrating that cleanup cannot relabel completion as stopped.
  The application Deployment UID/resourceVersion remained
  `3360fb27-d522-4b1d-9774-aa9e359e301a`/`1195095`; both Pods remained ready
  with zero restarts.
- The real run verified the API contract consumed by M11, while automatic
  polling and rendered lifecycle fields remain covered by Vitest because no
  browser executable was available in the verification environment. A single
  successful run does not constitute real-cluster verification of induced
  failure or active-stop outcomes; those paths remain offline-tested.
- Post-run `make verify` passed on 2026-11-03 with Ruff, strict mypy, 303 Python
  tests at 100% statement and branch coverage, ten Vitest tests, strict
  TypeScript, and a Vite production build.
- A read-only M14 local-cluster preflight on 2026-11-06 confirmed that
  `payments/kri-workload` still has Deployment UID
  `3360fb27-d522-4b1d-9774-aa9e359e301a`, resourceVersion `1195095`, two Ready
  replicas, the exact `90m/140m` CPU and `109Mi/192Mi` memory baseline, and one
  shared runtime image digest. The node was Ready with no reported pressure;
  no Kubernetes resources or workload traffic were created or changed.
- The digest-bound, unapproved M14 plan proposes only the retained deterministic
  recommendation `cpu_limit: 140m -> 220m`, with two baseline and two candidate
  trials, fixed objectives/guardrails, explicit stop/rollback/cleanup rules,
  and immutable artifact destinations. Its plan digest is
  `612af134d27a524e300c6f80e36c4367b5060a3ed10d7ab34f6a90d75130062e`.
- Follow-up read-only inspection corrected the monitoring diagnosis: the prior
  check used namespace `monitoring` instead of `kri-monitoring`. All nine live
  monitoring objects match the checked-in manifest, Prometheus is 1/1 Ready,
  its Service endpoint is populated, and Prometheus, cAdvisor, and both
  application targets report `up`. Local access failed only because no process
  forwards the ClusterIP Service to `localhost:9090`; no manifest apply is
  needed.
- At that point M14 execution remained blocked pending explicit experiment
  approval and local access restoration. Missing required metrics must stop a
  future run or yield `inconclusive`.
- Local Prometheus access was restored at `2026-11-06T14:36:41Z` with only a
  foreground `127.0.0.1:9090` port-forward to the existing Service. No manifest
  was applied: monitoring/workload resourceVersions remained `1154524` and
  `1195095`, and no M14 load Job was created.
- Exactly one zero-work success and one bounded invalid diagnostic request were
  sent to each application Pod outside any experiment window. Subsequent
  20-second range checks found five samples per series for both Pods across all
  required M14 CPU, throttling, memory, request, error, and latency families;
  all four scrape targets remained `up` without errors.
- The exact M14 plan was approved and attempted on 2026-11-08. Baseline A1
  started at `09:37:34Z` with the planned 120-second mixed load but Kubernetes
  terminated it as `Failed/DeadlineExceeded` at `09:40:55Z`. The mandatory stop
  rule prevented A2, the candidate rollout, B1, and B2 from starting.
- A1's immutable 120-second observation retained 70 normalized series and
  1,750 samples. It was degraded only because no related Kubernetes events were
  reported. Descriptive values include 11.5583 requests/second, 57.79% target
  attainment, 0.611648-second p95, 86.32% mean throttled-period ratio, and zero
  measured error ratio; no candidate effect can be inferred.
- Offline M14 evaluation classified report
  `m14-kri-workload-cpu-limit-20261108` as `inconclusive` because A1 failed and
  the required two baseline/two candidate comparisons are absent. Report digest
  is `9ee9834a4065060d39fdfcf8cb3a62110326a7b3473219d1c00637dd1bc87f1d`.
  Cleanup and restoration are verified: only A1's Job was deleted, no candidate
  rollout occurred, and the original Deployment remains UID/resourceVersion
  `3360fb27-d522-4b1d-9774-aa9e359e301a`/`1195095` at `90m/140m` CPU and
  `109Mi/192Mi` memory.
- Offline diagnosis on 2026-11-09 reproduced A1's lifecycle failure: a 50 ms
  load run with one non-returning request was still alive after 500 ms because
  `ThreadPoolExecutor` performs an unconditional `shutdown(wait=True)`. A socket
  timeout was not a hard process deadline, so Kubernetes eventually supplied
  A1's `DeadlineExceeded` terminal state.
- The load generator now uses concurrency-bounded daemon request workers,
  retains the no-queue admission policy, drains completed requests for at most
  one second, and exits nonzero if any request remains active. A new stuck-I/O
  regression verifies bounded return. No Kubernetes resource, recommendation,
  M14 plan value, or retained experiment artifact was changed, and M14 was not
  rerun.
- Post-fix offline verification passed on 2026-11-09: the isolated stuck-I/O
  reproduction exited status 1 after approximately 1.1 seconds; 43 workload
  tests passed; and full verification passed with Ruff, formatting, strict
  mypy, 340 Python tests at 100% statement/branch coverage, 10 Vitest tests,
  strict TypeScript, and the Vite production build.
- Real local-kind verification passed on 2026-11-09 with the separate
  `lifecycle-smoke-20261109` experiment. The uniquely tagged corrected image
  ran one 10-second mixed-load Job, whose container exited 0 after 11 seconds
  with no restart and whose Job reached `Complete`/`CompletionsReached` after
  14 seconds, safely inside its 70-second active deadline. The runtime image
  digest was
  `import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e`.
  The disposable Job was deleted, while the original application Deployment
  retained its UID, resourceVersion, generation, image, `90m/140m` CPU, and
  2/2 readiness. No M14 A/B trial or candidate rollout was started.
- Revised M14 plan v2 was prepared without cluster mutation on 2026-11-09. It
  pins the verified load-generator runtime digest separately from the unchanged
  target application image, assigns four fresh `m14v2-*` trial IDs, preserves
  policy 1.0 objectives and guardrails, and enumerates the exact Job creation,
  counter initialization, candidate rollout, rollback, unchanged-Service
  re-application, and Job cleanup operations that require later approval. The
  validated plan digest is
  `e41ce61c3e5a64a7a01b2f35a0c707c6df606e02c294950563fb9f720d39027a`;
  no v2 approval or trial manifest was created at planning time.
- M14 v2 execution was approved on 2026-11-09 but stopped at A1's mandatory
  warning-event gate. The digest-form kind import was present in containerd,
  yet kubelet attempted to pull its synthetic repository and the load Pod
  entered `ErrImagePull`/`ImagePullBackOff` without starting. Substituting the
  cached source tag was outside the approved digest-pinned plan, so A2, the
  candidate rollout, B1, and B2 were not started.
- The v2 evaluator classified report
  `m14-kri-workload-cpu-limit-20261109-v2` as `inconclusive`: A1 was stopped,
  its 94.5-second failure window was short and degraded, three repetitions were
  absent, and required comparisons were incomplete. No objective or guardrail
  was decided. Report content digest is
  `7e24c6a96bded1515196e00960b93e8693fc1a617d04a04e09366f17a161c4dc`.
- M14 v2 rollback and cleanup are verified. Only the approved A1 Job and owned
  Pod were created and deleted. No candidate apply occurred; the original
  Deployment UID/resourceVersion/generation, sole ReplicaSet, two Pod UIDs,
  image, resources, readiness, and restart counts remain unchanged. All four
  v2 Job names are absent and no mutation outside the approved scope occurred.
- The local load-image resolution was corrected and verified on 2026-11-09
  without an M14 trial. Load Jobs now render the node-cached tag with
  `imagePullPolicy: Never`; application Deployments retain `IfNotPresent`.
  Disposable Pod `kri-load-image-resolution-20261109` used tag
  `kri-workload:lifecycle-smoke-20261109`, resolved to runtime digest
  `import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e`,
  imported `kri_workload.load`, printed `load-image-ok`, and exited 0 with no
  restart. Its events explicitly reported the image already present on the
  machine, with no registry-pull attempt or warning. The Pod was deleted, and
  the application Deployment retained its original UID/resourceVersion,
  generation, image, `IfNotPresent` policy, resources, and 2/2 readiness.
- M14 v3 was prepared without Kubernetes access or trial execution on
  2026-11-09. Plan `m14-kri-workload-cpu-limit-20261109-v3` uses cached tag
  `kri-workload:lifecycle-smoke-20261109` with `imagePullPolicy: Never`, requires
  the verified runtime digest after scheduling, and assigns four fresh
  `m14v3-*` experiment/observation identities. Resource values, load controls,
  policy 1.0 objectives, guardrails, uncertainty handling, rollout, rollback,
  and cleanup boundaries remain unchanged. The exact mutation ledger includes
  application counter initialization, four fixed Job/Pod lifecycles, one
  candidate apply, one rollback apply, controller-owned rollout consequences,
  unchanged-Service re-application, and only v3 Job cleanup. Plan digest is
  `0a384b519d69d0242ba739b797e0235f0d943f77f9cc74bb416985d476c4a3d4`;
  no v3 approval or trial manifest existed at planning time.
- M14 v3 execution was approved on 2026-11-09. The full preflight passed and
  A1 resolved the cached tag with `imagePullPolicy: Never` to the verified
  runtime digest without a pull attempt. It ran the complete 120-second window
  but exited 1; Kubernetes recorded `BackoffLimitExceeded`. Because the load
  generator returns nonzero for any request exception or a worker still active
  after its shutdown grace and emits no per-request failure log, retained
  evidence cannot distinguish those causes. The mandatory failed-Job gate
  stopped A2, the candidate rollout, B1, and B2.
- The v3 evaluator classified report
  `m14-kri-workload-cpu-limit-20261109-v3` as `inconclusive`. A1's exact window
  retained 70 normalized series and 1,750 samples, but its failed lifecycle,
  degraded event evidence, and missing repetitions block every objective and
  guardrail decision. Report content digest is
  `017110aa7803111a4fc937d365b5d0f291247b5f030b524b2a1ce67e23725ca2`.
- M14 v3 rollback and cleanup are verified. Only the approved A1 Job and owned
  Pod were created and deleted. No candidate apply occurred; the original
  Deployment UID/resourceVersion/generation, sole ReplicaSet, both application
  Pod UIDs, image, resources, readiness, and restart counts remain unchanged.
  All v3 Job names are absent and no mutation outside approval occurred.
- Load-generator diagnostics were improved offline on 2026-11-09 without an
  M14 rerun or Kubernetes mutation. Each configured run now emits one final
  schema-1.0 JSON summary with separate succeeded, failed, timed-out, and stuck
  worker counts. Stable exits 2/3/4/5 identify request failure, timeout, stuck
  worker, or multiple modes; exit 0 remains the sole success. Load Pods use
  `FallbackToLogsOnError` so Kubernetes can retain the summary as the container
  termination message. The evaluator still rejects every nonzero lifecycle.
- One bounded real-cluster diagnostic Pod verified that behavior on 2026-11-09
  without starting an M14 Job or changing the application Deployment. Image
  `kri-workload:diagnostics-20261109` was built from the updated source, loaded
  into kind, and selected from the node cache with `imagePullPolicy: Never`.
  A one-second request to the Pod's closed loopback port produced exactly one
  request failure, process/Kubernetes exit code 2, reason `Error`, and a
  schema-1.0 summary with zero timeouts and zero stuck workers. Kubernetes'
  termination message matched stdout exactly under `FallbackToLogsOnError`.
  The Pod ran from `2026-11-09T09:14:53Z` through `09:14:54Z` and was deleted.
  No load-generator Job remained, and the application Deployment retained UID
  `3360fb27-d522-4b1d-9774-aa9e359e301a`, resourceVersion `1195095`, generation
  1, image `kri-workload:local`, resources `90m/140m` CPU and `109Mi/192Mi`
  memory, and 2/2 readiness before and after the test. Offline tests continue
  to cover the complete 0/2/3/4/5 exit-code mapping; this single real-cluster
  test intentionally exercised only the deterministic request-failure path.
- A separate 120-second V3 baseline failure-diagnostic plan was prepared on
  2026-11-09 without Kubernetes mutation. Plan
  `m14-v3-baseline-diagnostic-20261109` pins the unchanged V3 baseline and load
  settings, verified diagnostic tag/runtime digest, one fresh non-trial Job,
  one owned Pod, evidence capture, and Job/Pod cleanup. It explicitly prohibits
  candidate trials and every application, monitoring, or image-cache mutation.
  Execution requires approval quoting the plan ID and exact plan-file SHA-256
  `6964669ecb43e27047b95f26c4128cad488732ce0aec3b8621b5bc3500cac8f1`.
  Offline rendering verified the fixed Job name, image, pull and termination
  policies, load settings, resource bounds, restart policy, and 180-second
  deadline. A read-only readiness snapshot then confirmed the exact context,
  unchanged Deployment UID/resourceVersion/generation and baseline resources,
  2/2 ready application Pods at the pinned runtime image with historical
  restart count 3 each, the unused Job and record IDs, Ready/pressure-free
  node, cached diagnostic tag at the pinned runtime digest, Ready Prometheus,
  and healthy application and cAdvisor targets. The sole retained warning is
  V3 A1's historical `BackoffLimitExceeded` event at `08:13:32Z`. This
  snapshot authorizes nothing and must be repeated after approval immediately
  before execution. No diagnostic Job or other Kubernetes mutation occurred.
- The digest-bound V3 baseline diagnostic was approved and executed once on
  2026-11-09. Mandatory preflight repeated successfully, then the sole Job
  `kri-load-m14v3-diag-base-20261109` ran the original mixed/concurrency-4/
  20-rps/120-second baseline load with the pinned diagnostic image. Its one
  Pod ran from `09:37:50Z` through `09:39:51Z`, selected the cached image at
  runtime digest `7199ce4354f3c13ba9f82f114f8a9695ec309c8a88d2b0459301c6f49af6c052`,
  and had zero restarts. The failure reproduced as exit 3
  (`request_timeout`): 1,498 requests started and completed, 1,494 succeeded,
  four timed out, none had a non-timeout failure, and no worker was stuck.
  The schema-1.0 stdout summary exactly matched Kubernetes' termination
  message and exit code; the Job consequently ended
  `BackoffLimitExceeded`, preserving the unchanged nonzero-lifecycle guardrail.
  This identifies timeout as V3's immediate generator failure class but does
  not identify the individual slow requests or evaluate the CPU recommendation.
  Evidence is retained in
  `results/m14-v3-baseline-diagnostic-20261109.json` and the terminal experiment
  record. Cleanup deleted only the approved Job and owned Pod. All
  load-generator Jobs are absent, while the original Deployment and Pod
  identities, image, resourceVersion/generation, resources, readiness, and
  restart counts remain unchanged. No candidate trial or application mutation
  occurred.
- Load execution and measured request outcomes were separated offline after the
  V3 diagnostic. Load-summary schema 1.1 now exits zero with
  `execution_status: completed` when all workers return, even if request
  failures or timeouts were measured; only a stuck worker is a generator
  execution failure and exits 4. The same summary is written to stdout and the
  explicit Kubernetes termination log. New experiment-record schema 1.2 accepts
  a succeeded Job only after reconciling exactly one owned Pod and validating
  that summary against the container exit code; failed/stopped records remain
  lifecycle-invalid for M14 and may preserve a summary when available.
- M14 report/evaluator schema 1.1 retains the application HTTP error ratio,
  client failure ratio and counts, and uses their maximum as the unchanged
  policy-facing error ratio. Missing either source remains a blocking
  measurement limitation rather than becoming zero. The web contract and
  status panel expose the retained client outcomes. `make verify` passed with
  Ruff, formatting, strict mypy, 359 Python tests at 100% statement/branch
  coverage, ten frontend tests, TypeScript checking, and a production build.
  Verification was offline: no image was rebuilt or loaded, no Kubernetes
  resource was changed, and no M14 trial was rerun. A separately approved image
  build/load and bounded real-cluster lifecycle check remain required before
  relying on this behavior in a new experiment.
- A minimal real-cluster lifecycle verification was prepared for separate
  approval as
  plan `load-generator-schema12-timeout-verification-20261109` in
  `docs/LOAD_GENERATOR_SCHEMA12_REAL_CLUSTER_VERIFICATION_PLAN.md`, SHA-256
  `a74df3bd902daa238db59f94d6e0b4864e6b03685abc08e7fac8532bb7c15a7a`.
  It pins all image build inputs and authorizes, only after separate approval,
  one fresh cached image, one 15-second concurrency-4 Job, schema-1.2 evidence
  reconciliation, and deletion of that Job/owned Pod. Passing requires at least
  one separately recorded request timeout with process exit 0, a completed Job,
  and exact equality between stdout, termination-message, and persisted
  `load_summary`; zero observed timeouts is inconclusive and does not authorize
  a retry. Read-only preflight found the baseline Deployment and two application
  Pods unchanged and Ready, a healthy node, no load-generator resources, and no
  pre-existing fresh tag or record. The fixed Job render was validated offline
  and `git diff --check` passed. No image, cluster resource, application,
  request stream, or experiment record was changed or created during plan
  preparation.
- The digest-bound schema-1.2 lifecycle plan was approved and executed once on
  2026-11-09. The fresh image had local ID
  `sha256:7a608b497c785452d65fbf9ebd06183d4da29cf6237120fd56de57b489a4733b`
  and resolved from the kind node cache to runtime digest
  `sha256:3980b56b915b631157ca6bf8df8ae6c77f503fc77eb7881c25ef402e3325eba8`.
  The sole 15-second Job used exactly one owned Pod with zero restarts and
  terminated normally: all 180 started requests completed, 176 succeeded,
  four timed out, none had a non-timeout request failure, and no worker was
  stuck. The schema-1.1 summary therefore retained the measured timeouts with
  `execution_status: completed` and exit 0; Kubernetes recorded container
  reason `Completed` and Job `Complete=True`, not a failed Job. Stdout and the
  termination message matched exactly. Controller reconciliation persisted a
  succeeded schema-1.2 record with the same `load_summary`, Job UID
  `96b8e432-bab9-4156-8531-d322d39d50fb`, and Kubernetes timestamps at
  `results/experiments/schema12-timeout-20261109.json`; its SHA-256 is
  `57e3a9cadaf9b6a376d6f2651850e7867a640f4d7a000a561c6614296ab07908`.
  Approved cleanup removed only the fixed Job and owned Pod. Final assertions
  found no load-generator resources and confirmed the application Deployment
  UID, resourceVersion, generation, image, resources, replicas, both Pod UIDs,
  readiness, and restart counts were unchanged. The retained experiment record
  and fresh local/node image tag are the plan's intentional residual evidence;
  no M14 trial or application/monitoring mutation occurred.
- M14 V4 was prepared for separate approval in
  `docs/M14_LOCAL_EXPERIMENT_PLAN_V4.md` and the validated machine envelope
  `evaluation/m14-local-cpu-limit-plan-v4.json`. Its plan ID is
  `m14-kri-workload-cpu-limit-20261109-v4`, canonical plan SHA-256 is
  `30b702973e197b197d55919b18c4be690f8af8e8bdba98b8a6db859197aaad7c`,
  envelope file SHA-256 is
  `6d2f6b54ee896e1743355bd46c5aa06007e22b8249bcee7b3e42790c176c4e5b`,
  and plan-document SHA-256 is
  `28f49ba72be1bc5d851be3bd68c4914e76e24875b28867e7b503c3c3ece64da9`.
  Fresh A1/A2/B1/B2 IDs use the verified cached schema-1.2 load image and retain
  the exact V3 baseline, candidate, load, objectives, guardrails, repetition
  count, uncertainty treatment, rollout, and rollback. Eligibility now requires
  exact schema-1.1 termination evidence in each succeeded schema-1.2 experiment
  record; application and client failure evidence feed the unchanged strict
  error guardrail. Contract validation, byte-equivalent policy comparisons,
  all four offline Job renders, candidate/rollback scope, and artifact absence
  passed; 53 targeted effectiveness/workload tests and `git diff --check`
  passed. Read-only cluster inspection found the baseline application Ready,
  the node healthy, no load Jobs, all V4 IDs absent, the verified load runtime
  digest cached, and in-cluster Prometheus 1/1 Ready. At
  `2026-11-09T11:23:36Z`, the existing loopback Prometheus port-forward was
  alive and needed no replacement. Prometheus, cAdvisor, and both application
  targets were healthy without scrape errors; all ten required M14 families
  returned 42 series and 294 finite samples over a 30-second no-load window.
  Monitoring and workload identities/resourceVersions remained unchanged, and
  no load Job existed. No approval/trial manifest was created and no image,
  diagnostic traffic, experiment, or Kubernetes mutation occurred during plan
  preparation. Target and metric readiness remained mandatory immediately
  before execution.
- M14 V4 was approved and all four fixed trials executed on 2026-11-09 with
  the pinned cached schema-1.2 image. Every Job completed with one Pod, zero
  restarts, exit 0, no stuck worker, exact stdout/termination/schema-1.2
  evidence, and all ten metric families. A1/A2 completed 1,465/1,544 requests
  with three timeouts each; B1/B2 completed 2,057/2,072 with three/two
  timeouts; no non-timeout client failure occurred. Baseline observations had
  70 series/1,750 samples each but remained degraded solely because no related
  Kubernetes event was reported; B1/B2 had complete quality with 70 series and
  1,747/1,750 samples.
- The authoritative V4 result is `inconclusive`. Candidate throughput and
  target attainment improved 40.59%, latency improved 23.50%, client-aware
  error ratio improved 39.27%, and all five guardrails passed. The throttling
  objective failed (2.41% improvement, candidate ratio 0.79646 versus required
  20% and <=0.60) and throughput-per-CPU-core failed (8.70% regression).
  Baseline quality limitations block a causal decision. In addition, transient
  candidate-rollout readiness warnings at `11:37:03Z`/`11:37:08Z` were found
  during the final audit; B1/B2 had been run despite the plan's warning-event
  stop condition, so both are explicitly confounded and the procedural
  violation is retained. Similar rollback-startup warnings mean formal
  rollback verification is `failed`, although the exact baseline configuration
  is restored and healthy. Cleanup is `verified`: all load Jobs/Pods are absent,
  baseline ReplicaSet is 2/2, candidate ReplicaSet is 0/0, both current Pods are
  Ready with zero restarts, the Service is unchanged, the node has no pressure,
  and all four monitoring targets are healthy.
- The V4 report is in `docs/M14_LOCAL_EXPERIMENT_REPORT_V4.md` (SHA-256
  `6bfb8bc9043b50a7f8351e662856a31ffc41087cb9d36b09f718fc25d244a24f`).
  The authoritative audited manifest SHA-256 is
  `e14bb17d74956995704f2d107d10f289252970b21dc07c3cb22b5f8ce756e9f6`;
  audited report content/envelope SHA-256 values are
  `9b5da27b6f9eb254e72a4623ae2fdffbb82f59f9858644f7fff90d1826090f10`
  and
  `6645be759284aecfcaa1ffd4fbff27d473c11be435a4fb46440a277af6065dd3`.
  The preliminary report that marked rollback verified is preserved and
  superseded, not overwritten. No mutation outside the plan's enumerated
  resource names/fields occurred, but the missed stop sequence is not treated
  as compliant execution.
- M12–M18 planning was documented on 2026-11-03 without implementing new
  functionality. A consistency check confirmed exactly one roadmap acceptance
  section for every M0–M18 milestone and one decision entry for every D001–D025,
  while distinguishing the completed M0–M11 first phase from final M18 scope.
  `git diff --check` passed.
- Post-planning `make verify` passed from the project virtual environment with
  Ruff, strict mypy, 303 Python tests at 100% statement and branch coverage, ten
  Vitest tests, strict TypeScript, and a Vite production build. No Kubernetes,
  Prometheus, Qdrant, Ollama, or saved-artifact mutation was performed.
- Real M12 verification accepted run `m12-qwen3-4b-rag-off-20261103h` against
  retained real package `llm-input-ui-20261102151015`. It pinned local
  `qwen3:4b` to digest
  `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`,
  used temperature zero, seed 42, an 8,192-token context, a 1,024-token output
  bound, disabled thinking, and explicit RAG-off mode.
- The accepted request ran from `2026-11-03T08:55:12.908435Z` through
  `2026-11-03T08:57:57.464769Z`. Ollama reported 1,165 prompt tokens, 563 output
  tokens, and 164.513 seconds. The candidate preserved all five real
  uncertainties, returned no invented conditions or recommendations, and
  passed independent validation with zero issues. Prompt, raw response,
  candidate, validation, and complete artifact digests are preserved under
  artifact digest
  `148e2a36f449aab149819dd4e27065091669b8f42abcb6884f6a3f5dc3dd6bec`.
- Real rejected/failed artifacts also demonstrate two bounded dependency
  timeouts, token-limit interruption, evidence-object echo, unfilled prose, and
  undeclared timestamp claims. Those results drove JSON-mode generation,
  explicit evidence/template separation, sentinel validation, and conservative
  finding-free output; none was repaired or promoted. The timed-out local
  runner was explicitly stopped after it continued consuming CPU.
- Post-M12 `make verify` passed on 2026-11-03 with Ruff, strict mypy, 317 Python
  tests at 100% statement and branch coverage, ten Vitest tests, strict
  TypeScript, and a Vite production build. The suite remained offline; the
  separate real verification contacted only local Ollama and wrote immutable
  result artifacts.
- Fresh real M13 evaluation `m13-final-20261105` ran eight planned trials over
  two retained real incident packages. It pinned `qwen3:4b` digest
  `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`,
  prompt 1.4, temperature zero, seed 42, an 8,192-token context, a 768-token
  output bound, disabled thinking, and dataset digest
  `c89ac9ea18c62ab6fcb3ec30164290daf560202cddd21976c4e7598e1abb97f1`.
- Five real candidates were parseable but rejected for undeclared numbers in
  generated prose. Three RAG-on trials failed before scoring: one 600-second
  timeout and two output-bound incomplete generations. Validation success was
  zero in both modes. Only one pair had both candidates for other quality
  metrics; its equal perfect structural scores were inconclusive and do not
  override validation failure or the three missing pairs.
- Across all four pairs, RAG-off mean latency was 335.332 seconds and RAG-on
  mean latency was 513.635 seconds. The mean paired RAG-on difference was
  +178.303 seconds with 48.914-second standard deviation, so latency regressed.
  Quality benefit was inconclusive. Immutable report digest is
  `12e797408c9134f2d4a181cab1f97bee9aeffa59e126045f23b9982bb39fa192`.
- CPU bottleneck trials distinguished a 900-second full-schema timeout, a
  509.365-second compact-object placeholder copy, a 600-second Qwen3.5 9B
  timeout, and a 409.619-second positional-array pre-bound result. Prompt 1.4
  reduced final RAG-off runs to 296.337–425.400 seconds and prevented structural
  count/chunk-ID drift, but did not make local generation reliable or
  interactive.
- A real prompt 1.5 follow-up on retained CPU-throttling package
  `llm-input-ui-20261102161957` produced validator-accepted explanations with
  zero issues in both modes. The identical-options pair used a 4,096-token
  context and 768-token output ceiling. RAG-off used 930 prompt tokens, 367
  output tokens, and 89.324 seconds; RAG-on used 1,244 prompt tokens, 682 output
  tokens, and 181.216 seconds. RAG-on emitted 16 valid citations resolving to
  the two supplied CPU runbook chunks; RAG-off emitted none. Relative to prompt
  1.4 mode means, latency improved 73.4% and 64.7%, respectively, without
  changing independent validation or deterministic fact attachment. A separate
  accepted RAG-off run established a 640-token minimum tested ceiling at 88.485
  seconds.
- The follow-up retained failed 512/640/768/1,024-token boundary attempts and a
  control-character grammar failure. Incomplete or malformed output remained
  failed; no response was repaired. The accepted artifact digests are
  `dac9d262759fcd39aa50ca6c66c8598bf1eb80d2cea278619366b8fcabccf632`
  (RAG-off) and
  `d17290918893312b570818265f278a72f4739cacedca1d0201335bef175bafe1`
  (RAG-on).
- Post-M13 `make verify` passed on 2026-11-05 from the project virtual
  environment with Ruff, strict mypy over 48 source files, 325 Python tests at
  100% statement and branch coverage, ten Vitest tests, strict TypeScript, and
  a Vite production build. Offline replay reproduced the retained real report's
  trial/failure counts and every paired comparison.
- Post-optimization `make verify` passed on 2026-11-06 with Ruff, formatting,
  strict mypy over 48 source files, 325 Python tests at 100% statement and
  branch coverage, ten Vitest tests, strict TypeScript, and a Vite production
  build. The suite remained offline; real Ollama runs are retained separately.
- M14 offline `make verify` passed on 2026-11-06 with Ruff, formatting, strict
  mypy over 50 source files, 339 Python tests at 100% statement and branch
  coverage, ten Vitest tests, strict TypeScript, and a Vite production build.
  Verification used synthetic and retained artifacts only and performed no
  Kubernetes or external-service operation.
- GitHub-presentation verification passed on 2026-11-10 with Ruff lint and
  formatting, strict mypy over 50 source files, 359 offline Python tests at 100%
  statement and branch coverage, ten Vitest tests, strict TypeScript, and a Vite
  production build. README local links, `git diff --check`, tracked-file secret
  patterns, and retained M14 plan/approval/manifest schemas were checked without
  contacting or mutating Kubernetes or external services.

## Next
Revise the M14 procedure so readiness and warning-event stop gates are checked
before every candidate trial, then obtain explicit approval before any new
cluster mutation. A future run must retain at least two valid baseline and two
valid candidate trials, terminal lifecycle and complete metrics, and separate
rollback/cleanup verification. The current V4 evidence remains inconclusive and
must not be reused as successful acceptance. M15 must not begin until valid M14
acceptance evidence exists; M14–M17 must complete before M18 begins.

## Known limitations
- The cluster Metrics API was unavailable during M1 verification; load evidence
  used application process CPU and network receive counters instead.
- The verified workload image remains cached on the disposable kind node.
- M15–M18 are planned but not implemented. M10 and M11 are loopback-only
  development tools and do not provide production authentication,
  authorization, TLS, or deployment packaging.
- M14 real-cluster acceptance remains incomplete. V4 observed 40.59% higher
  throughput and 23.50% lower p95 latency, but failed the throttling and CPU
  efficiency objectives. Candidate trials also continued after readiness-warning
  stop conditions, so the authoritative classification is `inconclusive`, not a
  verified optimization success. Earlier attempts remain retained as superseded
  or incomplete evidence.
- M11 has offline component coverage and a production build, but has not yet
  been exercised in a browser against live Kubernetes, Prometheus, and Qdrant
  services.
- M13 dataset 1.0.0 contains two retained finding-bearing pressure incidents,
  not the longer-term 20–30-case mix. Healthy workloads, insufficient
  monitoring, counter resets, and additional policy edge cases remain absent.
- CPU-only Qwen3 prompt 1.5 is reliable for the verified CPU-throttling package
  but remains too slow for a tight interactive budget: accepted latency was
  89.324 seconds without retrieval and 181.216 seconds with retrieval. This
  single-package follow-up does not revise the inconclusive two-case prompt 1.4
  M13 comparison or establish general reliability.
- Existing schema 1.0 experiment artifacts cannot be retroactively assigned
  terminal state or provenance after their Kubernetes Jobs have disappeared;
  they remain readable and their missing lifecycle evidence stays explicit.
