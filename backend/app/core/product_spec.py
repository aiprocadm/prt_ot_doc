"""Канонические пути к продуктовой спецификации vNext и сжатые правила из разд. 36 ТЗ.

Полный текст: ``docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`` (source of truth для upgrade-spec).
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "PLATFORM_VNEXT_UPGRADE_SPEC_PATH",
    "ARCHITECTURE_RULES",
    "ENGINEERING_RULES",
    "PRODUCT_UX_RULES",
    "SIX_QUESTIONS",
    # Бизнес-расширение (Дополнения №1–№2, разд. 49–62)
    "BIZ_DOMAINS",
    "UX_BUDGET",
    "ACCESS_CHECK_ORDER",
    # Сквозная безопасность (Дополнение №3, разд. 63–70)
    "SECURITY_DOMAINS",
    "SECURITY_QUESTION",
    # Данные, ЖЦ клиента, API, эксплуатация (Дополнение №4, разд. 71–74)
    "LIFECYCLE_DOMAINS",
    "API_BREAKING_CHANGES",
    "MIGRATION_RULE",
]

# backend/app/core -> backend (parents[1]=app, parents[2]=backend)
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

PLATFORM_VNEXT_UPGRADE_SPEC_PATH = _REPO_ROOT / "docs" / "spec" / "PLATFORM_VNEXT_UPGRADE_SPEC.md"
SPEC_INDEX_README_PATH = _REPO_ROOT / "docs" / "spec" / "README.md"

# Разд. 36.1 — архитектурные ограничения для доработок
ARCHITECTURE_RULES: tuple[str, ...] = (
    "Не ломать существующие рабочие модули.",
    "Не удалять действующие API без слоя совместимости.",
    "Все новые функции — через feature flags.",
    "Additive DB migrations; сохранять tenant isolation.",
    "Не смешивать bounded contexts напрямую; тяжёлые операции — в async workers.",
)
# Enforcement (ARCH-3): правило «не смешивать bounded contexts напрямую» проверяется
# AST-чекером ``scripts/ci/check_context_boundaries.py`` — запускается через
# ``make check-boundaries`` или внутри ``make gate`` (scripts/ci/local_gate.py).
# Новый cross-context импорт (app.modules.* <-> app.domains.*) валит проверку;
# текущие протечки — временный allowlist, вычищаемый ARCH-1 (domains/ → modules/).

# Разд. 36.2
ENGINEERING_RULES: tuple[str, ...] = (
    "Unit/integration/e2e; OpenAPI; changelog; seed/demo; correlation-id; строгая типизация.",
)

# Разд. 36.3
PRODUCT_UX_RULES: tuple[str, ...] = (
    "Новый экран — с primary user goal; новая сущность — с master data.",
    "Не плодить workflow, если хватает rules/presets/tasks.",
    "Массовые операции — preview и прогресс; mobile/field — с учётом offline.",
)

# Разд. 36.4 — шесть обязательных вопросов к новой функции
SIX_QUESTIONS: tuple[str, ...] = (
    "Для какой роли она нужна?",
    "В каком сценарии она используется?",
    "Какие данные ей нужны и откуда они берутся?",
    "Как ведёт себя при отсутствии сети/ошибке интеграции?",
    "Как пользователь понимает, что произошло и что делать дальше?",
    "Как отключается/включается по tenant без глобального refactor?",
)

# ---------------------------------------------------------------------------
# Бизнес-расширение (Дополнения №1–№2 к ТЗ, разд. 49–62). Тег [vNext-BIZ].
# Карта требований — в TZ_FULL_UNIFIED.md (раздел B-NEXT); реализация — фазами
# 11–15 в PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md. Здесь — программные константы.
# ---------------------------------------------------------------------------
BIZ_DOMAINS: tuple[str, ...] = (
    "managed_clients",  # разд. 49–51: ведение клиентов аутсорсером
    "reseller_hierarchy",  # разд. 52: продажа платформы аутсорсерам
    "tenant_leasing",  # разд. 53: аренда заказчикам
    "multidiscipline",  # разд. 54–57: ПБ/ПромБез/Эко/ГО-ЧС/БДД
    "ux_budget",  # разд. 59–60: простой UX, лимиты экрана
    "module_entitlements",  # разд. 61: модульная поставка (default-OFF)
)

# Разд. 59.2 — числовой UX-бюджет экрана (проверяемо в UI-ревью)
UX_BUDGET: dict[str, int] = {
    "max_primary_cta": 2,
    "max_visible_form_fields": 7,
    "max_default_table_columns": 7,
    "max_dashboard_blocks": 6,
    "max_nav_depth": 3,
}

# Разд. 61.3 — порядок enforcement доступа (модуль проверяется раньше роли)
ACCESS_CHECK_ORDER: tuple[str, ...] = (
    "tenant_context",  # 1) есть tenant-контекст
    "module_entitlement",  # 2) включён ли модуль у заказчика
    "rbac_role",  # 3) есть ли право у роли
    "abac_object",  # 4) доступен ли конкретный объект
)

# ---------------------------------------------------------------------------
# Сквозная безопасность (Дополнение №3 к ТЗ, разд. 63–70). Тег [vNext-SEC].
# Карта — B-NEXT.7; реализация — Phase 16 (приоритет ВЫШЕ бизнес-фаз).
# ---------------------------------------------------------------------------
SECURITY_DOMAINS: tuple[str, ...] = (
    "threat_model_hierarchy",  # 63: reseller/client изоляция
    "impersonation_control",  # 63.2: работа от имени клиента
    "appsec_owasp",  # 64: OWASP + парсинг документов (XXE-fix)
    "ssrf_protection",  # 64.3: вебхуки/интеграции
    "rls_isolation",  # 65: RLS как второй рубеж
    "pdn_152fz",  # 66: ПДн/152-ФЗ
    "secrets_management",  # 67: единая политика секретов
    "external_perimeter",  # 68: внешний контур
    "security_ci_gate",  # 69: SAST/DAST/пентест
)

# Разд. 69.2 — седьмой вопрос к новой фиче (расширение SIX_QUESTIONS)
SECURITY_QUESTION = "Какие новые поверхности атаки вводит фича и как они закрыты?"

# ---------------------------------------------------------------------------
# Данные, ЖЦ клиента, API, эксплуатация (Дополнение №4 к ТЗ, разд. 71–74).
# Тег [vNext-OPS]. Карта — B-NEXT.8; реализация — фазы 17–20.
# ---------------------------------------------------------------------------
LIFECYCLE_DOMAINS: tuple[str, ...] = (
    "data_import",  # 71: импорт-фреймворк
    "client_offboarding",  # 72: экспорт/удаление данных клиента
    "api_versioning",  # 73: версии + deprecation
    "zero_downtime_ops",  # 74: деплой без простоя
)

# Разд. 73.1 — что считается ломающим изменением API (для contract-тестов)
API_BREAKING_CHANGES: tuple[str, ...] = (
    "remove_field",
    "rename_field",
    "change_type",
    "change_semantics",
    "tighten_validation",
)

# Разд. 74.2 — правило миграций на живой системе
MIGRATION_RULE = (
    "expand-contract: additive сначала, удаление старого — отдельным "
    "шагом после раската; совместимость старого и нового кода."
)
