.PHONY: install lint format test contract run build clean up down migrate

LINT_PATHS=app tests scripts

install:
	poetry install --with dev --no-interaction

lint:
	poetry run ruff check --no-fix $(LINT_PATHS)
	poetry run black --check $(LINT_PATHS)

format:
	poetry run ruff check --fix $(LINT_PATHS)
	poetry run black $(LINT_PATHS)

test:
	poetry run pytest

contract:
	poetry run pytest -m contract

run:
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000

migrate:
	poetry run alembic -c app/migrations/alembic.ini upgrade head

build:
	poetry build

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
	find . -type d -name '__pycache__' -exec rm -rf {} +

up:
	docker compose up -d --build

down:
	docker compose down -v
