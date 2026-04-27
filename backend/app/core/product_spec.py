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
