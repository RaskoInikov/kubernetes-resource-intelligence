# M14 local controlled experiment plan v4

Status: **prepared and unapproved; experiments and Kubernetes mutations are
not authorized**. V1-v3 remain immutable historical attempts.

The machine-readable envelope is
`evaluation/m14-local-cpu-limit-plan-v4.json`, with plan SHA-256
`30b702973e197b197d55919b18c4be690f8af8e8bdba98b8a6db859197aaad7c`.
Execution requires a separate positive approval quoting that exact plan ID and
digest. Any plan or scope change requires a new digest and approval.

## Fixed identities and configurations

| Item | Required value |
| --- | --- |
| Plan ID | `m14-kri-workload-cpu-limit-20261109-v4` |
| Context / cluster | `kind-kube-optimizer` / `kind-kube-optimizer` |
| Namespace / target | `payments` / Deployment and Service `kri-workload` |
| Deployment UID | `3360fb27-d522-4b1d-9774-aa9e359e301a` |
| Target image ID | `docker.io/library/import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91` |
| Baseline | 2 replicas; CPU `90m/140m`; memory `109Mi/192Mi` |
| Candidate | 2 replicas; CPU `90m/220m`; memory `109Mi/192Mi` |
| Load image tag | `kri-workload:schema12-timeout-20261109` |
| Local load image ID | `sha256:7a608b497c785452d65fbf9ebd06183d4da29cf6237120fd56de57b489a4733b` |
| Required load runtime image ID | `docker.io/library/import-2026-11-09@sha256:3980b56b915b631157ca6bf8df8ae6c77f503fc77eb7881c25ef402e3325eba8` |
| Pull policy | `Never` |

The load image completed the separately approved real-cluster verification in
`results/experiments/schema12-timeout-20261109.json` (SHA-256
`57e3a9cadaf9b6a376d6f2651850e7867a640f4d7a000a561c6614296ab07908`).
It retained four request timeouts in a schema-1.1 summary while exiting 0 and
completing its Job; the controller persisted the same evidence in a succeeded
schema-1.2 experiment record. V4 authorizes no image build, load, pull, retag,
or cache modification.

## Fresh trials and ordering

Trials run sequentially in this exact order: A1, A2, candidate rollout, B1,
B2, rollback. They never overlap. Each terminal trial is reconciled and its
observation retained before its Job is deleted; a 60-second quiet period
separates trials.

| Trial | Role | Experiment ID / Job suffix | Observation ID | CPU limit |
| --- | --- | --- | --- | --- |
| A1 | baseline 1 | `m14v4-base-1-20261109` | `obs-m14v4-base-1-20261109` | `140m` |
| A2 | baseline 2 | `m14v4-base-2-20261109` | `obs-m14v4-base-2-20261109` | `140m` |
| B1 | candidate 1 | `m14v4-cand-1-20261109` | `obs-m14v4-cand-1-20261109` | `220m` |
| B2 | candidate 2 | `m14v4-cand-2-20261109` | `obs-m14v4-cand-2-20261109` | `220m` |

Every trial uses mixed load, concurrency 4, a target rate of 20 requests per
second, a 120-second duration, `backoffLimit: 0`, and a 180-second active
deadline. The metrics interval is exactly 120 seconds from the reconciled
Kubernetes Job start, queried at 5-second steps.

## Schema-1.2 lifecycle and error evidence

A trial is eligible only when exactly one Job-owned Pod uses the fixed cached
image and runtime digest, has zero restarts, exits 0 with reason `Completed`,
and the Job reaches `Complete` without a failed condition. Controller
reconciliation must persist a schema-1.2 `succeeded` experiment record whose
schema-1.1 `load_summary` exactly matches the Pod termination message and exit
code. The summary must have `execution_status: completed`, no execution failure
reason, zero stuck workers, and internally consistent counts.

Request failures and timeouts are measured client outcomes and do not by
themselves fail a Job. They remain strict evaluation evidence: M14 computes the
client failure ratio from the summary and uses the larger of that ratio and the
application HTTP error ratio for the unchanged error guardrail. Missing either
source is blocking and produces `inconclusive`; it is never replaced with zero.
A failed Job, stuck worker, contradictory termination evidence, missing
summary, or rejected reconciliation stops the sequence.

## Mandatory read-only preflight

Repeat the full preflight immediately before requesting approval and again
after approval, before any mutation. Require:

- exact context, namespace, Deployment UID, target image, baseline resources,
  two ready replicas, application Pod identities/restarts, Service selector,
  and stable co-tenants;
- the fixed load tag in local Docker and the kind node, resolving to the exact
  local and runtime image IDs above;
- an offline render for each of the four Jobs matching its fixed ID, load,
  resources, `imagePullPolicy: Never`, `terminationMessagePolicy: File`,
  `/dev/termination-log`, and target `http://kri-workload:8080/work`;
- all four Job names, experiment artifacts, observation artifacts, and any V4
  approval or trial manifest absent;
- a Ready node without memory, disk, or PID pressure and no new warning event;
- Prometheus Deployment and Service Ready, a loopback-only port-forward to
  Service `kri-prometheus`, both application targets and cAdvisor healthy, and
  usable samples for all ten M14 metric families over a disposable no-load
  window; and
- the machine plan validates against the current contract and its objectives
  and guardrails remain exactly equal to V3 policy 1.0.

Stop without mutation on any mismatch. Do not repair drift, replace artifacts,
or restore monitoring under this plan. At `2026-11-09T11:23:36Z`, the existing
loopback-only port-forward was alive and Prometheus was Ready. Prometheus,
cAdvisor, and both application targets were healthy with no scrape error; all
ten required families returned 42 series and 294 finite samples over a
30-second no-load window. This read-only snapshot authorizes no experiment and
must still be repeated after approval immediately before execution.

## Exact Kubernetes mutations requiring later approval

Approval of this plan would authorize only:

1. One bounded invalid `/work` request to each of the two current baseline
   application Pods, outside all measurement windows, to initialize the error
   counter; repeat once on each of the two candidate Pods after rollout. These
   four HTTP requests alter application metric state but do not mutate
   Kubernetes resources.
2. Creation through the scoped workload controller of exactly these Jobs:
   `kri-load-m14v4-base-1-20261109`,
   `kri-load-m14v4-base-2-20261109`,
   `kri-load-m14v4-cand-1-20261109`, and
   `kri-load-m14v4-cand-2-20261109`. Each uses the fixed load configuration,
   cached image, pull policy, termination evidence, resources, and Job controls.
   The Job controller may create exactly one owned Pod per Job.
3. Only after A1 and A2 both succeed with complete evidence, one scoped
   controller apply of the candidate. The sole permitted user-selected
   Pod-template change is
   `/spec/template/spec/containers[name=application]/resources/limits/cpu`
   from `140m` to `220m`. The controller re-applies the existing Service with
   no permitted Service spec change and uses
   `KRI_WORKLOAD_IMAGE=kri-workload:local`. The Deployment controller may
   create/scale its owned ReplicaSets and replace the two application Pods.
4. After B2, or immediately after any stop condition following candidate
   rollout, one scoped rollback apply changing only that CPU limit from `220m`
   to `140m`, with the same target image and unchanged Service. The Deployment
   controller may create/scale its owned ReplicaSets and replace only its
   candidate Pods.
5. Deletion of each created V4 Job only after its terminal schema-1.2 record
   and immutable observation are retained. Kubernetes may garbage-collect only
   that Job's owned Pod. The application Deployment and Service are never
   deleted.

Normal API-server metadata/status changes and the listed controller-owned
rollout consequences are included. Local creation of the four experiment
records, four observations, final digest-bound trial manifest, approval record,
and effectiveness report is evidence persistence, not Kubernetes mutation.

No namespace, ConfigMap, Secret, monitoring resource, image cache, non-V4 Job,
diagnostic Pod, request/memory/replica setting, target image, or other
Deployment/Service field may be created, patched, restarted, scaled, deleted,
or otherwise changed.

## Fixed commands

Each load command substitutes only its table ID and already-deployed CPU limit:

```bash
KRI_K8S_CONTEXT=kind-kube-optimizer \
KRI_K8S_NAMESPACE=payments \
KRI_WORKLOAD_IMAGE=kri-workload:schema12-timeout-20261109 \
  .venv/bin/kri-workload start-load \
  --cpu-request 90m --cpu-limit <140m-baseline-or-220m-candidate> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 20 \
  --duration-seconds 120 --experiment-id <fixed-v4-id>
```

Candidate and rollback substitute only the reviewed CPU limit:

```bash
KRI_K8S_CONTEXT=kind-kube-optimizer \
KRI_K8S_NAMESPACE=payments \
KRI_WORKLOAD_IMAGE=kri-workload:local \
  .venv/bin/kri-workload deploy \
  --cpu-request 90m --cpu-limit <220m-candidate-or-140m-rollback> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2
```

## Unchanged objectives, guardrails, and uncertainty

Policy 1.0 is exactly equal to V3:

- reduce mean throttled-period ratio by at least 20% and to at most 0.60;
- improve target attainment by at least 10% and reach at least 0.75; and
- do not reduce throughput per average CPU core.

Every objective is required. Guardrails permit at most 5% p95-latency
regression with candidate p95 no greater than 0.75 seconds, error ratio no
greater than 1%, 100% readiness, zero candidate container restarts, and at most
15% aggregate p95-memory regression with an absolute 384 MiB ceiling. Every
guardrail must pass. Missing/incomparable evidence, fewer than two trials per
role, lifecycle/digest failure, drift, or a declared confounder yields
`inconclusive`.

Two trials retain individual values, means, and population standard deviations
but do not establish a production effect or confidence interval. Sequential
order, co-tenant changes, scrape gaps, rollouts, and other confounders are
preserved, never adjusted away.

## Artifacts and evaluation

Do not create placeholder approval or trial artifacts. After explicit approval,
retain each reconciled record under `results/experiments/` and each observation
under `results/observations/`. Create
`evaluation/m14-local-cpu-limit-trials-v4.json` only after all four trials have
immutable digests. Evaluate only after rollback and cleanup are verified:

```bash
.venv/bin/python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v4.json \
  --m14-approval evaluation/m14-local-cpu-limit-approval-v4.json \
  --m14-trials evaluation/m14-local-cpu-limit-trials-v4.json \
  --report-id m14-kri-workload-cpu-limit-20261109-v4 \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/m14-kri-workload-cpu-limit-20261109-v4.json
```

The evaluator is read-only. A stop before four valid trials remains
`inconclusive`; it does not authorize filling missing entries or continuing
past a stop condition.
