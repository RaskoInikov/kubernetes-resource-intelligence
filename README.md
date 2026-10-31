# Kubernetes Resource Intelligence

Kubernetes Resource Intelligence is an evidence-grounded resource analysis
project. The current repository state contains only the M0 development
foundation; application behavior begins in M1.

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

- `src/kri/` — Python package; currently configuration only.
- `tests/` — offline Python tests.
- `deploy/` — future disposable Kubernetes resources.
- `knowledge/` — future canonical knowledge documents.
- `results/` — generated experiment artifacts (ignored except `.gitkeep`).
- `web/` — future frontend application.
- `docs/` — product, architecture, contracts, roadmap, and progress.

See `docs/ROADMAP.md` for milestone scope. Do not implement later milestones
as part of repository setup.
