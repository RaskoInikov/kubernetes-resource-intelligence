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