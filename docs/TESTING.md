# Legacy testing doc pointer

This file is kept only for backward-compatible links.

Use the canonical testing guide instead:

- `docs/TESTING.md`
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

## Полный pytest (зафиксированный прогон)

Актуальные цифры, разбивка по каталогам и группы падений: **`docs/audit/BASELINE_VERIFICATION.md`** — секция *Full pytest (все `testpaths`) — 2026-05-02*.

Кратко (Windows, Python 3.13.7, агрегат трёх прогонов = полный `testpaths`): **1147** собрано, **1086** passed, **52** failed, **7** skipped, **2** errors.

## Среда pytest

`tests/conftest.py` задаёт тестовые `DATABASE_URL` (sqlite), Redis memory, плейсхолды для S3; при пустом `SECRET_KEY` в окружении выставляется безопасное тестовое значение, чтобы `bootstrap("api")` не падал.

## CI

Сводка: `docs/CI_PIPELINE_OVERVIEW.md` (файл `.github/workflows/ci.yml` — backend pytest, фронт `npm run ci`, compose smoke).

## Матрицы и приёмка

- Критерии must-pass: `docs/TEST_BASELINE.md`
- E2E политика: `docs/stabilization/e2e-access.md`
- Соответствие ТЗ (сводно): `docs/audit/TZ_COMPLIANCE.md`, `docs/audit/TZ_COVERAGE_MATRIX.md`

