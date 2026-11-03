.PHONY: dev-api dev-check dev-web format frontend lint sync-knowledge test typecheck verify workload-image

IMAGE ?= kri-workload:local

format:
	python -m ruff format .

lint:
	python -m ruff check .
	python -m ruff format --check .

typecheck:
	python -m mypy

test:
	python -m pytest --cov=kri --cov-report=term-missing

frontend:
	npm --prefix web run typecheck
	npm --prefix web test
	npm --prefix web run build

dev-check:
	python scripts/check_local_services.py

sync-knowledge:
	python scripts/sync_knowledge.py

dev-api: dev-check
	kri-api

dev-web:
	npm --prefix web run dev

verify: lint typecheck test frontend

workload-image:
	docker build --tag "$(IMAGE)" deploy/workload
