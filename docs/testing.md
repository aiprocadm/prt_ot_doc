# Тестирование (канонический гайд)

Короткие пути в репозитории; детализация по слоям — в `docs/TEST_BASELINE.md`, `docs/CI_PIPELINE_OVERVIEW.md`, `docs/stabilization/`.

## Локальная проверка (как в README)

**Backend (из корня репозитория):**

```bash
# Windows PowerShell
$env:PYTHONPATH = "backend"
.venv/Scripts/python.exe -m pytest -q

# Unix
export PYTHONPATH=backend
python -m pytest -q
```

**Точечно (KPI P0 / tenant / idempotency / шаблоны):**

```bash
pytest -q tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py
```

**Frontend:** `npm --prefix frontend run ci` (или по отдельности `typecheck`, `test`, `build` — см. `frontend/package.json`).

## Среда pytest

`tests/conftest.py` задаёт тестовые `DATABASE_URL` (sqlite), Redis memory, плейсхолды для S3; при пустом `SECRET_KEY` в окружении выставляется безопасное тестовое значение, чтобы `bootstrap("api")` не падал.

## CI

Сводка: `docs/CI_PIPELINE_OVERVIEW.md` (файл `.github/workflows/ci.yml` — backend pytest, фронт `npm run ci`, compose smoke).

## Матрицы и приёмка

- Критерии must-pass: `docs/TEST_BASELINE.md`
- E2E политика: `docs/stabilization/e2e-access.md`
- Соответствие ТЗ (сводно): `docs/audit/TZ_COMPLIANCE.md`, `docs/audit/TZ_COVERAGE_MATRIX.md`
