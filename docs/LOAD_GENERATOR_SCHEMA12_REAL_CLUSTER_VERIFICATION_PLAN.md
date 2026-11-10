# Load-generator schema-1.2 real-cluster verification plan

Status: **prepared and unapproved; no mutation or load is authorized**.

Plan ID: `load-generator-schema12-timeout-verification-20261109`

Execution requires a separate positive approval quoting this plan ID and the
exact SHA-256 of this file reported in `docs/PROGRESS.md`. Any change to this
file invalidates the approval.

## Purpose and boundary

Use one short, disposable load Job to verify the updated outcome semantics in
the local kind cluster:

1. at least one client request timeout is retained in the schema-1.1 load
   summary;
2. the load process still exits 0 and the Job reaches `Complete` when no worker
   is stuck; and
3. controller reconciliation atomically persists the same summary in a
   succeeded schema-1.2 experiment record.

This is a lifecycle/evidence check, not an M14 baseline or candidate trial. It
does not collect an M14 observation, evaluate a recommendation, or authorize
any application or monitoring-resource change.

## Fixed identity and bounded load

| Item | Required value |
| --- | --- |
| Context / cluster | `kind-kube-optimizer` / `kind-kube-optimizer` |
| Namespace | `payments` |
| Application | existing Deployment and Service `kri-workload` |
| Application identity | Deployment UID `3360fb27-d522-4b1d-9774-aa9e359e301a`, generation `1`, resourceVersion `1195095` |
| Application image ID | `docker.io/library/import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91` |
| Application configuration | 2 replicas; CPU `90m/140m`; memory `109Mi/192Mi` |
| Application Pods | `kri-workload-698f67d7f6-8cwhn` / UID `994a1e5c-74fb-4062-a38f-b1843d5ec8dc` / 3 restarts; `kri-workload-698f67d7f6-p92q8` / UID `a406d4fe-73ba-463d-ab7c-6ec76da39ea5` / 3 restarts |
| Experiment ID | `schema12-timeout-20261109` |
| Job | `kri-load-schema12-timeout-20261109` |
| New image tag | `kri-workload:schema12-timeout-20261109` |
| Pull policy | `Never` |
| Load | mixed; concurrency 4; 100 requests/second; 15 seconds |
| Job controls | `backoffLimit: 0`; `activeDeadlineSeconds: 75`; restart `Never` |
| Load-container resources | requests `25m` CPU / `32Mi`; limits `500m` CPU / `128Mi` |
| Termination evidence | `/dev/termination-log`, policy `File` |
| Local record | `results/experiments/schema12-timeout-20261109.json` |

The high target rate does not create an unbounded queue: arrivals are skipped
while the four workers are occupied. The 15-second scheduling window and the
remaining-duration request timeout make this a bounded attempt to observe a
timeout at shutdown. They do not guarantee that cluster timing will produce
one; absence of a timeout is an explicit inconclusive result, not permission to
retry.

The approved build inputs are pinned below. A mismatch stops execution before
the build:

| Build input | SHA-256 |
| --- | --- |
| `deploy/workload/Dockerfile` | `e7ed3526f189f3d7b69875611c0cc86a37c31c0f25676679f4c4d705b34e73de` |
| `deploy/workload/__init__.py` | `a021711d906c25f982d36cd17e34dd80df07e8475ab17a6656b7d63aec1140c3` |
| `deploy/workload/app.py` | `47740b30f2cb48e369af5258420be59a53ba02bff03e3d1b22d6179f40b3be16` |
| `deploy/workload/load.py` | `33b1e5a49af40fad3d45b2723ce15051c6f11d7617450969ce2c290708e36776` |
| `deploy/workload/metrics.py` | `0ab8b3c9dd06bc55ff1ee50219716dc0a50ae8968bf1b46c15be29635f770707` |

## Mandatory read-only preflight

Repeat these checks immediately after approval and before any mutation:

- current context and namespace are exactly the fixed values above;
- the five build-input hashes and this plan hash match their approved values;
- the Deployment UID, generation, image, resources, desired/available/ready
  replicas, application Pod UIDs, readiness, and restart counts match the
  captured baseline;
- the Service still selects the two ready application Pods on port 8080;
- the node is Ready with no memory, disk, or PID pressure;
- no load-generator Job/Pod, fixed Job, or fixed local experiment record
  exists;
- the fresh image tag is absent from both local Docker and the kind node; and
- an offline render of the fixed Job has the exact image, command, environment,
  target `http://kri-workload:8080/work`, resources, pull policy, deadline, and
  termination-message settings in this plan.

Stop on any mismatch. This plan does not authorize drift repair, record
replacement, tag replacement, or cleanup of an unexpected pre-existing
resource.

## Exact approved execution sequence

After successful preflight, build and load only the pinned source under the
fresh tag:

```bash
make workload-image IMAGE=kri-workload:schema12-timeout-20261109
kind load docker-image kri-workload:schema12-timeout-20261109 \
  --name kube-optimizer
```

Capture the local Docker image ID and the kind node's immutable runtime image
ID for that tag. Stop before creating the Job unless the node inventory resolves
the fresh tag to exactly one image.

Create the sole experiment and Job with:

```bash
KRI_K8S_CONTEXT=kind-kube-optimizer \
KRI_K8S_NAMESPACE=payments \
KRI_WORKLOAD_IMAGE=kri-workload:schema12-timeout-20261109 \
  .venv/bin/kri-workload start-load \
  --cpu-request 90m --cpu-limit 140m \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 100 \
  --duration-seconds 15 \
  --experiment-id schema12-timeout-20261109
```

Wait only for this Job and for no longer than its 75-second active deadline.
Do not retry, replace, or modify it. The Job controller may create exactly one
owned Pod.

After the Job is terminal, capture its UID, condition, timestamps, events, Pod
ownership, Pod restart count, selected image, runtime image ID, complete stdout,
and terminated container state. Reconcile evidence with exactly one invocation:

```bash
KRI_K8S_CONTEXT=kind-kube-optimizer \
KRI_K8S_NAMESPACE=payments \
KRI_WORKLOAD_IMAGE=kri-workload:schema12-timeout-20261109 \
  .venv/bin/kri-workload status schema12-timeout-20261109
```

Retain a separate read-only capture of the termination message before cleanup.
Then delete only the fixed Job. The preferred command is `stop-load` after a
successful reconciliation:

```bash
KRI_K8S_CONTEXT=kind-kube-optimizer \
KRI_K8S_NAMESPACE=payments \
KRI_WORKLOAD_IMAGE=kri-workload:schema12-timeout-20261109 \
  .venv/bin/kri-workload stop-load schema12-timeout-20261109
```

If reconciliation itself rejects contradictory or missing evidence, use only
this fallback to perform the same approved cleanup:

```bash
kubectl --context kind-kube-optimizer --namespace payments \
  delete job kri-load-schema12-timeout-20261109
```

## Acceptance criteria

The verification passes only if all of the following hold:

- exactly one Job-owned Pod used the fresh cached tag with
  `imagePullPolicy: Never`, and its runtime image ID matches the post-load node
  inventory;
- the container terminated once with reason `Completed`, exit code 0, and no
  restart; the Job has `Complete=True` and no `Failed=True` condition;
- stdout's final JSON object and the Kubernetes termination message are the
  same schema-1.1 summary;
- the summary has `execution_status: completed`,
  `execution_failure_reason: null`, `exit_code: 0`,
  `request_timeouts >= 1`, and `stuck_workers: 0`;
- summary counts are internally consistent and preserve request failures and
  timeouts separately;
- the local artifact is schema 1.2 with lifecycle `succeeded`, the fixed Job
  UID and Kubernetes timestamps, and a `load_summary` exactly equal to the
  termination-message summary; and
- cleanup removes the fixed Job and owned Pod while the application identity,
  configuration, Pod UIDs, readiness, and restart counts remain unchanged.

Record the experiment-artifact SHA-256 and raw counts. Do not convert missing
or malformed evidence to zero. A completed Job with zero observed timeouts is
safe but **inconclusive** for the requested timeout assertion. A failed Job,
stuck worker, missing schema-1.2 artifact, evidence mismatch, application drift,
or wrong image is a failed verification. Every such outcome still requires the
approved cleanup and does not authorize another run.

## Exact mutations and residual state requiring approval

Approval authorizes only:

1. creation of the fresh local Docker image tag from the pinned build context;
2. loading that tag into the `kube-optimizer` kind node image cache;
3. creation of local experiment record
   `results/experiments/schema12-timeout-20261109.json`;
4. creation of namespaced Job
   `payments/kri-load-schema12-timeout-20261109` with the fixed specification;
5. creation by the Job controller of exactly one Pod owned by that Job; and
6. deletion of that Job after capture, allowing garbage collection of only its
   owned Pod.

The brief request stream consumes bounded application capacity and increments
application metrics but is not a Kubernetes-resource mutation. The retained
local experiment record and fresh Docker/node image tags are intentional
evidence/residual state and are not deleted under this plan.

No Deployment, ReplicaSet, application Pod, Service, ConfigMap, Secret,
namespace, monitoring resource, existing image tag, M14 Job, or M14 artifact
may be created, patched, restarted, scaled, deleted, overwritten, or otherwise
mutated. No application rollback is necessary because no application
configuration change is authorized.
