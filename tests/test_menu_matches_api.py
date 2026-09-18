"""Сторож: пункт меню виден ровно тем, кого пускает его ручка (срез-217).

ЧТО БЫЛО. ``docs/audit/ACCESS_MENU_VS_API.md``: 51 пункт меню из 77 был виден
роли, которой ручка отвечает 403. Человек видел раздел, заходил и получал
отказ — и решал, что сломана платформа. Повторный замер 17.09 дал 44 из 67
сопоставленных; первый экран после входа был отказом для большинства ролей.

ПОЧЕМУ ТАК ВЫШЛО. Прав было три словаря — у ручек, у витрины и на сервере — и
ни один не знал о двух других. Теперь список ролей у права живёт ОДИН РАЗ, в
``core/screen_access.SCREEN_ACCESS``: из него берут роли ручки, из него
``/auth/me`` отдаёт витрине права для меню.

ЧТО ПРОВЕРЯЕТСЯ — ПО ЖИВОМУ ПРИЛОЖЕНИЮ, а не по тексту:

1. у каждого пункта меню есть ручка, которую его страница зовёт первой;
2. роли, которым карта даёт право пункта, ручка ПУСКАЕТ — роли достаются из
   замыкания проверки доступа (``rbac``/``abac``), как в срезе-213;
3. карта витрины (её собственная запасная карта) НЕ ШИРЕ серверной: иначе в
   офлайне меню показало бы больше, чем сервер потом разрешит;
4. разбор видит выдачу права — доказано поломкой, потому что сторож по тексту
   молчит и когда всё хорошо, и когда сломан он сам.

ГРАНИЦА НАЗВАНА. Составные страницы (справочники, портал клиента) зовут
несколько ручек; здесь взята та, без которой страница пуста. Ручки без ролевого
сторожа («любой вошедший») пункт не ограничивают и проходят как совпадение.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.routing import iter_route_contexts

from app.api import create_app
from app.core.screen_access import SCREEN_ACCESS, screen_roles
from app.models.tenant_billing import RoleEnum

REPO_ROOT = Path(__file__).resolve().parents[1]
NAV_TS = REPO_ROOT / "frontend" / "src" / "router" / "navigationConfig.ts"
PERMISSIONS_TS = REPO_ROOT / "frontend" / "src" / "permissions" / "permissions.ts"

V1 = "/api/v1"

#: Пункт меню (путь витрины) → ручка, которую страница зовёт первой.
#: Составные страницы — по ручке, без которой страница пуста.
MENU_ENDPOINTS: dict[str, tuple[str, str]] = {
    "/dashboard": ("GET", f"{V1}/dashboard/summary"),
    "/companies": ("GET", f"{V1}/companies"),
    "/branches": ("GET", f"{V1}/branches"),
    "/persons": ("GET", f"{V1}/persons"),
    "/documents": ("GET", f"{V1}/documents"),
    "/templates": ("GET", f"{V1}/templates"),
    "/packs": ("GET", f"{V1}/package-presets"),
    "/packs/wizard": ("GET", f"{V1}/packs/scenarios"),
    "/generation": ("POST", f"{V1}/documents/generate"),
    "/documents/quick-generate": ("POST", f"{V1}/documents/generate"),
    "/pipelines/runs": ("GET", f"{V1}/pipelines/runs"),
    "/archive": ("GET", f"{V1}/files"),
    "/search": ("GET", f"{V1}/search"),
    "/command-center": ("GET", f"{V1}/operational/dashboard"),
    "/workspace/attention": ("GET", f"{V1}/workspace/attention"),
    "/workspace/data-quality": ("GET", f"{V1}/data-quality/report"),
    "/exports": ("GET", f"{V1}/exports"),
    "/tasks": ("GET", f"{V1}/tasks"),
    "/notifications": ("GET", f"{V1}/notifications"),
    "/calendar": ("GET", f"{V1}/calendar/events"),
    "/approvals/inbox": ("GET", f"{V1}/approvals"),
    "/approval-routes": ("GET", f"{V1}/approval-routes"),
    "/signatures": ("GET", f"{V1}/sign/requests"),
    "/edo": ("GET", f"{V1}/edo/messages"),
    "/risk": ("GET", f"{V1}/risks"),
    "/activities": ("GET", f"{V1}/corrective-actions"),
    "/ppe": ("GET", f"{V1}/ppe/issues"),
    "/warehouse": ("GET", f"{V1}/ppe/stock/levels"),
    "/training": ("GET", f"{V1}/training/programs"),
    "/briefings": ("GET", f"{V1}/briefings/entries"),
    "/internships": ("GET", f"{V1}/internships"),
    "/medical": ("GET", f"{V1}/medical/exams"),
    "/permits": ("GET", f"{V1}/permits"),
    "/work-permits": ("GET", f"{V1}/work-permits"),
    "/incidents": ("GET", f"{V1}/incidents"),
    "/inspections": ("GET", f"{V1}/inspections"),
    "/audit-prep": ("GET", f"{V1}/inspection-prep/packages"),
    "/committees": ("GET", f"{V1}/committees"),
    "/sout": ("GET", f"{V1}/sout"),
    "/fire-safety": ("GET", f"{V1}/fire-safety/documents"),
    "/fire-training": ("GET", f"{V1}/fire-safety/drills"),
    "/fire-inspections": ("GET", f"{V1}/prescriptions"),
    "/industrial-safety": ("GET", f"{V1}/industrial-safety/facilities"),
    "/ecology": ("GET", f"{V1}/ecology/facilities"),
    "/civil-defense": ("GET", f"{V1}/civil-defense/formations"),
    "/road-safety": ("GET", f"{V1}/road-safety/vehicles"),
    "/managed-clients": ("GET", f"{V1}/managed-clients"),
    "/crm-finance": ("GET", f"{V1}/contracts"),
    "/npa": ("GET", f"{V1}/npa"),
    "/privacy/subjects": ("GET", f"{V1}/privacy/agreements"),
    "/privacy/breaches": ("GET", f"{V1}/privacy/breaches"),
    "/npa/requirements": ("GET", f"{V1}/compliance/requirements"),
    "/reports": ("GET", f"{V1}/reports/kpi"),
    "/reports/builder": ("GET", f"{V1}/report-builder/definitions"),
    "/analytics/trends": ("GET", f"{V1}/analytics/trends/incidents"),
    "/analytics": ("GET", f"{V1}/analytics/dashboard/executive"),
    "/committees/kpi": ("GET", f"{V1}/committees/kpi"),
    "/client-portal/dashboard": ("GET", f"{V1}/client-portal/dashboard"),
    "/client-portal/packages": ("GET", f"{V1}/client-portal/packages"),
    "/client-portal/documents": ("GET", f"{V1}/client-portal/documents"),
    "/client-portal/history": ("GET", f"{V1}/client-portal/history"),
    "/client-portal/requests": ("GET", f"{V1}/client-portal/requests"),
    "/budget": ("GET", f"{V1}/budget/budgets"),
    "/imports": ("GET", f"{V1}/imports/batches"),
    "/integrations": ("GET", f"{V1}/integrations/readiness"),
    "/reference": ("GET", f"{V1}/ppe/items"),
    "/sites": ("GET", f"{V1}/sites"),
    "/contractors": ("GET", f"{V1}/contractors/registry"),
    "/admin": ("GET", f"{V1}/admin/users"),
    "/admin/tenants": ("GET", f"{V1}/platform/tenants"),
    "/admin/branding": ("GET", f"{V1}/platform/branding"),
    "/admin/billing": ("GET", f"{V1}/billing/plan"),
    "/admin/outbox": ("GET", f"{V1}/admin/outbox"),
    "/rules": ("GET", f"{V1}/rules"),
    "/admin/health": ("GET", f"{V1}/admin/tenant-health"),
    "/audit": ("GET", f"{V1}/audit"),
    "/settings": ("GET", f"{V1}/tenancy/context"),
}

#: Экраны без ручки: страница не обращается к серверу вовсе.
MENU_WITHOUT_ENDPOINT: frozenset[str] = frozenset({"/help/sync-conflicts"})

#: Витрина зовёт одну и ту же роль иначе, чем сервер.
FRONT_TO_SERVER_ROLE: dict[str, str] = {"ot_pb_head": "ot_pb_lead"}

SERVER_ROLES: frozenset[str] = frozenset(role.value for role in RoleEnum)


# --- разбор витрины ---


def _menu_items() -> list[tuple[str, str, str]]:
    """(подпись, путь, код права) для каждого пункта главного меню."""

    source = NAV_TS.read_text(encoding="utf-8")
    names = re.findall(
        r'label: "([^"]+)",\s+to: "([^"]+)",\s+icon: \w+,\s+(?://[^\n]*\n\s*)*permission: PERMISSIONS\.(\w+)',
        source,
    )
    catalogue = _permission_catalogue()
    return [(label, to, catalogue[name]) for label, to, name in names]


def _permission_catalogue() -> dict[str, str]:
    source = PERMISSIONS_TS.read_text(encoding="utf-8")
    block = re.search(r"export const PERMISSIONS = \{(.*?)\n\} as const;", source, re.S)
    assert block is not None, "каталог PERMISSIONS не найден"
    return dict(re.findall(r"(\w+): \"([^\"]+)\"", block.group(1)))


def _front_role_permissions() -> dict[str, set[str]]:
    """Запасная карта витрины: роль (в именах сервера) → коды прав.

    Тот же разбор, что у сторожа контуров дисциплин (срез-119): блок роли —
    либо список ``PERMISSIONS.X``, либо ``ALL_PERMISSIONS`` с исключениями.
    """

    source = PERMISSIONS_TS.read_text(encoding="utf-8")
    catalogue = _permission_catalogue()
    base_block = re.search(r"const baseOpsPermissions: Permission\[\] = \[(.*?)\n\];", source, re.S)
    assert base_block is not None
    base_ops = set(re.findall(r"PERMISSIONS\.(\w+)", base_block.group(1)))

    block = re.search(
        r"export const ROLE_PERMISSIONS: Record<Role, Permission\[\]> = \{\n(.*?)\n\};",
        source,
        re.S,
    )
    assert block is not None, "карта ROLE_PERMISSIONS не найдена"
    entries: dict[str, str] = {}
    current: str | None = None
    for line in block.group(1).split("\n"):
        started = re.match(r"^  (\w+): ", line)
        if started:
            current = started.group(1)
            entries[current] = ""
        if current is not None:
            entries[current] += line + "\n"

    result: dict[str, set[str]] = {}
    for role, text in entries.items():
        if "ALL_PERMISSIONS" in text:
            excluded = set(re.findall(r"!== PERMISSIONS\.(\w+)", text))
            names = set(catalogue) - excluded
        else:
            names = set(re.findall(r"PERMISSIONS\.(\w+)", text))
            if "...baseOpsPermissions" in text:
                names |= base_ops
        result[FRONT_TO_SERVER_ROLE.get(role, role)] = {catalogue[n] for n in names}
    return result


# --- живые ручки ---


def _closure_roles(func) -> frozenset[str] | None:
    """``normalized_roles`` из замыкания ``rbac``; ``None`` — это не rbac."""

    code = getattr(func, "__code__", None)
    closure = getattr(func, "__closure__", None)
    if code is None or closure is None or "normalized_roles" not in code.co_freevars:
        return None
    return closure[code.co_freevars.index("normalized_roles")].cell_contents


def _module_gate(func) -> tuple[str, str] | None:
    """``(ресурс, действие)`` из замыкания сторожа прав модуля; ``None`` — не он.

    СРЕЗ-227. Второй рубеж продукта: ``require_permission("briefings.read")``
    разворачивается в ``require_action(resource_type=…, action=…)``, и решение
    принимает движок прав модуля, а не список ролей. Разбор обязан видеть и его.
    """

    code = getattr(func, "__code__", None)
    closure = getattr(func, "__closure__", None)
    if code is None or closure is None:
        return None
    names = code.co_freevars
    if "resource_type" not in names or "action" not in names:
        return None
    resource = closure[names.index("resource_type")].cell_contents
    action = closure[names.index("action")].cell_contents
    if not isinstance(resource, str) or not isinstance(action, str):
        return None
    return resource, action


def _module_gate_roles(resource: str, action: str) -> frozenset[str]:
    """Кого пускает рубеж прав модуля."""

    from app.core.rbac_abac import permissions_for_role

    code = f"{resource}:{action}".lower()
    # Владелец и администратор проходят рубеж всегда (явная оговорка в движке).
    admitted = {"owner", "admin"}
    admitted |= {role for role in SERVER_ROLES if code in permissions_for_role(role)}
    return frozenset(admitted)


def _route_roles(route) -> frozenset[str] | None:
    """Роли, которые пускает ручка; ``None`` — рубежа нет вовсе.

    СРЕЗ-227: рубежей ДВА, и раньше разбор видел только первый. У ручек
    инструктажей, заданий генерации, корпоративных рисков и обучения стоит
    ``rbac()`` БЕЗ ролей (любой вошедший), а настоящий отказ выдаёт движок прав
    модуля. Разбор считал такие ручки «не ограниченными», и пятнадцати ролям
    меню обещало разделы, куда ручка отвечала 403.
    """

    found: list[frozenset[str]] = []
    stack, seen = [route.dependant], set()
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        roles = _closure_roles(dep.call)
        if roles:
            found.append(roles)
        gate = _module_gate(dep.call)
        if gate is not None:
            found.append(_module_gate_roles(*gate))
        stack.extend(dep.dependencies)
    if not found:
        return None
    effective = found[0]
    for item in found[1:]:
        effective &= item
    return effective


@pytest.fixture(scope="module")
def live_routes() -> dict[tuple[str, str], object]:
    app = create_app()
    index: dict[tuple[str, str], object] = {}
    for context in iter_route_contexts(app.routes):
        route = getattr(context, "route", context)
        path = getattr(context, "path", None) or getattr(route, "path", "")
        if not hasattr(route, "dependant"):
            continue
        for method in getattr(route, "methods", None) or ():
            index[(method, path)] = route
            index[(method, path.rstrip("/"))] = route
    return index


# --- проверки ---


def test_каждый_пункт_меню_сопоставлен_ручке() -> None:
    """Пункт без ручки в реестре — сторож его не проверяет, а значит, врёт."""

    paths = {to for _, to, _ in _menu_items()}
    unmapped = paths - set(MENU_ENDPOINTS) - MENU_WITHOUT_ENDPOINT
    assert not unmapped, f"пункты меню без ручки в реестре: {sorted(unmapped)}"


def test_каждая_ручка_реестра_существует(live_routes) -> None:
    missing = [
        f"{method} {path}"
        for method, path in MENU_ENDPOINTS.values()
        if (method, path) not in live_routes
    ]
    assert not missing, f"в реестре названы ручки, которых нет: {missing}"


@pytest.mark.parametrize(
    "label,to,code", _menu_items(), ids=lambda v: v if v.startswith("/") else ""
)
def test_меню_не_шире_ручки(label: str, to: str, code: str, live_routes) -> None:
    """ГЛАВНОЕ. Кому карта даёт право пункта — того ручка обязана пустить."""

    if to in MENU_WITHOUT_ENDPOINT:
        pytest.skip("страница не обращается к серверу")
    method, path = MENU_ENDPOINTS[to]
    admitted = _route_roles(live_routes[(method, path)])
    if admitted is None:
        return  # рубежа нет вовсе — ручка открыта любому вошедшему
    granted = set(screen_roles(code)) & SERVER_ROLES
    refused = sorted(granted - admitted)
    assert not refused, (
        f"«{label}» ({to}): пункт виден ролям {refused}, а {method} {path} их не пускает. "
        f"Ручка обязана брать роли из screen_roles({code!r})."
    )


def test_запасная_карта_витрины_не_шире_серверной() -> None:
    """В офлайне меню рисуется по карте витрины — она не смеет обещать больше."""

    wider: list[str] = []
    for role, codes in _front_role_permissions().items():
        if role not in SERVER_ROLES:
            continue  # роли, которых на сервере нет, серверу и не предъявят
        for code in sorted(codes):
            if role not in set(screen_roles(code)):
                wider.append(f"{role}: {code}")
    assert not wider, "карта витрины даёт больше, чем сервер:\n  " + "\n  ".join(wider)


def test_разбор_видит_второй_рубеж(live_routes) -> None:
    """Срез-227. Доказано поломкой: пока разбор не знал про права модуля, ручки
    инструктажей читались как «открыты любому вошедшему», и сторож молчал.

    Проверяется НЕ список ролей, а сам факт: у этой ручки рубеж ВИДЕН и он уже
    кого-то не пускает.
    """

    admitted = _route_roles(live_routes[("GET", f"{V1}/briefings/entries")])
    assert admitted is not None, "рубеж прав модуля снова невидим для разбора"
    assert "lawyer" not in admitted, "рубеж виден, но никого не ограничивает"
    assert {"owner", "admin", "ot_specialist"} <= admitted


def test_разбор_видит_выдачу_права() -> None:
    """Доказано поломкой: без этого предыдущая проверка зелена и при пустом разборе."""

    front = _front_role_permissions()
    assert "ot_specialist" in front and "ppe.view" in front["ot_specialist"]
    assert "student" in front and "ppe.view" not in front["student"]
    assert len(_menu_items()) > 60, "разбор меню потерял пункты"


def test_карта_покрывает_каталог_витрины() -> None:
    catalogue = set(_permission_catalogue().values())
    assert catalogue == set(SCREEN_ACCESS), (
        f"не в таблице: {sorted(catalogue - set(SCREEN_ACCESS))}; "
        f"лишние: {sorted(set(SCREEN_ACCESS) - catalogue)}"
    )


def test_руководитель_не_меньше_специалиста_по_всем_ручкам(live_routes) -> None:
    """Срез-223: правило карты — по ВСЕМ живым ручкам, не только за пунктами меню.

    Замер 17.09 после среза-217: 60 ручек ВНЕ меню пускали специалиста по ОТ и
    отказывали его руководителям — один и тот же список «admin, owner,
    ot_specialist», скопированный из одного коммита по одиннадцати файлам.
    Теперь их права живут в карте (``*.manage``, ``doc.edit``), а этот сторож
    не даёт списку «без руководителей» появиться снова где угодно.
    """

    leads = {"ot_pb_lead", "ot_head"}
    behind: list[str] = []
    seen_routes: set[tuple[str, int]] = set()
    checked = 0
    for (method, path), route in live_routes.items():
        if (method, id(route)) in seen_routes:
            continue
        seen_routes.add((method, id(route)))
        roles = _route_roles(route)
        if roles is None or "ot_specialist" not in roles:
            continue
        checked += 1
        missing = leads - roles
        if missing:
            behind.append(f"{method} {path}: без {sorted(missing)}")
    assert checked > 400, f"разбор увидел лишь {checked} ручек со специалистом — сломан?"
    assert not behind, (
        "ручки пускают специалиста ОТ, но не его руководителей — "
        "роли обязаны браться из screen_roles(...):\n  " + "\n  ".join(behind)
    )
