.PHONY: install run worker test check migrate seed lint typecheck fmt

install:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	python -m app.workers.main

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

