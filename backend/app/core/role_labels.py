"""Русские названия ролей арендатора — единый словарь для витрин (срез-147).

До среза роль в интерфейсе показывалась кодом (``ot_specialist``), а там, где
её выбирают, каждый экран заводил свой список из трёх-пяти ролей с
собственными подписями. Требование реестра (B.18 разд. 19.2) «относится к
роли» — значит, роль надо ВЫБРАТЬ, а не впечатать латиницей; выбирать можно
только из закрытого перечня ``RoleEnum`` и только с человеческой подписью.

Подписи — из ``docs/DOMAIN_MODEL.md`` (таблица «Роли (RoleEnum)»): словарь
повторяет документ, а не придумывает названия. Полнота стережётся тестом
``backend/tests/test_role_labels.py``: новая роль без подписи — красный
прогон, а не код в выпадающем списке.
"""

from __future__ import annotations

from app.models.models import RoleEnum

#: Человеческое название каждой роли ``RoleEnum`` (docs/DOMAIN_MODEL.md).
ROLE_LABELS: dict[str, str] = {
    RoleEnum.OWNER.value: "Владелец арендатора",
    RoleEnum.ADMIN.value: "Администратор",
    RoleEnum.OT_PB_LEAD.value: "Руководитель ОТиПБ",
    RoleEnum.OT_HEAD.value: "Начальник отдела ОТ",
    RoleEnum.OT_SPECIALIST.value: "Специалист ОТ",
    RoleEnum.PB_ENGINEER.value: "Инженер ПБ",
    RoleEnum.ECOLOGIST.value: "Эколог",
    RoleEnum.HR.value: "HR",
    RoleEnum.LAWYER.value: "Юрист",
    RoleEnum.ACCOUNTANT.value: "Бухгалтер",
    RoleEnum.LINE_MANAGER.value: "Линейный руководитель",
    RoleEnum.MANAGER.value: "Менеджер",
    RoleEnum.EXECUTOR.value: "Исполнитель",
    RoleEnum.WORKER.value: "Рабочий / сотрудник",
    RoleEnum.EMPLOYEE.value: "Сотрудник",
    RoleEnum.CLERK.value: "Делопроизводитель",
    RoleEnum.TEACHER.value: "Преподаватель",
    RoleEnum.STUDENT.value: "Обучающийся",
    RoleEnum.CONTRACTOR_INSPECTOR.value: "Проверяющий-подрядчик",
    RoleEnum.INSPECTOR_CONTRACTOR.value: "Проверяющий-подрядчик",
    RoleEnum.AUDITOR_RO.value: "Аудитор (только чтение)",
    RoleEnum.CLIENT_ADMIN.value: "Администратор клиентского портала",
    RoleEnum.CLIENT_USER.value: "Пользователь клиентского портала",
    RoleEnum.CLIENT.value: "Внешний клиент",
}

#: Псевдонимы (docs/DOMAIN_MODEL.md): ``employee`` — синоним ``worker``,
#: ``inspector_contractor`` — синоним ``contractor_inspector``. Как значение
#: они законны, но в справочнике для выбора показывать две одинаковые роли
#: нельзя — человек не поймёт, чем они различаются.
ROLE_ALIASES: dict[str, str] = {
    RoleEnum.EMPLOYEE.value: RoleEnum.WORKER.value,
    RoleEnum.INSPECTOR_CONTRACTOR.value: RoleEnum.CONTRACTOR_INSPECTOR.value,
}

#: Все коды ролей, которые принимает запись «требование относится к роли».
ROLE_CODES: frozenset[str] = frozenset(role.value for role in RoleEnum)


def role_label(code: str | None) -> str | None:
    """Подпись роли; неизвестный код возвращается как есть (не молча пусто)."""
    if not code:
        return None
    return ROLE_LABELS.get(code, code)


def role_options() -> list[dict[str, str]]:
    """Роли для выбора на витрине: без псевдонимов, в порядке ``RoleEnum``."""
    return [
        {"code": role.value, "label": ROLE_LABELS[role.value]}
        for role in RoleEnum
        if role.value not in ROLE_ALIASES
    ]
