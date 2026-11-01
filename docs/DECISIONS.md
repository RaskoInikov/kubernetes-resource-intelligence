# Architectural Decisions

## D001 — Storage
Use Prometheus for metrics, Qdrant for vector retrieval,
and versioned JSON/Markdown for reproducible evidence.

## D002 — Model
Use one local LLM in a later development phase.

## D003 — Analysis
Numerical recommendations are deterministic Python calculations.

## D004 — RAG
Use one Qdrant collection with document-type metadata.

## D005 — User Experience
Two-panel interface: workload control and incident analysis.

## D006 — Safety
No autonomous Kubernetes remediation.

## D007 — Scope
The first implementation phase ends at the LLM input package.

## D008 — Workloads
Configure workload behavior independently of incident labels.

## D009 — M1 Kubernetes Boundary
Use a fixed-name Deployment and Service for the disposable application and one
DNS-label-safe Job per load experiment. Target only a configured, pre-existing
namespace, pass context and namespace to every `kubectl` call, and keep
application and load lifecycles independent.

## D010 — M2 Metrics Sources
Use kubelet/cAdvisor for container CPU usage, CPU throttling, and memory working
set. Instrument the disposable application directly for HTTP throughput, errors,
and latency. Prometheus scrapes both sources and keeps raw series distinct; M2
does not calculate observations or substitute absent metrics.

## D011 — Disposable Prometheus
Run project-owned Prometheus resources in `kri-monitoring` with emptyDir storage,
six-hour retention, a pinned image, non-root security, and least-scope RBAC for
node proxy metrics and annotated Pod discovery. Do not alter unrelated monitoring
installations.

## D012 — Deterministic Analysis Policy
Analyze resource signals per Pod/container and aggregate only HTTP context.
Policy version 1.1 detects CPU throttling at 20%, CPU peak/limit saturation at
90%, memory max/limit pressure at 90%, and request mismatch at 120%. Do not
repair counter resets or infer negative findings from missing inputs. Emit only
increase recommendations, round them to Kubernetes units, cap them at twice the
current setting, and require explicit approval for every resource change.
Coalesce repeated counter evaluations before calculating CPU peaks. Treat
throttling at 50%, limit utilization at 100%, and request utilization at 150%
as critical; lower detected values are warnings. Report finite-window,
scrape-resolution, near-threshold, and recommendation-cap uncertainty.

## D013 — Canonical Knowledge Format
Store canonical M6 knowledge as human-readable Markdown registered by one
versioned JSON manifest. The manifest, not a vector database, owns document
identity, semantic version, verification status, provenance, relative path, and
content digest. Reject checksum drift, unsafe or duplicate paths, unregistered
Markdown, incomplete document-type coverage, and invalid verification metadata.
Keep loading and inspection local and read-only; Qdrant indexing begins in M7.

## D014 — Derived Qdrant Knowledge Index
Use one configured project collection with cosine vectors from a deterministic,
versioned local feature-hashing embedder. Chunk canonical Markdown by section
with stable bounded chunks and deterministic UUID point IDs. Store complete
document, verification, source, chunk, repository, and implementation metadata
in every payload. Synchronize only project-owned points and fail on incompatible
collection schema instead of recreating it. Default retrieval to verified
documents. Treat Qdrant as rebuildable derived state; M6 files remain canonical.

## D015 — Pretrained Semantic Embeddings
Supersede D014's local feature hashing with the Apache-2.0
`sentence-transformers/all-MiniLM-L6-v2` model executed locally through
FastEmbed. Use its 384-dimensional normalized dense vectors for both indexing
and queries, record the exact model name and embedder version in derived
payloads, and bump the incompatible Qdrant index schema to 2.0. Keep offline
tests deterministic and network-free by injecting a model double through the
same validated embedding boundary.

## D016 — Analysis-Grounded Retrieval Evaluation
Construct M8 retrieval queries only from validated M5 condition and
recommendation fields, and retain every originating analysis reference in the
retrieved evidence package. Query once per recommendation and group remaining
conditions by type to avoid replica-count-dependent duplicate retrieval. Measure
quality against a fixed, separately authored and reviewed graded-judgment
dataset using Recall@k, MRR@k, and nDCG@k. Record the dataset digest and exact
results; report threshold failure without changing judgments or hiding misses.
Classify query intent into reference, runbook, or incident scope, retrieve 20
semantic candidates, and apply a fixed 85% semantic/15% exact-term rerank. Keep
both component scores so the final ordering remains inspectable.

## D017 — Validated LLM Handoff
Represent M9 as structured, versioned data rather than free-form prompt text.
Preserve every M5 finding and uncertainty exactly, include only its transitive
statistic/evidence closure, and bind the complete M5 and M8 sources with
canonical digests. Bound retrieved text to three ranked hits per query, twelve
deduplicated excerpts, and 600 characters per excerpt while recording retrieved
and included counts. Persist immutable JSON inside a package-digest envelope.
Reject mismatched or dangling inputs; do not recalculate numbers, invoke an LLM,
or infer Kubernetes changes.

## D018 — Thin Versioned HTTP Orchestration
Expose M1-M9 through one `/api/v1` FastAPI boundary whose successful bodies are
the existing contracts. Keep Kubernetes mutation explicit and separate from all
collection/analysis routes. Persist only artifacts whose owning milestones
already define immutable stores (M4 observations and M9 packages); return M5
analysis and M8 evidence directly and require clients to pass those exact
contracts forward. Query only an already synchronized Qdrant index. Use typed
422/404/409/502 failures, dependency-injected services for offline testing, and
no implicit LLM inference or remediation.
