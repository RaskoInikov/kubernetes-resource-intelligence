# M14 local controlled experiment plan v3

Status: **approved on 2026-11-09; execution stopped on failed A1**. V1 and v2
remain immutable historical attempts. The v3 execution record is in
`docs/M14_LOCAL_EXPERIMENT_REPORT_V3.md`.

The machine-readable envelope is
`evaluation/m14-local-cpu-limit-plan-v3.json`, SHA-256
`0a384b519d69d0242ba739b797e0235f0d943f77f9cc74bb416985d476c4a3d4`.
Any execution requires a separate positive approval bound to that exact v3
plan ID and digest.

## Fixed identities and image resolution

| Item | Required value |
| --- | --- |
| Context / cluster | `kind-kube-optimizer` / `kind-kube-optimizer` |
| Namespace / target | `payments` / Deployment `kri-workload` |
| Target application image | `docker.io/library/import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91` |
| Load Job image reference | `kri-workload:lifecycle-smoke-20261109` |
| Load Job pull policy | `Never` |
| Required load runtime image ID | `docker.io/library/import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e` |
| Baseline | 2 replicas; CPU `90m/140m`; memory `109Mi/192Mi` |
| Candidate | 2 replicas; CPU `90m/220m`; memory `109Mi/192Mi` |

The cached tag/policy/runtime-digest combination was verified by a standalone
no-load Pod on 2026-11-09. Kubernetes reported the image already present,
resolved it to the required runtime digest, imported `kri_workload.load`, and
exited 0 without a registry attempt. The controller now renders `Never` for
load Jobs only; application Deployments retain `IfNotPresent`.

The plan contract's `image_identity` pins the target application image. The
load reference and runtime identity are separately fixed here and in the
machine plan's stop conditions because schema 1.0 has no separate load-image
field.

## Read-only approval gate

Immediately before any approval or execution, repeat the complete read-only
preflight. Require:

- exact context, namespace, Deployment UID, target image, resources, two ready
  replicas, Pod identities/restarts, and stable co-tenants;
- cached load tag and its required runtime digest in the kind node inventory;
- a rendered v3 load Job whose image is the cached tag and whose pull policy is
  `Never`;
- all four v3 Job, experiment, and observation IDs absent;
- a Ready node without memory, disk, or PID pressure and no new warning event;
- Prometheus ready with both application Pods and cAdvisor healthy; and
- usable samples for all M14 metric families over a disposable no-load window.

Abort without mutation on drift or missing evidence. The existing loopback-only
Prometheus port-forward is not a Kubernetes resource. If the cached image is
absent or resolves differently, stop: v3 does not authorize building or loading
an image.

## Fresh fixed trials

The order remains A1, A2, candidate rollout, B1, B2, rollback. Trials never
overlap and each is followed by artifact capture and a 60-second quiet period.

| Trial | Role | Experiment / Job suffix | Observation ID | Target configuration |
| --- | --- | --- | --- | --- |
| A1 | baseline 1 | `m14v3-base-1-20261109` | `obs-m14v3-base-1-20261109` | `90m/140m`, `109Mi/192Mi`, 2 replicas |
| A2 | baseline 2 | `m14v3-base-2-20261109` | `obs-m14v3-base-2-20261109` | same as A1 |
| B1 | candidate 1 | `m14v3-cand-1-20261109` | `obs-m14v3-cand-1-20261109` | `90m/220m`, `109Mi/192Mi`, 2 replicas |
| B2 | candidate 2 | `m14v3-cand-2-20261109` | `obs-m14v3-cand-2-20261109` | same as B1 |

Each trial uses mixed load, concurrency 4, target 20 requests/second, duration
120 seconds, Job active deadline 180 seconds, and an exact 120-second metrics
window from the reconciled Job start at 5-second steps. Only a `succeeded` Job
with one owned Pod, zero restarts, the cached tag, and the required runtime
image ID is eligible. Any failed lifecycle or replacement Pod stops execution.

## Exact mutations requiring later approval

Approval bound the exact v3 plan ID and digest to only these operations. The
execution report identifies which authorized operations occurred:

1. One bounded invalid `/work` request to each current baseline application Pod
   to initialize the error counter, outside all measurement windows; repeat
   once on each candidate Pod after rollout. These requests alter application
   metric state but do not change Kubernetes resources.
2. Creation of exactly these four namespaced Jobs through the scoped workload
   controller:
   `kri-load-m14v3-base-1-20261109`,
   `kri-load-m14v3-base-2-20261109`,
   `kri-load-m14v3-cand-1-20261109`, and
   `kri-load-m14v3-cand-2-20261109`. Each has `backoffLimit: 0`,
   `activeDeadlineSeconds: 180`, image
   `kri-workload:lifecycle-smoke-20261109`, and `imagePullPolicy: Never`.
   The Job controller may create exactly one owned Pod for each Job.
3. After two succeeded baseline trials only, one scoped controller apply of the
   candidate. The sole permitted user-selected Pod-template change is
   `/spec/template/spec/containers[name=application]/resources/limits/cpu`
   from `140m` to `220m`. The controller re-applies the existing Service with
   no permitted Service spec change and must use
   `KRI_WORKLOAD_IMAGE=kri-workload:local` so the target image stays fixed. The
   Deployment controller may create/scale its owned ReplicaSet and replace the
   two application Pods.
4. After B2, or immediately after any post-rollout stop condition, one scoped
   controller rollback apply of that CPU-limit field from `220m` to `140m`,
   again with the unchanged Service and target image. The Deployment controller
   may scale/create its owned ReplicaSet and replace only its two candidate
   Pods.
5. Deletion of each created v3 Job, up to the four fixed names, only after its
   terminal record and immutable observation are retained. Kubernetes may
   garbage-collect only that Job's owned Pod. The application Deployment and
   Service must never be deleted.

Normal API-server metadata updates (`resourceVersion`, `generation`, managed
fields, and the scoped controller's last-applied annotation) and the listed
owned-controller consequences are included. They authorize no other spec or
resource mutation.

The candidate/rollback command is fixed, substituting only the reviewed CPU
limit:

```bash
KRI_WORKLOAD_IMAGE=kri-workload:local kri-workload deploy \
  --cpu-request 90m --cpu-limit <220m-candidate-or-140m-rollback> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2
```

Each load command is fixed, substituting only the listed v3 ID and its matching
already-deployed target CPU limit:

```bash
KRI_WORKLOAD_IMAGE=kri-workload:lifecycle-smoke-20261109 \
  kri-workload start-load \
  --cpu-request 90m --cpu-limit <140m-baseline-or-220m-candidate> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 20 \
  --duration-seconds 120 --experiment-id <fixed-v3-id>
```

Image build/load, monitoring-resource application, namespace creation, target
image changes, request/memory/replica changes, non-v3 Jobs, diagnostic Pods,
and any other Deployment or Service change are outside v3.

## Unchanged objectives, guardrails, and uncertainty

Policy 1.0 is byte-for-byte equivalent to v2 for objectives and guardrails:

- reduce mean throttled-period ratio by at least 20% and to at most 0.60;
- improve target attainment by at least 10% and reach at least 0.75; and
- do not reduce throughput per average CPU core.

Guardrails allow at most 5% p95-latency regression with candidate p95 no higher
than 0.75 seconds, error ratio no higher than 1%, 100% readiness, zero candidate
container restarts, and at most 15% aggregate p95-memory regression with an
absolute 384 MiB ceiling. Every objective and guardrail must pass. Missing or
incomparable signals, fewer than two trials per role, lifecycle/digest failure,
drift, or a declared confounder yields `inconclusive`.

Two trials per role preserve per-trial values, means, and population standard
deviations but do not establish a production effect or confidence interval.
Sequential-order or co-tenant drift must be declared, never adjusted away.

## Artifacts and offline evaluation

Retain reconciled experiment records under `results/experiments/` and immutable
observations under `results/observations/`. Only after all four trials, rollback,
and cleanup are verified may a digest-bound v3 trial manifest be created. Do
not create placeholder entries.

```bash
python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v3.json \
  --m14-approval evaluation/<explicit-v3-approval>.json \
  --m14-trials evaluation/<complete-v3-trial-manifest>.json \
  --report-id m14-kri-workload-cpu-limit-20261109-v3 \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/m14-kri-workload-cpu-limit-20261109-v3.json
```

The evaluator is read-only. The retained approval is
`evaluation/m14-local-cpu-limit-approval-v3.json`.
