.PHONY: install install-pip lint format test contract run clean up down migrate tenant-migrate tenant-init seed smoke logs dev env frontend-install lint-frontend format-frontend test-frontend dev-lite test-lite dev-nodocker test-nodocker check-docker demo cs\:dev cs\:test cs\:reset final-acceptance tenant-bootstrap tenant-demo-bootstrap pilot-smoke pilot-readiness codex-audit

LINT_PATHS=backend/app tests scripts
VENV_BIN=.venv/bin
PYTHON=$(VENV_BIN)/python
PYTEST=$(VENV_BIN)/pytest
RUFF=$(VENV_BIN)/ruff
BLACK=$(VENV_BIN)/black
UVICORN=$(VENV_BIN)/uvicorn
ALEMBIC=$(VENV_BIN)/alembic

check-docker:
	@./scripts/check_docker.sh

env:
	@test -f .env || cp .env.example .env

install: install-pip

install-pip:
	python -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(RUFF) check --no-fix $(LINT_PATHS)
	$(BLACK) --check $(LINT_PATHS)
	$(MAKE) lint-frontend

format:
	$(RUFF) check --fix $(LINT_PATHS)
	$(BLACK) $(LINT_PATHS)
	$(MAKE) format-frontend

test:
	$(PYTEST)
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
	$(PYTEST) -m contract

run:
	PYTHONPATH=backend $(UVICORN) app.main:app --host 0.0.0.0 --port 8000

migrate:
	PYTHONPATH=backend $(ALEMBIC) -c backend/app/migrations/alembic.ini upgrade heads

seed:
	PYTHONPATH=backend $(PYTHON) scripts/create_tenant.py demo "Demo Tenant" demo@example.local || true
	PYTHONPATH=backend $(PYTHON) scripts/migrate_tenant.py demo || true

smoke:
	./scripts/smoke.sh

logs:
	docker compose logs -f --tail=200

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

cs\:dev: dev-lite

cs\:test: test-lite

cs\:reset:
	rm -f dev.db
	rm -rf .local_storage
	rm -rf frontend/coverage
	@echo "Codespaces local state reset complete (dev.db, .local_storage, frontend/coverage)."

down:
	docker compose down -v


demo:
	@echo "Demo bootstrap is enabled via .env (DEMO_BOOTSTRAP=1). Start app with make cs:dev."


tenant-migrate:
	@test -n "$(TENANT)" || (echo "TENANT is required" && exit 1)
	PYTHONPATH=backend $(PYTHON) scripts/migrate_tenant.py $(TENANT)

tenant-init: tenant-migrate


final-acceptance:
	@./scripts/final_acceptance.sh


tenant-bootstrap:
	@test -n "$(TENANT)" || (echo "TENANT is required" && exit 1)
	@test -n "$(TENANT_NAME)" || (echo "TENANT_NAME is required" && exit 1)
	@test -n "$(OWNER_EMAIL)" || (echo "OWNER_EMAIL is required" && exit 1)
	PYTHONPATH=backend $(PYTHON) scripts/bootstrap_tenant.py --tenant $(TENANT) --name "$(TENANT_NAME)" --owner-email $(OWNER_EMAIL)

tenant-demo-bootstrap:
	PYTHONPATH=backend $(PYTHON) scripts/bootstrap_demo_tenant.py --force

pilot-smoke:
	$(PYTEST) tests/e2e/pilot_smoke -q

pilot-readiness:
	PYTHONPATH=backend $(PYTHON) scripts/pilot_readiness.py


codex-audit:
	@./scripts/codex_audit.sh


# CI recovery baseline targets
test-backend:
	$(PYTEST)

test-smoke:
	./scripts/smoke.sh

ci-local:
	$(MAKE) lint
	$(MAKE) test-backend
	$(MAKE) test-frontend
	$(MAKE) test-smoke
