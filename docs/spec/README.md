# Specs

Карта «что в каком файле» (без копипаста требований): [TZ_OVERVIEW.md](./TZ_OVERVIEW.md).

## Если в задаче сказано «по ТЗ» без ссылки на файл

1. **Объём работ и критерии готовности** — брать из [`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md) (теги [MVP] / v1.1+ и матрица [`docs/audit/TZ_COVERAGE_MATRIX.md`](../audit/TZ_COVERAGE_MATRIX.md), если ведёте учёт).
2. **Ограничения на доработку** (не ломать prod, feature flags, миграции, UX) — из разд. 36 [`PLATFORM_VNEXT_UPGRADE_SPEC.md`](./PLATFORM_VNEXT_UPGRADE_SPEC.md) либо сжато из `backend/app/core/product_spec.py`.
3. **Продуктовая рамка/дорожная карта** — [`PLATFORM_VNEXT_UPGRADE_SPEC.md`](./PLATFORM_VNEXT_UPGRADE_SPEC.md) целиком; не смешивать с пунктом 1, если в задаче не сказано «по vNext-спекy».

---

- [PLATFORM_VNEXT_UPGRADE_SPEC.md](./PLATFORM_VNEXT_UPGRADE_SPEC.md) — **продуктовый upgrade-spec vNext** (конкурентный паритет, издания, UX, модули, критерии приёмки, разд. 36 для AI/разработки). Каноничный путь в коде: `backend/app/core/product_spec.py` (`PLATFORM_VNEXT_UPGRADE_SPEC_PATH`).
- [TZ_FULL_UNIFIED.md](./TZ_FULL_UNIFIED.md) — **единое полное ТЗ** репозитория (артефакты, P0/P1, пометки MVP/v1.1/v1.2/v2.0).
- [PLATFORM_DESIGN.md](./PLATFORM_DESIGN.md) — целевая архитектура платформы.
- [TZ.md](./TZ.md) — историческая версия ТЗ.
- [mapping.md](./mapping.md) — карта соответствия требований и реализации.
