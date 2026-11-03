# Project Progress

## Current milestone
M12 — Local Qwen3 inference and independent output validation (complete,
offline and real-service verified)

## Completed
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

## Next
M0–M12 are complete. Implement M13's fixed, independently reviewed paired
RAG-on/off quality evaluation. M13–M17 must complete and verify all remaining
backend, ML, retrieval, experiment, lineage, API, and reliability work before
M18 begins.

## Known limitations
- The cluster Metrics API was unavailable during M1 verification; load evidence
  used application process CPU and network receive counters instead.
- The verified workload image remains cached on the disposable kind node.
- M13–M18 are planned but not implemented. M10 and M11 are loopback-only development
  tools and do not provide production authentication, authorization, TLS, or
  deployment packaging.
- M11 has offline component coverage and a production build, but has not yet
  been exercised in a browser against live Kubernetes, Prometheus, and Qdrant
  services.
- Real M12 acceptance used a finding-free retained package. Detected-condition
  and recommendation explanations are exhaustively covered with deterministic
  offline model responses, but a real Qwen3 run over the larger six-condition,
  two-recommendation package exceeded the 600-second CPU-only request bound.
  M13 must measure this latency and validate real finding-bearing trials rather
  than treating the finding-free acceptance run as quality evidence.
- Existing schema 1.0 experiment artifacts cannot be retroactively assigned
  terminal state or provenance after their Kubernetes Jobs have disappeared;
  they remain readable and their missing lifecycle evidence stays explicit.
