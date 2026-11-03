# Evaluation Strategy

## Research Questions

1. Does retrieval of verified Kubernetes documentation, runbooks, and
   historical incidents improve the factual correctness, grounding,
   uncertainty coverage, and usefulness of local Qwen3 explanations?
2. Do deterministic resource recommendations improve their targeted condition
   without unacceptable regressions in throughput, latency, errors, resource
   use, or workload stability?
3. Can the complete backend reproduce results from immutable, traceable
   artifacts and fail safely when data or dependencies are unavailable?

## Retrieval Evaluation (M8)

M8 evaluates Qdrant retrieval independently of generation with the fixed,
reviewed graded-judgment dataset. It records the dataset digest and exact ranked
results and reports Recall@k, MRR@k, and nDCG@k. Retrieval evaluation remains a
prerequisite; a plausible generated answer cannot excuse a retrieval miss.

## RAG-on/off LLM Evaluation (M13)

Each case has paired configurations:

1. Qwen3 with the deterministic M5 facts and explicit RAG-off input.
2. Qwen3 with the same facts/settings plus verified M8 evidence.

The fixed dataset targets 20–30 independently authored and reviewed cases
covering confirmed incidents, normal workloads, insufficient monitoring data,
counter resets or other quality defects, and resource-policy edge cases. Labels
define expected facts, uncertainties, allowed recommendations and citations,
and exclusions before system output is inspected.

Required deterministic metrics are validation success, supported numerical
claims, unsupported-claim rate, citation precision and recall, finding and
uncertainty coverage, recommendation consistency, and generation latency.
Reports retain failed/invalid trials, paired differences, sample counts, and
variability. Any model-based usefulness score is supplementary and reports its
own model/prompt identity; it is never the sole correctness gate.

## Recommendation Effectiveness (M14)

Approved baseline/candidate experiments keep the load and workload identity
constant except for declared deterministic M5 resource changes. Repeated trials
compare:

- `/work` throughput and configured-target attainment;
- p95 latency and response errors;
- CPU consumption and throttled-period ratio;
- memory working set and pressure;
- Pod readiness, restarts, events, and load lifecycle stability.

Reports include absolute and relative effects, trial variation, timestamp and
window comparability, data-quality limitations, confounders, and cleanup. Fixed
guardrails classify an outcome as effective, ineffective, harmful, or
inconclusive. Missing dedicated error signals, unstable Pods, mismatched
windows, insufficient samples, or unverified lifecycle can force an
inconclusive result rather than becoming zero or success.

## Backend Acceptance (M17)

Offline evaluation replays fixed artifacts with deterministic doubles. Real
acceptance separately uses an approved bounded workload on kind, real
Prometheus samples, an isolated Qdrant collection, and the configured local
Qwen3 model. Dependency failure, timeout, cancellation, restart, idempotency,
concurrency, corruption, and cleanup checks are part of acceptance.

The versioned acceptance report records exact cluster, image, model/digest,
prompt, validator, dataset, analysis policy, repository/index, contract, and
service identities plus timestamps and artifact digests. Evidence is labeled
as fresh real, retained real, recorded, or mocked. Mandatory skipped, failed, or
inconclusive checks prevent backend acceptance and therefore block M18.

## Reproducibility and Leakage Controls

- Preserve immutable inputs, raw outputs, validation reports, exact settings,
  source versions, timestamps, and canonical digests.
- Keep dataset author and independent reviewer distinct.
- Never tune labels, thresholds, prompts, or trial exclusions from the evaluated
  results without creating and reviewing a new dataset/version.
- Keep evaluation documents out of retrievable operational knowledge unless
  explicitly intended and labeled.
- Do not claim bitwise LLM reproducibility; reproduce the recorded plan and
  report observed variation across trials.
- Distinguish offline, retained-real, and fresh real-service evidence in every
  report and in `docs/PROGRESS.md`.
