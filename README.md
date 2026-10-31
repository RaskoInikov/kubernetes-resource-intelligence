# Kubernetes Resource Intelligence

Kubernetes Resource Intelligence is an evidence-grounded resource analysis
project. M1 provides a disposable application and an independently controlled
load generator; monitoring and analysis begin in later milestones.

## Requirements

- Python 3.12 or newer
- A virtual environment tool (`venv` is sufficient)

No Kubernetes cluster or external service is needed for M0 verification.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

`.env` is for local values and is not committed. Settings use the `KRI_`
prefix and fail validation when a required value is absent or malformed.

## Verification

Run the complete local verification suite:

```bash
make verify
```

The individual commands are:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest --cov=kri --cov-report=term-missing
```

These checks are offline. Future real-service checks must be reported
separately, as required by `AGENTS.md`.

## Repository layout

- `src/kri/` — Python contracts, configuration, and workload controller.
- `tests/` — offline Python tests.
- `deploy/workload/` — build context for the disposable target/load image.
- `knowledge/` — future canonical knowledge documents.
- `results/` — generated experiment artifacts (ignored except `.gitkeep`).
- `web/` — future frontend application.
- `docs/` — product, architecture, contracts, roadmap, and progress.

See `docs/ROADMAP.md` for milestone scope. Do not implement later milestones
as part of repository setup.

## M1 workload operations

All commands target `KRI_K8S_CONTEXT` and the pre-existing
`KRI_K8S_NAMESPACE`. The controller never creates a namespace. Build the test
image and make it available to the target cluster using the mechanism for that
cluster. For the example kind context:

```bash
make workload-image IMAGE=kri-workload:local
kind load docker-image kri-workload:local --name kube-optimizer
```

Building or loading an image changes local Docker or cluster-node state. Run
those commands only as an explicitly approved experiment operation.

Application deployment is separate from load generation:

```bash
kri-workload deploy \
  --cpu-request 100m --cpu-limit 500m \
  --memory-request 64Mi --memory-limit 256Mi \
  --replicas 2

kri-workload start-load \
  --cpu-request 100m --cpu-limit 500m \
  --memory-request 64Mi --memory-limit 256Mi \
  --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 10 \
  --duration-seconds 60 --experiment-id exp-example-1

kri-workload status exp-example-1
kri-workload stop-load exp-example-1
kri-workload delete
```

`stop-load` deletes only `job/kri-load-<experiment-id>`. It does not modify the
Deployment or Service. `delete` is the distinct application-removal operation.
Experiment records are written atomically beneath `results/experiments/` and
are ignored by Git.

These commands perform persistent Kubernetes mutations and therefore require
explicit approval before execution. M1's default `make verify` is fully offline
and uses fake command responses. Optional real-cluster verification must record
the context, namespace, image, commands, and observed results separately; mock
or dry-run results must not be reported as real integration success.
