# Evaluation

## Research Question

Does retrieval of Kubernetes documentation, runbooks,
and historical incidents improve the factual correctness,
interpretability, and usefulness of LLM explanations?

## RAG Configurations

1. LLM without RAG.
2. LLM with documentation and runbooks.
3. LLM with documentation, runbooks, and historical incidents.

## Evaluation Dataset

Target: 20–30 independently reviewed cases.

Include:
- Confirmed incidents.
- Normal workload observations.
- Insufficient monitoring data.
- Synthetic edge cases.

## Metrics

Retrieval:
- Recall@k
- Document relevance

Analysis:
- Correctness against independent labels
- Data coverage and freshness

Future LLM evaluation:
- Factual correctness
- Evidence grounding
- Explanation usefulness
- Generation latency
- Validation success rate

## Reproducibility

Record input snapshots, document versions,
retrieval configuration, model settings, and outcomes.

Prevent evaluation-data leakage.