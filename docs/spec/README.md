# Specs

**Канонический и единственный источник истины для фразы «продолжай по ТЗ»: [`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md).**

Карта «что в каком файле» (без копипаста требований): [`TZ_OVERVIEW.md`](./TZ_OVERVIEW.md).

## Если в задаче сказано «по ТЗ» / «продолжай по ТЗ» без ссылки

1. Прочитайте **`TZ_FULL_UNIFIED.md`**, разделы:
   - `0` — как читать и работать «по ТЗ»;
   - `A` — объём и приёмка MVP (теги `[MVP]`, `P0/P1`);
   - `B` — полный объём (vNext, теги `[v1.1] / [v1.2] / [v2.0]`);
   - `C` — где смотреть текущий статус;
   - `D` — фазы реализации;
   - `E` — обязательные правила доработки (разд. 36 vNext: feature flags, additive миграции, tenant isolation, six questions).
2. Проверьте текущий handoff в `../../AI_IMPLEMENTATION_REPORT.md` (последний блок «Last Agent Handoff» / `Next Steps`).
3. Сверьте MVP-статус по `../audit/TZ_COVERAGE_MATRIX.md`; сверьте фазу — по `../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`.
4. Полный текст vNext (разделы 0–37) — `PLATFORM_VNEXT_UPGRADE_SPEC.md`. Используется как исчерпывающий каталог требований полного объёма; в ежедневной работе не открывается целиком — заходите по ссылкам из раздела B `TZ_FULL_UNIFIED.md`.

При сомнении уточняйте у пользователя, к какому файлу привязать приёмку, вместо того чтобы расширять scope из vNext-спека.

## Файлы

| Документ | Назначение |
|----------|------------|
| [`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md) | **Канон.** Единое полное ТЗ: MVP-объём (раздел A) + полный объём vNext (раздел B) + правила доработки + карта канонических документов |
| [`TZ_OVERVIEW.md`](./TZ_OVERVIEW.md) | Карта «что в каком файле» (без дублирования требований) |
| [`PLATFORM_VNEXT_UPGRADE_SPEC.md`](./PLATFORM_VNEXT_UPGRADE_SPEC.md) | Продуктовая рамка vNext (разделы 0–37): конкурентный паритет, упаковка, модули, mobile, sellability. Канонический путь в коде: `backend/app/core/product_spec.py` |
| [`PLATFORM_DESIGN.md`](./PLATFORM_DESIGN.md) | Целевая архитектура платформы |
| [`TZ.md`](./TZ.md) | Историческая первая версия ТЗ (справочно). Не использовать для приёмки |
| [`mapping.md`](./mapping.md) | Карта соответствия разделов спецификации и кода/тестов |

## Связанные документы вне `docs/spec/`

- `../audit/TZ_COVERAGE_MATRIX.md` — машинно-проверяемая матрица покрытия требований MVP (`done` / `partial` / `missing`).
- `../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — фазированный план реализации (Phase 0..10).
- `../../AI_IMPLEMENTATION_REPORT.md` — журнал волн / handoff между агентами / следующий точный шаг.
- `../../RELEASE_READINESS.md` — релиз-вердикт; canonical: `../stabilization/RELEASE_BLOCKERS_STATUS.md`.
- `../../KNOWN_LIMITATIONS.md` — ограничения, перенесённые на следующие итерации.
- `../AI_AGENT_WORKFLOW.md` — компактный рабочий цикл для AI/агентов.

## Запрет на дубли

См. раздел G в [`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md#g-карта-канонических-документов-и-запрет-на-дубли):

- Любые новые требования — только в `TZ_FULL_UNIFIED.md`.
- Любая дорожная карта — только в `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`.
- Любой статус MVP — только в `TZ_COVERAGE_MATRIX.md`.
- Любой релиз-вердикт — только в `RELEASE_READINESS.md` + `RELEASE_BLOCKERS_STATUS.md`.
