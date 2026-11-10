# M14 local controlled experiment plan v2

Status: **approved on 2026-11-09; execution stopped on failed-to-start A1**.
This revision replaces the stopped v1 execution attempt but does not alter its
retained artifacts or inconclusive report. The v2 execution record is in
`docs/M14_LOCAL_EXPERIMENT_REPORT_V2.md`.
The prepared, unapproved successor is
`docs/M14_LOCAL_EXPERIMENT_PLAN_V3.md`.

The machine-readable plan is
`evaluation/m14-local-cpu-limit-plan-v2.json`, SHA-256
`e41ce61c3e5a64a7a01b2f35a0c707c6df606e02c294950563fb9f720d39027a`.
Any later approval record must name that exact plan ID and digest.

## Fixed identities and preflight gates

| Item | Required value |
| --- | --- |
| Context / cluster | `kind-kube-optimizer` / `kind-kube-optimizer` |
| Namespace / target | `payments` / Deployment `kri-workload` |
| Target application image | `docker.io/library/import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91` |
| Verified load image | `docker.io/library/import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e` |
| Verified load image source tag | `kri-workload:lifecycle-smoke-20261109` |
| Baseline | 2 replicas; CPU `90m/140m`; memory `109Mi/192Mi` |
| Candidate | 2 replicas; CPU `90m/220m`; memory `109Mi/192Mi` |

The load image was verified by the separate successful 10-second experiment
`lifecycle-smoke-20261109`. The source tag is descriptive only; all v2 load
Jobs must set `KRI_WORKLOAD_IMAGE` to the immutable verified digest above, and
every created Pod must resolve to that same `imageID` before its trial is
accepted. The plan contract's `image_identity` continues to pin the target
application image, so the two identities remain distinguishable.

Before approval or mutation, repeat the complete read-only preflight from v1.
Also require all four v2 Job names and artifact IDs to be absent, verify the
load digest is present on the kind node, verify the target application digest,
Deployment UID, configuration and readiness, and query every required metric
over a no-load interval. Abort on drift, missing data, node pressure, warning
events, unexpected co-tenants, or an active earlier experiment. Restoring a
loopback-only Prometheus port-forward is non-persistent and is not a Kubernetes
resource mutation.

## Fresh fixed trials

The order is A1, A2, candidate rollout, B1, B2, rollback. Trials never overlap;
each is followed by artifact capture and a 60-second quiet interval.

| Trial | Role | Experiment / Job suffix | Observation ID | Target configuration |
| --- | --- | --- | --- | --- |
| A1 | baseline 1 | `m14v2-base-1-20261109` | `obs-m14v2-base-1-20261109` | `90m/140m`, `109Mi/192Mi`, 2 replicas |
| A2 | baseline 2 | `m14v2-base-2-20261109` | `obs-m14v2-base-2-20261109` | same as A1 |
| B1 | candidate 1 | `m14v2-cand-1-20261109` | `obs-m14v2-cand-1-20261109` | `90m/220m`, `109Mi/192Mi`, 2 replicas |
| B2 | candidate 2 | `m14v2-cand-2-20261109` | `obs-m14v2-cand-2-20261109` | same as B1 |

Every trial retains the existing controls: mixed load, concurrency 4, target 20
requests/second, duration 120 seconds, Job active deadline 180 seconds, and a
120-second observation window from the reconciled Job start timestamp at
5-second steps. Only a `succeeded` Job is eligible. A failed lifecycle,
including `DeadlineExceeded`, stops the sequence and produces an inconclusive
evaluation.

## Exact mutations requiring later approval

Approval bound the exact plan ID and SHA-256 to only these operations. The
execution report records which authorized operations actually occurred:

1. Send one bounded invalid `/work` request to each of the two current target
   Pods to initialize `kri_http_request_errors_total`, then wait for two
   scrapes. Repeat once for each of the two Pods created by the candidate
   rollout. These requests mutate application counter state but do not create,
   patch, or delete Kubernetes resources and remain outside measurement
   windows.
2. Create exactly four namespaced Jobs through `kri-workload start-load`:
   `kri-load-m14v2-base-1-20261109`,
   `kri-load-m14v2-base-2-20261109`,
   `kri-load-m14v2-cand-1-20261109`, and
   `kri-load-m14v2-cand-2-20261109`. Each Job has `backoffLimit: 0`,
   `activeDeadlineSeconds: 180`, and the verified immutable load image digest.
   The Job controller may create exactly one owned Pod for each Job; retries are
   disabled, so a replacement load Pod is not an accepted trial and stops the
   sequence.
3. After A1 and A2 only, invoke the scoped controller once to apply the
   candidate. The only permitted target Pod-template value change is
   `/spec/template/spec/containers[name=application]/resources/limits/cpu`
   from `140m` to `220m`. Because the controller applies both its Deployment
   and Service manifests, approval also covers re-application of the existing
   `kri-workload` Service with no allowed Service spec change. Set
   `KRI_WORKLOAD_IMAGE=kri-workload:local` for this operation so the target
   image is not changed. The Deployment controller will create or scale its
   owned ReplicaSet and replace the two application Pods as the expected
   consequence of the Pod-template change; no unrelated workload may be
   touched.
4. After B2, or immediately after any post-rollout stop condition, invoke the
   scoped controller once to roll back the same CPU-limit field from `220m` to
   `140m`. This likewise re-applies the unchanged Service and must use
   `KRI_WORKLOAD_IMAGE=kri-workload:local`. The Deployment controller may scale
   the retained baseline ReplicaSet or create an equivalent owned ReplicaSet,
   replace the two candidate Pods, and delete only Deployment-owned Pods.
5. Delete each created v2 Job, up to the four fixed names, after it has a
   terminal experiment record and immutable observation. Deleting a Job also
   garbage-collects only its owned Pod. Never delete the application Deployment
   or Service.

The API server will update normal server-managed metadata such as
`resourceVersion`, `generation`, and managed fields. The scoped controller also
updates its last-applied annotation to the reviewed manifest. Those metadata
changes and the owned controller consequences above are included in the later
approval scope; they do not authorize another user-selected spec change.

The candidate and rollback controller commands are fixed as follows:

```bash
KRI_WORKLOAD_IMAGE=kri-workload:local kri-workload deploy \
  --cpu-request 90m --cpu-limit <220m-candidate-or-140m-rollback> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2
```

Each trial command is fixed as follows, substituting only the listed ID and its
already-deployed target configuration:

```bash
KRI_WORKLOAD_IMAGE='docker.io/library/import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e' \
  kri-workload start-load \
  --cpu-request 90m --cpu-limit <140m-baseline-or-220m-candidate> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 20 \
  --duration-seconds 120 --experiment-id <fixed-v2-id>
```

Image building/loading, monitoring resource application, namespace creation,
changes to requests, memory, replicas, target image, any non-v2 Job, and any
other Deployment or Service change are outside this plan and require separate
approval. If the verified image is absent from the node, stop; this plan does
not authorize loading or rebuilding it.

## Objectives, guardrails, and uncertainty

The existing policy is unchanged:

- reduce mean throttled-period ratio by at least 20% and to at most 0.60;
- improve target attainment by at least 10% and reach at least 0.75 (15 rps of
  the 20 rps target); and
- do not reduce throughput per average CPU core.

Guardrails remain at most 5% p95-latency regression with candidate p95 no
higher than 0.75 seconds, error ratio no higher than 1%, 100% readiness, zero
candidate container restarts, and at most 15% aggregate p95-memory regression
with an absolute 384 MiB ceiling. Every objective and guardrail must pass.
Missing or incomparable signals, fewer than two trials per role, lifecycle or
digest failure, drift, or a declared confounder yields `inconclusive`.

Two trials per role preserve observed values, means, and population standard
deviations but do not establish a production effect or confidence interval.
The sequential order can retain temporal or co-tenant confounding; any observed
drift must be declared rather than adjusted away.

## Artifacts and evaluation

Retain lifecycle-reconciled experiment records under `results/experiments/`
and immutable observations under `results/observations/`. After rollback and
cleanup are independently verified, create a four-entry digest-bound v2 trial
manifest. Do not create placeholder trial digests. Evaluation remains offline:

```bash
python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v2.json \
  --m14-approval evaluation/<explicit-v2-approval>.json \
  --m14-trials evaluation/<complete-v2-trial-manifest>.json \
  --report-id m14-kri-workload-cpu-limit-20261109-v2 \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/m14-kri-workload-cpu-limit-20261109-v2.json
```

The evaluator does not mutate Kubernetes. The retained approval is
`evaluation/m14-local-cpu-limit-approval-v2.json`.
