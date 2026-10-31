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

### Prometheus Collector
Retrieves real workload time series.

### Kubernetes Collector
Reads Deployment configuration, Pods, resources, and events.

### Observation Builder
Normalizes and validates collected information.

### Python Analyzer
Calculates statistics, findings, and bounded recommendations.

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
- The M0 package contains no collectors, analysis, retrieval, API, workload,
  or frontend behavior.
