.PHONY: format lint test typecheck verify workload-image

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

verify: lint typecheck test

workload-image:
	docker build --tag "$(IMAGE)" deploy/workload
