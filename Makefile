.PHONY: install run worker test check migrate seed lint typecheck fmt load-test backup

install:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	arq app.workers.main.WorkerSettings

test:
	pytest

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .
	ruff check --fix .

typecheck:
	mypy app

check: lint typecheck test

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

load-test:
	python -m scripts.load_test

backup:
	python -m scripts.backup

