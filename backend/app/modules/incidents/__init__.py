"""Операции контура происшествий и проверок.

**Срез-117: слой жизненного цикла ``IncidentCase`` удалён.** Здесь жили
``IncidentCaseService``, ``IncidentInvestigationService`` и
``RiskReviewTriggerService`` — чистые функции переходов статусов для таблицы
``incident_cases``, которую НЕ заполняет ни одна ручка. Потребителей в
продукте у них не было (только собственные юнит-тесты), а живой контур
происшествий работает на ядровой модели ``Incident``: регистрация, журнал,
расследование и связь с CAPA идут через ``operations.py`` и ручки
``/incidents``. Держать рядом второй, недостижимый жизненный цикл — два места
правды, одно из которых никогда не выполняется (тот же разбор, что у сканера
напоминаний в срезе-113).

**Срез-135: модели ``IncidentCase`` / ``IncidentInvestigation`` (и соседние по
контуру) удалены из кода — их не читал и не писал никто.** Таблицы в базе
ОСТАЛИСЬ: данные арендаторов не удаляют ради чистоты кода, а без модели они
всё равно никому не видны. Список таблиц под снос — в
``docs/CLEANUP_CANDIDATES.md``; решение о сносе за владельцем. Если контур
понадобится — возвращать его надо вместе с ручками и моделями.
"""

from .operations import (
    add_inspection_result,
    append_log_entry,
    register_incident,
    register_inspection,
    update_incident,
    update_inspection,
)

__all__ = [
    "register_incident",
    "update_incident",
    "append_log_entry",
    "register_inspection",
    "update_inspection",
    "add_inspection_result",
]
