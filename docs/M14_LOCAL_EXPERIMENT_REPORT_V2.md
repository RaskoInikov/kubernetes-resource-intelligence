# M14 local controlled experiment report v2

## Outcome

Execution was explicitly approved on 2026-11-09 for plan
`m14-kri-workload-cpu-limit-20261109-v2`, digest
`e41ce61c3e5a64a7a01b2f35a0c707c6df606e02c294950563fb9f720d39027a`.
The read-only preflight passed, but execution stopped at A1's first mandatory
warning-event/image-drift gate. A2, the candidate rollout, B1, and B2 were not
started.

The M14 classification is **`inconclusive`**. No objective or guardrail can be
decided because the plan has no valid succeeded baseline trial and no candidate
trial. Values collected while the application was idle are retained as source
data but are not treated as load-test performance.

## Preflight

Immediately before execution:

- the approval matched the exact plan ID and digest;
- Deployment `payments/kri-workload` retained UID/resourceVersion
  `3360fb27-d522-4b1d-9774-aa9e359e301a`/`1195095`, generation 1, two ready
  replicas, target digest
  `import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91`,
  CPU `90m/140m`, and memory `109Mi/192Mi`;
- the verified load image digest was listed in the kind node's containerd
  image inventory;
- all four v2 Job and artifact IDs were absent;
- node pressure was false, Prometheus was ready, and no workload warning event
  or active prior experiment existed; and
- a no-load 20-second query returned all ten required metric families, 70
  series, 350 samples, and no missing metric family.

The two approved baseline error-counter initialization requests returned the
expected HTTP 400 outside the measurement window. Pod readiness and restart
counts stayed unchanged after two scrapes.

## A1 stop condition

Job `kri-load-m14v2-base-1-20261109` was created at
`2026-11-09T07:44:18Z` with `backoffLimit: 0`, a 180-second active deadline,
and image reference
`docker.io/library/import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e`.
The Pod never started. Kubelet did not match that digest-form reference to the
cached kind import, attempted a registry pull, and reported `ErrImagePull` and
`ImagePullBackOff` because the synthetic `import-2026-11-09` repository is not
pullable from Docker Hub.

Changing the Job to the verified source tag or recreating it would have changed
the plan's exact image reference after approval. Execution therefore stopped
without substitution. The controller deleted A1 and recorded it as `stopped`
at `2026-11-09T07:46:09.240945Z` with Job UID
`393899e5-0be9-456e-807f-77a840bd47a4`.

A read-only failure-window observation covers `2026-11-09T07:44:18Z` through
`2026-11-09T07:45:52.524139Z`. It contains all ten metric families and 70
normalized series, but quality is `degraded` because no related application
event was retained. Its zero throughput and throttling describe an idle target,
not a completed A1 load trial. Latency and error ratio are unavailable.

Retained sources are:

| Artifact | SHA-256 |
| --- | --- |
| A1 experiment record | `db0c421314801da7f56f149338e77c7b11359cd1d5b7525b6a6f9a356a1547e9` |
| A1 observation | `e594de2c109b95b66d594c6a400f12458db381a2da727f49dcd4967bda1b4561` |
| Effectiveness report content | `7e24c6a96bded1515196e00960b93e8693fc1a617d04a04e09366f17a161c4dc` |
| Effectiveness envelope file | `b9086602e466ef5dc0c720efa95ac5bfec613d9d4001e6413312dcc99fd37327` |

## Policy result

The evaluator reported blocking issues for the declared image confounder,
non-succeeded lifecycle, short observation window, incomplete measurements,
insufficient repetitions, and incomplete required metrics. It produced no
baseline/candidate means, differences, variation, objective decisions, or
guardrail decisions. In particular, the plan does not provide evidence for or
against the `220m` recommendation.

## Rollback and cleanup

Rollback is **verified by unchanged baseline state**; no compensating apply was
needed because the candidate was never deployed. After cleanup:

- all four fixed v2 Job names are absent;
- the only created v2 Job and its owned Pod were deleted;
- no A2, B1, or B2 experiment or observation artifact exists;
- the Deployment still has its original UID, resourceVersion, generation,
  image, resources, and 2/2 readiness;
- the original ReplicaSet `kri-workload-698f67d7f6` remains the sole target
  ReplicaSet at 2/2; and
- both original application Pod UIDs, image digests, readiness, and historical
  restart counts are unchanged.

The only executed mutations were the two approved counter-initialization HTTP
requests, creation of the approved A1 Job and owned Pod, and deletion of that
Job and Pod. No Deployment, Service, monitoring resource, namespace, image
cache, A2/B1/B2 Job, or unrelated resource was changed.

## Reproduce the offline evaluation

```bash
python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v2.json \
  --m14-approval evaluation/m14-local-cpu-limit-approval-v2.json \
  --m14-trials evaluation/m14-local-cpu-limit-trials-v2.json \
  --report-id <new-report-id> \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/<new-report-id>.json
```

The retained report path is immutable, so reproduction must use a new ID and
output path.

## Image-reference correction

Follow-up validation keeps this stopped execution immutable. Future M14 load
Jobs must reference the node-cached tag
`kri-workload:lifecycle-smoke-20261109`, set `imagePullPolicy: Never`, and
require runtime `imageID`
`docker.io/library/import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e`.
The workload controller now renders that no-pull policy for load Jobs only;
application Deployments remain `IfNotPresent`. A standalone no-load Pod
validation is recorded in `docs/PROGRESS.md`; no v2 trial was retried.
