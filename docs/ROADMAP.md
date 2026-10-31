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
