# Карта спецификаций (одним взглядом)

**Канон:** [`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md) — точка входа для фразы «продолжай по ТЗ» (см. раздел 0 этого файла).

```mermaid
flowchart TB
  subgraph canon["Канон ТЗ (точка входа)"]
    TZF["docs/spec/TZ_FULL_UNIFIED.md<br/>(A. MVP, B. полный объём,<br/>C. статус, D. фазы, E. правила)"]
  end
  subgraph status["Статус и приёмка"]
    MAT["docs/audit/TZ_COVERAGE_MATRIX.md<br/>(REQ-ID → status)"]
    REP["AI_IMPLEMENTATION_REPORT.md<br/>(handoff волн)"]
    REL["RELEASE_READINESS.md +<br/>docs/stabilization/RELEASE_BLOCKERS_STATUS.md"]
  end
  subgraph product["Продуктовая рамка vNext"]
    VN["docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md<br/>(разд. 0–37, паритет, упаковка)"]
    PS["backend/app/core/product_spec.py<br/>(разд. 36: правила доработки)"]
    PLAN["docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md<br/>(Phase 0..10)"]
  end
  subgraph arch["Архитектура и история"]
    PD["docs/spec/PLATFORM_DESIGN.md"]
    TZH["docs/spec/TZ.md (history)"]
    MAP["docs/spec/mapping.md"]
  end
  TZF --> MAT
  TZF --> REP
  TZF --> REL
  TZF -->|"раздел B → подробности"| VN
  TZF -->|"раздел D → подробности"| PLAN
  VN -->|"разд. 36 ≈ tuples"| PS
```

## Файл → назначение

| Документ | Назначение |
|----------|------------|
| [`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md) | **Канон.** Точка входа «продолжай по ТЗ»: MVP-объём (`A`), полный объём (`B`), статус (`C`), фазы (`D`), правила доработки (`E`), карта канонических документов (`G`) |
| [`PLATFORM_VNEXT_UPGRADE_SPEC.md`](./PLATFORM_VNEXT_UPGRADE_SPEC.md) | Полный продуктовый upgrade-spec vNext (разд. 0–37). Подробности к разделу B канона. Разд. 36 — обязательные ограничения для доработки |
| [`PLATFORM_DESIGN.md`](./PLATFORM_DESIGN.md) | Целевая архитектура платформы (modular monolith, bounded contexts) |
| [`TZ.md`](./TZ.md) | Историческое исходное ТЗ (справочно, для приёмки не использовать) |
| [`mapping.md`](./mapping.md) | Соответствие разделов и кода |
| [`../audit/TZ_COVERAGE_MATRIX.md`](../audit/TZ_COVERAGE_MATRIX.md) | Статус покрытия MVP-требований (`done` / `partial` / `missing`) |
| [`../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`](../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md) | Фазированный план реализации |
| [`../../AI_IMPLEMENTATION_REPORT.md`](../../AI_IMPLEMENTATION_REPORT.md) | Журнал волн / handoff / «Следующий точный шаг» |

**Порядок по умолчанию для агента:** `TZ_FULL_UNIFIED.md` → `AI_IMPLEMENTATION_REPORT.md` → `TZ_COVERAGE_MATRIX.md` → при необходимости подробностей конкретного блока — `PLATFORM_VNEXT_UPGRADE_SPEC.md`. Подробно — раздел `0` в `TZ_FULL_UNIFIED.md` и [`README.md`](./README.md) этого каталога.
