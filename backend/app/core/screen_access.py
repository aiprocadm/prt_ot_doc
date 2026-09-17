"""Одна карта прав экрана: КАКОЙ РОЛИ виден пункт меню и КОГО пускает его ручка.

ЧТО БЫЛО (docs/audit/ACCESS_MENU_VS_API.md, замер 13.09 и повторный замер
17.09). Прав у платформы было ТРИ словаря, и ни один не знал о двух других:

1. каждая ручка держала СВОЙ список ролей (926 ручек с ролями, из них 226 —
   «только admin»);
2. витрина держала СВОЮ карту «роль → права» и по ней рисовала меню;
3. серверный словарь ``core/rbac_abac.ROLE_PERMISSIONS`` вёл роли под
   именами, которых в продукте НЕТ (``hse_specialist``, ``fire_engineer``,
   ``instructor``), поэтому для настоящих ролей ``/auth/me`` отдавал ПУСТОЙ
   список — и витрина молча падала на свою карту.

Итог измерялся: 44 пункта меню из 67 сопоставленных были видны роли, которой
ручка отвечает 403. Самое больное — первый экран: ВСЕ роли приземляются на
``/dashboard``, а сводку пускали пять; специалист по охране труда — основной
пользователь продукта — получал отказ сразу после входа. И руководитель службы
ОТиПБ видел ВСЁ меню (право скопом), а ручки пускали его реже, чем его же
специалиста: 74 ручки пускали специалиста и не пускали руководителя.

РЕШЕНИЕ. Список ролей у права живёт ОДИН РАЗ — здесь. Из него берут роли ручки
(``screen_roles("ppe.view")`` вместо ``["admin"]``), из него ``/auth/me``
отдаёт витрине права, по которым она рисует меню. Тогда «пункт виден ⇔ ручка
пускает» выполняется ПО ПОСТРОЕНИЮ, а сторож ``tests/test_menu_matches_api.py``
ловит ручки, ещё не переведённые на карту. Это тот же приём, что у контуров
дисциплин (срез-119, ``core/disciplines.discipline_write_roles``): пять копий
одного списка держатся вместе ровно до первой правки.

РЕШЕНИЯ О СОДЕРЖАНИИ (переданы владельцем; принцип — меню витрины выражало
замысел продукта «кто что делает», а ручки отстали):

* **Начальник не может иметь меньше прав, чем его специалист.** Руководитель
  службы ОТиПБ и начальник отдела ОТ получают всё, что есть у специалиста ОТ,
  инженера ПБ и эколога. Но они НЕ администраторы платформы: настройки
  безопасности, ключи, интеграции, правила автоматизации, очередь исходящих —
  только владелец и администратор. До этого руководитель видел эти пункты
  (право скопом) и получал отказ на каждом.
* **Обзорные экраны — всем внутренним ролям.** Все приземляются на главную, и
  сводка на ней — счётчики, а не персональные данные. Прятать её — значит
  встречать человека отказом.
* **Согласования, подписи и ЭДО — тем же, кто читает документы.** Это экраны
  документооборота, а не отдельный контур.
* **Синонимы ролей закрываются здесь, а не в каждой ручке.** ``employee`` —
  это ``worker``; ``inspector_contractor`` — ``contractor_inspector``; роли,
  которых на витрине не было вовсе (``clerk``, ``teacher``, ``manager``,
  ``ot_head``, ``client_admin``, ``client_user``), получают права по смыслу —
  раньше они получали ПУСТОЕ меню.

ГРАНИЦЫ НАЗВАНЫ. Здесь только ЧТЕНИЕ и видимость. Права на запись ручек не
расширялись, кроме тех, у кого на экране уже есть отдельное право
(``*.manage``, ``*.create``, ``*.issue``). Контуры дисциплин остаются на
``discipline_write_roles`` — у них свой сторож. Серверный словарь
``rbac_abac.ROLE_PERMISSIONS`` не тронут: им живёт синхронизация PWA со своим
словарём кодов; его правка — отдельная работа.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.models.tenant_billing import RoleEnum

__all__ = [
    "ROLE_SYNONYMS",
    "SCREEN_ACCESS",
    "all_screen_permissions",
    "permissions_for_roles",
    "screen_roles",
]

#: Роли, которые всегда получают всё. Владелец — не «админ» по имени, но
#: ручки перечисляют обе, и владелец при заведении получает и роль admin.
_FULL_ACCESS: tuple[str, ...] = ("owner", "admin")

#: Синонимы: право, выданное левой роли, действует и для правой.
#: ``employee`` = ``worker`` и ``inspector_contractor`` = ``contractor_inspector``
#: записаны так же в ``core/role_labels.ROLE_ALIASES``.
ROLE_SYNONYMS: dict[str, str] = {
    "worker": "employee",
    "contractor_inspector": "inspector_contractor",
}

#: Руководители ОТ: всё, что есть у специалистов, плюс своё.
_OT_LEADS: tuple[str, ...] = ("ot_pb_lead", "ot_head")
#: Профильные специалисты охраны труда и смежных дисциплин.
_OT_PROS: tuple[str, ...] = (*_OT_LEADS, "ot_specialist", "pb_engineer", "ecologist")
#: Роли, для которых платформа — рабочее место (не внешние и не портал).
_INTERNAL: tuple[str, ...] = (
    *_OT_PROS,
    "hr",
    "line_manager",
    "manager",
    "accountant",
    "lawyer",
    "auditor_ro",
    "clerk",
    "teacher",
    "student",
    "executor",
    "worker",
)
_PORTAL: tuple[str, ...] = ("client", "client_admin", "client_user")

#: ПРАВО ЭКРАНА → РОЛИ (кроме owner/admin — они везде).
#: Коды — ровно те, что в ``frontend/src/permissions/permissions.ts``.
SCREEN_ACCESS: dict[str, tuple[str, ...]] = {
    # --- обзор ---
    "dashboard.view": (*_INTERNAL, *_PORTAL, "contractor_inspector"),
    "command_center.view": (*_OT_PROS, "hr", "line_manager", "manager"),
    "analytics.view": (*_OT_LEADS, "ot_specialist", "hr", "line_manager", "manager"),
    "reports.view": (
        *_OT_PROS,
        "hr",
        "line_manager",
        "manager",
        "accountant",
        "auditor_ro",
        "client",
    ),
    "calendar.view": (*_OT_PROS, "hr", "line_manager"),
    "data_quality.view": (*_OT_LEADS, "ot_specialist", "hr", "line_manager"),
    "employee_card.view": (*_OT_LEADS, "ot_specialist", "hr", "line_manager"),
    # --- организация и люди ---
    "company.view": (*_OT_PROS, "hr", "line_manager", "manager", "accountant"),
    "company.create": (*_OT_LEADS, "ot_specialist", "hr"),
    "branch.view": (*_OT_PROS, "hr", "line_manager", "manager"),
    "branch.manage": (*_OT_LEADS, "hr"),
    "person.view": (*_OT_PROS, "hr", "line_manager", "manager"),
    "person.create": (*_OT_LEADS, "ot_specialist", "hr"),
    "reference.view": (*_OT_PROS,),
    "contractor.view": (*_OT_LEADS, "ot_specialist", "contractor_inspector", "client_admin"),
    "contractor.manage": (*_OT_LEADS, "ot_specialist"),
    # --- документооборот ---
    "doc.view": (*_INTERNAL, *_PORTAL, "contractor_inspector"),
    "doc.create": (*_OT_PROS, "hr", "line_manager", "manager", "clerk", "worker", "client_admin"),
    "doc.sign": (*_OT_LEADS, "lawyer"),
    "doc.export": (*_OT_PROS, "hr", "line_manager", "accountant", "lawyer"),
    "template.view": (*_OT_LEADS, "ot_specialist", "clerk"),
    "template.create": (*_OT_LEADS,),
    "template.edit": (*_OT_LEADS,),
    "template.delete": (),
    "template.activate": (),
    "pack.view": (
        *_OT_PROS,
        "hr",
        "line_manager",
        "manager",
        "clerk",
        "client_admin",
        "client_user",
    ),
    "generation.view": (*_OT_PROS, "hr", "line_manager", "manager", "clerk"),
    "file.view": (
        *_OT_PROS,
        "hr",
        "line_manager",
        "manager",
        "clerk",
        "worker",
        "client_admin",
        "client_user",
    ),
    "task.view": (
        *_OT_PROS,
        "hr",
        "line_manager",
        "manager",
        "clerk",
        "executor",
        "worker",
    ),
    "task.update": (*_OT_LEADS, "ot_specialist", "hr", "line_manager"),
    "workflow.manage": (),
    # --- охрана труда ---
    "risk.view": (*_OT_PROS, "line_manager"),
    "risk.assess": (*_OT_LEADS, "ot_specialist"),
    "risk.edit": (*_OT_LEADS,),
    "risk.export": (*_OT_PROS,),
    "activity.view": (*_OT_LEADS, "ot_specialist", "pb_engineer", "hr", "line_manager"),
    "ppe.view": (*_OT_PROS, "line_manager", "executor"),
    "ppe.issue": (*_OT_LEADS, "ot_specialist"),
    "warehouse.view": (*_OT_LEADS, "ot_specialist"),
    "training.view": (
        *_OT_LEADS,
        "ot_specialist",
        "hr",
        "line_manager",
        "teacher",
        "student",
        "executor",
        "worker",
    ),
    "training.assign": (*_OT_LEADS, "ot_specialist", "hr", "teacher"),
    "training.complete": (*_OT_LEADS, "hr", "teacher"),
    "medical.view": (*_OT_LEADS, "ot_specialist", "hr", "line_manager"),
    "permit.view": (*_OT_LEADS, "ot_specialist", "hr", "line_manager"),
    "permit.manage": (*_OT_LEADS, "ot_specialist"),
    "work_permit.view": (*_OT_LEADS, "ot_specialist", "pb_engineer", "line_manager"),
    "work_permit.manage": (*_OT_LEADS, "ot_specialist"),
    "incident.view": (*_OT_LEADS, "ot_specialist", "pb_engineer", "line_manager", "executor"),
    "incident.create": (*_OT_LEADS, "ot_specialist", "pb_engineer", "line_manager"),
    "inspection.view": (
        *_OT_LEADS,
        "ot_specialist",
        "pb_engineer",
        "hr",
        "line_manager",
        "contractor_inspector",
    ),
    "inspection.create": (*_OT_LEADS, "ot_specialist", "pb_engineer"),
    "audit_prep.view": (*_OT_LEADS, "ot_specialist", "pb_engineer", "hr", "line_manager"),
    "committee.view": (*_OT_LEADS, "ot_specialist", "hr", "line_manager"),
    "sout.view": (*_OT_LEADS, "ot_specialist"),
    "npa.view": (*_OT_PROS,),
    # --- контуры дисциплин: ровно как у discipline_write_roles (срез-119) ---
    "fire_safety.view": (*_OT_LEADS, "ot_specialist", "pb_engineer"),
    "fire_safety.manage": (*_OT_LEADS, "ot_specialist", "pb_engineer"),
    "fire_training.view": (*_OT_LEADS, "ot_specialist", "pb_engineer"),
    "fire_inspections.view": (*_OT_LEADS, "ot_specialist", "pb_engineer", "contractor_inspector"),
    "industrial_safety.view": (*_OT_LEADS, "ot_specialist"),
    "industrial_safety.manage": (*_OT_LEADS, "ot_specialist"),
    "ecology.view": (*_OT_LEADS, "ot_specialist", "ecologist"),
    "ecology.manage": (*_OT_LEADS, "ot_specialist", "ecologist"),
    "civil_defense.view": (*_OT_LEADS, "ot_specialist"),
    "civil_defense.manage": (*_OT_LEADS, "ot_specialist"),
    "road_safety.view": (*_OT_LEADS, "ot_specialist"),
    "road_safety.manage": (*_OT_LEADS, "ot_specialist"),
    # --- бизнес ---
    "managed_clients.view": (*_OT_LEADS, "manager"),
    "client_portal.view": (*_OT_LEADS, "manager", *_PORTAL),
    "crm_finance.view": ("accountant", "manager"),
    "budget.view": (*_OT_LEADS, "accountant"),
    "budget.manage": (*_OT_LEADS, "accountant"),
    "imports.manage": (*_OT_LEADS, "ot_specialist", "hr"),
    # --- ПДн: ровно как _PDN_ROLES (срез-208) ---
    "privacy.view": ("hr",),
    # --- администрирование: только владелец и администратор ---
    "admin.manage_roles": (),
    "admin.manage_tenants": (),
    "admin.outbox_manage": (),
    "integrations.view": (),
    "rules.view": (),
    "rules.manage": (),
    "settings.view": (*_OT_LEADS,),
    "audit.view": (*_OT_LEADS, "auditor_ro"),
}


def _expand(roles: Iterable[str]) -> frozenset[str]:
    expanded: set[str] = set(roles)
    for role in list(expanded):
        synonym = ROLE_SYNONYMS.get(role)
        if synonym:
            expanded.add(synonym)
    return frozenset(expanded)


def screen_roles(permission: str) -> tuple[str, ...]:
    """Роли, которым разрешено то, что стоит за правом экрана. Для ручек.

    Возвращает список С owner и admin: ручки объявляют полный список, а
    неизвестное право — ошибка на импорте, а не тихо пустой список (пустой
    список у ``rbac`` означал бы «любой вошедший»).
    """

    if permission not in SCREEN_ACCESS:
        raise KeyError(f"право экрана «{permission}» не заведено в SCREEN_ACCESS")
    return tuple(sorted(_expand(SCREEN_ACCESS[permission]) | set(_FULL_ACCESS)))


def permissions_for_roles(roles: Iterable[str]) -> list[str]:
    """Права экрана для набора ролей человека. Для ``/auth/me``.

    Синоним роли получает права своей пары; владелец и администратор — всё.
    """

    held = {str(role).strip().lower() for role in roles if role}
    if held & set(_FULL_ACCESS):
        return sorted(SCREEN_ACCESS)
    return sorted(code for code, granted in SCREEN_ACCESS.items() if held & _expand(granted))


def all_screen_permissions() -> tuple[str, ...]:
    return tuple(sorted(SCREEN_ACCESS))


def _check_roles_exist() -> None:
    """Таблица не смеет называть роль, которой нет в продукте.

    Именно так серверный словарь и разошёлся с жизнью: в нём годами жили
    ``hse_specialist`` и ``fire_engineer``, а настоящие роли не получали
    ничего. Проверка на импорте — чтобы это не повторилось молча.
    """

    known = {role.value for role in RoleEnum}
    for code, granted in SCREEN_ACCESS.items():
        unknown = set(granted) - known
        if unknown:
            raise RuntimeError(
                f"SCREEN_ACCESS[{code!r}] называет несуществующие роли: {sorted(unknown)}"
            )


_check_roles_exist()
