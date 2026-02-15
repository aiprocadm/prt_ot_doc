.PHONY: install install-pip install-poetry lint format test contract run build clean up down migrate dev env frontend-install lint-frontend format-frontend test-frontend dev-lite test-lite dev-nodocker test-nodocker check-docker

LINT_PATHS=backend/app tests scripts

check-docker:
	@./scripts/check_docker.sh

env:
	@test -f .env || cp .env.example .env

install: install-pip

install-pip:
	python -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r requirements.txt -r requirements-dev.txt

install-poetry:
	poetry install --with dev --no-interaction

lint:
	poetry run ruff check --no-fix $(LINT_PATHS)
	poetry run black --check $(LINT_PATHS)
	$(MAKE) lint-frontend

format:
	poetry run ruff check --fix $(LINT_PATHS)
	poetry run black $(LINT_PATHS)
	$(MAKE) format-frontend

test:
	poetry run pytest
	$(MAKE) test-frontend

test-lite:
	@./scripts/test_lite.sh

test-nodocker: test-lite

test\:lite: test-lite

frontend-install:
	cd frontend && npm ci

lint-frontend: frontend-install
	cd frontend && npm run lint

format-frontend: frontend-install
	cd frontend && npm run format:write

test-frontend: frontend-install
	cd frontend && npm run test

contract:
	poetry run pytest -m contract

run:
	PYTHONPATH=backend poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000

migrate:
	PYTHONPATH=backend poetry run alembic -c backend/app/migrations/alembic.ini upgrade heads

build:
	poetry build

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
	find . -type d -name '__pycache__' -exec rm -rf {} +

up: env check-docker
	docker compose up -d --build

dev: env check-docker
	docker compose up --build

dev-lite:
	@./scripts/dev_lite.sh

dev-nodocker: dev-lite

dev\:lite: dev-lite

down:
	docker compose down -v
