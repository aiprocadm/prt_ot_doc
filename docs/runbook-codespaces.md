# Runbook: GitHub Codespaces (dockerless-first)

## Quick start
```bash
cp .env.example .env
pip install -r requirements-dev.txt
cd frontend && npm ci && cd ..
make dev:lite
```

## Health checks
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

## Tests
```bash
pytest --collect-only -q
make test:lite
cd frontend && npm run test -- --run src/__tests__/apiClient.test.ts src/__tests__/TenantGate.test.tsx src/__tests__/DocumentsPage.test.tsx src/__tests__/TasksPage.test.tsx
```

## VS Code Testing panel
- Python tests are auto-discovered via `.vscode/settings.json` + `vscode_pytest.py`.
- Frontend tests run with `vitest` from `frontend` workspace.

## If Docker is available
```bash
make dev
make test
```

## Notes
- Dockerless mode uses local storage and local process topology prepared by scripts in `scripts/`.
- Tenant header (`X-Tenant`) is mandatory for business `/api/v1/*` routes.
