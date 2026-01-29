.PHONY: install lint format test contract run build clean up down migrate dev env

LINT_PATHS=backend/app tests scripts

env:
	@test -f .env || cp .env.example .env

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
	PYTHONPATH=backend poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000

migrate:
	PYTHONPATH=backend poetry run alembic -c backend/app/migrations/alembic.ini upgrade head

build:
	poetry build

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
	find . -type d -name '__pycache__' -exec rm -rf {} +

up: env
	docker compose up -d --build

dev: env
	docker compose up --build

down:
	docker compose down -v
