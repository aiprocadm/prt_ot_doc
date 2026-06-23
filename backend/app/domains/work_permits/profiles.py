"""Профили видов работ наряда-допуска: приказ, структурная секция, валидация.

Чистый модуль (без I/O / без sqlalchemy) — как lifecycle.py. Полиморфный шов
per-type специфики: legal_reference, словари структурной секции, валидация
type_specific, сборка печатной StructuredSection. Высота читает колонку
safety_systems; ОЗП — type_specific JSON.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.work_permits import print_form as pf

# --- словари структурной секции ОЗП (902н) ---
GAS_PARAMETERS = {
    "oxygen": "Кислород (O₂), %",
    "flammable": "Горючие газы и пары, % НКПР",
    "harmful": "Вредные вещества, мг/м³",
}
VENTILATION_MODES = {
    "natural": "Естественная",
    "forced": "Принудительная",
    "none": "Не применяется",
    "not_required": "Не требуется",
}
_GAS_KEYS = {"parameter", "value", "norm", "measured_at"}

# --- словарь средств пожаротушения (огневые работы, ППР 1479) ---
FIRE_FIGHTING_MEANS = {
    "extinguisher_powder": "Огнетушитель порошковый",
    "extinguisher_co2": "Огнетушитель углекислотный",
    "water": "Вода (ёмкость/ведро)",
    "sand": "Ящик с песком",
    "felt": "Кошма / асбестовое полотно",
    "fire_hose": "Пожарный кран/рукав",
}

# --- словарь СИЗ органов дыхания (газоопасные работы, ФНП 528) ---
RESPIRATORY_PPE = {
    "hose_mask": "Шланговый противогаз (ПШ-1/ПШ-2)",
    "scba": "Автономный дыхательный аппарат (ИДА)",
    "isolating_mask": "Изолирующий противогаз",
    "filter_mask": "Фильтрующий противогаз/респиратор",
    "air_supply": "Аппарат с принудительной подачей воздуха",
}

# --- технические мероприятия подготовки места (электроустановки, ПОТЭЭ 903н п.16.1) ---
ELECTRICAL_MEASURES = {
    "disconnect": "Произведены отключения, приняты меры против ошибочного включения",
    "lockout_signs": "На приводах и ключах управления вывешены запрещающие плакаты",
    "verify_no_voltage": "Проверено отсутствие напряжения на токоведущих частях",
    "grounding": "Установлено заземление (включены ЗН / наложены переносные заземления)",
    "barriers_signs": "Вывешены плакаты, ограждены рабочие места и токоведущие части под напряжением",
}

# --- условие производства работ по напряжению (электроустановки) ---
VOLTAGE_CONDITIONS = {
    "de_energized": "Со снятием напряжения",
    "near_live": "Без снятия напряжения вблизи токоведущих частей",
    "away_live": "Без снятия напряжения вдали от токоведущих частей",
}

# --- подземные коммуникации в зоне земляных работ ---
UTILITIES = {
    "power_cable": "Электрические кабели",
    "gas_pipe": "Газопровод",
    "water_sewer": "Водопровод / канализация",
    "heating": "Теплосеть",
    "comms": "Кабели связи",
}

# --- способ защиты стенок выемки (земляные работы) ---
SHORING_METHODS = {
    "natural_slopes": "Естественные откосы",
    "shield_bracing": "Крепление щитами / распорами",
    "sheet_piling": "Шпунтовое ограждение",
    "none_shallow": "Без крепления (мелкая выемка)",
}


@dataclass(frozen=True)
class WorkTypeProfile:
    code: str
    label: str
    legal_reference: str
    structured_kind: str | None  # "safety_systems" | "confined_env" | "fire_safety" | "gas_works" | "electrical_safety" | "excavation_safety" | None


PROFILES: dict[str, WorkTypeProfile] = {
    "height": WorkTypeProfile(
        "height",
        "Работа на высоте",
        "Приказ Минтруда России от 16.11.2020 № 782н",
        "safety_systems",
    ),
    "confined_space": WorkTypeProfile(
        "confined_space",
        "Работа в ограниченных и замкнутых пространствах",
        "Приказ Минтруда России от 15.12.2020 № 902н",
        "confined_env",
    ),
    "electrical": WorkTypeProfile(
        "electrical",
        "Работа в электроустановках",
        "Приказ Минтруда России от 15.12.2020 № 903н",
        "electrical_safety",
    ),
    "hot_work": WorkTypeProfile(
        "hot_work",
        "Огневые работы",
        "Постановление Правительства РФ от 16.09.2020 № 1479 (ППР)",
        "fire_safety",
    ),
    "gas_hazardous": WorkTypeProfile(
        "gas_hazardous",
        "Газоопасные работы",
        "Приказ Ростехнадзора от 15.12.2020 № 528 "
        "(ФНП «Правила безопасного ведения газоопасных, огневых и ремонтных работ»)",
        "gas_works",
    ),
    "excavation": WorkTypeProfile(
        "excavation",
        "Земляные работы",
        "Приказ Минтруда России от 11.12.2020 № 883н (ПОТ при строительстве, реконструкции и ремонте)",
        "excavation_safety",
    ),
}

_GENERIC = WorkTypeProfile(
    "generic", "Работы повышенной опасности", "Правила по охране труда", None
)


def profile_for(work_type: str) -> WorkTypeProfile:
    return PROFILES.get(work_type, _GENERIC)


def legal_reference(work_type: str) -> str:
    return profile_for(work_type).legal_reference


def _validate_gas_analysis(rows: list | None) -> None:
    """Общая валидация таблицы замеров (ОЗП и огневые). None — ок."""
    if rows is None:
        return
    if not isinstance(rows, list):
        raise ValueError("gas_analysis must be a list")
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("gas_analysis row must be an object")
        bad = set(r) - _GAS_KEYS
        if bad:
            raise ValueError(f"unknown gas_analysis keys: {sorted(bad)}")
        if r.get("parameter") not in GAS_PARAMETERS:
            raise ValueError(f"invalid gas parameter: {r.get('parameter')!r}")


def _validate_code_list(values: list | None, allowed: dict, field_name: str) -> None:
    """Список кодов ⊆ allowed (или None). Общий для fire_fighting_means и respiratory_ppe."""
    if values is None:
        return
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    for v in values:
        if v not in allowed:
            raise ValueError(f"invalid {field_name}: {v!r}")


def validate_type_specific(work_type: str, payload: dict | None) -> None:
    """Raise ValueError если type_specific не соответствует профилю вида работ.

    None/пустой — всегда ок. Виды без структурной секции не принимают непустой payload
    (включая height — он использует safety_systems-колонку).
    """
    if not payload:
        return
    kind = profile_for(work_type).structured_kind
    if kind == "confined_env":
        unknown = set(payload) - {"gas_analysis", "ventilation"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        vent = payload.get("ventilation")
        if vent is not None and vent not in VENTILATION_MODES:
            raise ValueError(f"invalid ventilation: {vent!r}")
        _validate_gas_analysis(payload.get("gas_analysis"))
    elif kind == "fire_safety":
        unknown = set(payload) - {"fire_fighting_means", "gas_analysis"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("fire_fighting_means"), FIRE_FIGHTING_MEANS, "fire_fighting_means")
        _validate_gas_analysis(payload.get("gas_analysis"))
    elif kind == "gas_works":
        unknown = set(payload) - {"respiratory_ppe", "gas_analysis"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("respiratory_ppe"), RESPIRATORY_PPE, "respiratory_ppe")
        _validate_gas_analysis(payload.get("gas_analysis"))
    elif kind == "electrical_safety":
        unknown = set(payload) - {"technical_measures", "voltage_condition"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("technical_measures"), ELECTRICAL_MEASURES, "technical_measures")
        vc = payload.get("voltage_condition")
        if vc is not None and vc not in VOLTAGE_CONDITIONS:
            raise ValueError(f"invalid voltage_condition: {vc!r}")
    elif kind == "excavation_safety":
        unknown = set(payload) - {"utilities", "shoring"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("utilities"), UTILITIES, "utilities")
        shoring = payload.get("shoring")
        if shoring is not None and shoring not in SHORING_METHODS:
            raise ValueError(f"invalid shoring: {shoring!r}")
    else:
        raise ValueError(f"type_specific is not accepted for work_type {work_type!r}")


def _gas_table(rows):
    """StructuredTable из строк замеров (ОЗП и огневые) или None."""
    if not rows:
        return None
    return pf.StructuredTable(
        headers=["Параметр", "Значение", "Норма", "Замер"],
        rows=[
            [
                GAS_PARAMETERS.get(r.get("parameter"), r.get("parameter") or ""),
                str(r.get("value") or ""),
                str(r.get("norm") or ""),
                str(r.get("measured_at") or ""),
            ]
            for r in rows
        ],
    )


def build_structured_section(
    work_type: str,
    *,
    safety_systems: list[str] | None,
    type_specific: dict | None,
):
    """Собрать печатную StructuredSection по профилю (или None)."""
    kind = profile_for(work_type).structured_kind
    if kind == "safety_systems":
        if not safety_systems:
            return None
        labels = ", ".join(pf.safety_system_label(c) for c in safety_systems)
        return pf.StructuredSection(
            title="Системы обеспечения безопасности (782н)", kv=[("Системы", labels)], table=None
        )
    if kind == "confined_env":
        ts = type_specific or {}
        kv: list[tuple[str, str]] = []
        vent = ts.get("ventilation")
        if vent:
            kv.append(("Вентиляция", VENTILATION_MODES.get(vent, vent)))
        table = _gas_table(ts.get("gas_analysis"))
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Анализ воздушной среды и вентиляция (902н)", kv=kv, table=table
        )
    if kind == "fire_safety":
        ts = type_specific or {}
        kv = []
        means = ts.get("fire_fighting_means") or []
        if means:
            kv.append(
                ("Средства пожаротушения", ", ".join(FIRE_FIGHTING_MEANS.get(m, m) for m in means))
            )
        table = _gas_table(ts.get("gas_analysis"))
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Пожарная безопасность огневых работ (1479)", kv=kv, table=table
        )
    if kind == "gas_works":
        ts = type_specific or {}
        kv = []
        ppe = ts.get("respiratory_ppe") or []
        if ppe:
            kv.append(("СИЗОД", ", ".join(RESPIRATORY_PPE.get(c, c) for c in ppe)))
        table = _gas_table(ts.get("gas_analysis"))
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Защита органов дыхания и анализ среды (528)", kv=kv, table=table
        )
    if kind == "electrical_safety":
        ts = type_specific or {}
        kv = []
        vc = ts.get("voltage_condition")
        if vc:
            kv.append(("Условие проведения", VOLTAGE_CONDITIONS.get(vc, vc)))
        measures = ts.get("technical_measures") or []
        if measures:
            kv.append(
                ("Технические мероприятия", "; ".join(ELECTRICAL_MEASURES.get(m, m) for m in measures))
            )
        if not kv:
            return None
        return pf.StructuredSection(
            title="Меры безопасности в электроустановках (903н)", kv=kv, table=None
        )
    if kind == "excavation_safety":
        ts = type_specific or {}
        kv = []
        shoring = ts.get("shoring")
        if shoring:
            kv.append(("Защита стенок выемки", SHORING_METHODS.get(shoring, shoring)))
        utils = ts.get("utilities") or []
        if utils:
            kv.append(("Подземные коммуникации", ", ".join(UTILITIES.get(u, u) for u in utils)))
        if not kv:
            return None
        return pf.StructuredSection(
            title="Безопасность земляных работ (883н)", kv=kv, table=None
        )
    return None
