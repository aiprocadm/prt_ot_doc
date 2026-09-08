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

Модели ``IncidentCase`` / ``IncidentInvestigation`` и их таблицы НЕ удалялись:
у них миграции и политики RLS, а данные арендаторов не удаляют ради чистоты
кода. Если контур понадобится — возвращать его надо вместе с ручками.
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
