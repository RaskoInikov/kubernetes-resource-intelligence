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
