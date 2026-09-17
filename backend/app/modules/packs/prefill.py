"""Подсказки мастера фабрики из реестров (решение владельца, handoff #960).

ЗАЧЕМ. Три комплекта отчётности подряд — экология (разд. 55.3), БДД (56.2) и
ГО-ЧС (56.1) — заставили написать одну и ту же границу: «числа в отчёт вносит
специалист, платформа их из реестров не собирает». При этом реестры полны:
парк, водители, ДТП, нарушения. Человек открывает отчёт и вручную переписывает
в него то, что система уже знает.

ГЛАВНОЕ РЕШЕНИЕ: ПОДСКАЗКА, А НЕ ОТВЕТ.

Значение из реестра приходит в поле ``suggested`` и НЕ становится ответом само
собой. Причина не в осторожности, а в том, чьё имя стоит под документом:
отчёт подписывает специалист, и он отвечает за каждое число в нём. Подставь
платформа число молча — и человек подпишет то, чего не проверял, а расхождение
реестра с действительностью станет ЕГО расхождением.

Поэтому подсказка всегда приходит С ИСТОЧНИКОМ («ДТП за 365 дней по реестру
БДД»): по нему видно, что именно посчитано и за какой срок. Число без
источника проверить нельзя, а значит нельзя и подтвердить.

ГРАНИЦА ОСТАЁТСЯ: платформа не решает, какой период у отчёта и какие числа в
нём верны. Она показывает своё и называет, откуда оно.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline, areas_of_discipline
from app.models.civil_defense import (
    CD_FORMATION_KINDS,
    CD_GO_CATEGORIES,
    CivilDefenseFormation,
    CivilDefenseFormationMember,
    CivilDefenseProfile,
)
from app.models.ecology import (
    EmissionMeasurement,
    EmissionSource,
    EnvironmentalFacility,
    WasteMovement,
    WaterUsagePoint,
    WaterUsageRecord,
)
from app.models.incidents import Incident, IncidentStatus
from app.models.industrial_safety import (
    OPO_HAZARD_CLASSES,
    DeviceWorkRecord,
    HazardousFacility,
    ProductionControlMeasure,
    ProductionControlPlan,
    TechnicalDevice,
)
from app.models.inspections import Attestation
from app.models.road_safety import Driver, RoadAccident, TrafficViolation, Vehicle
from app.modules.packs.definitions import (
    PACK_CODE_BDD_REPORTS,
    PACK_CODE_ECO_REPORTS,
    PACK_CODE_GOCHS_REPORTS,
    PACK_CODE_OPO_REPORTS,
)
from app.services.discipline_road_safety import admitted_driver_where

__all__ = ["Suggestion", "suggestions_for_pack"]

#: окно подсказок по происшествиям — ТО ЖЕ, что у сводки контура БДД. Два
#: разных окна дали бы два разных числа на соседних экранах, и специалист не
#: смог бы понять, какое из них правда.
_WINDOW_DAYS = 365


@dataclass(slots=True, frozen=True)
class Suggestion:
    """Подсказка к одному вопросу мастера.

    ``source`` обязателен: число без объяснения, откуда оно, проверить нельзя,
    а неподтверждаемую подсказку подставлять в документ бессмысленно.
    """

    value: str
    source: str


async def _road_safety_suggestions(session: AsyncSession, tenant_id: str) -> dict[str, Suggestion]:
    """Подсказки для отчётности БДД — из реестров контура.

    Считается ТОЛЬКО то, что реестр знает точно:

    * парк и водительский состав — на СЕГОДНЯ (число в эксплуатации меняется
      каждый день, и «сколько их было в прошлом квартале» реестр не помнит);
    * происшествия и нарушения — за окно, ТО ЖЕ, что в сводке контура.

    Мероприятия по предупреждению ДТП НЕ подсказываются: они живут в ядровом
    CAPA и относятся к конкретным происшествиям, а «сколько мероприятий
    запланировано на период» — вопрос плана, которого у платформы нет.
    """

    today = date.today()
    window_start = datetime.combine(
        today - timedelta(days=_WINDOW_DAYS), time.min, tzinfo=timezone.utc
    )

    vehicles = int(
        await session.scalar(
            select(func.count())
            .select_from(Vehicle)
            .where(
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
                Vehicle.status == "in_service",
            )
        )
        or 0
    )
    drivers = int(
        await session.scalar(
            select(func.count())
            .select_from(Driver)
            # Правило «допущенный водитель» одно на платформу (срез-88).
            .where(*admitted_driver_where(tenant_id))
        )
        or 0
    )
    accident_window = (
        RoadAccident.tenant_id == tenant_id,
        RoadAccident.deleted_at.is_(None),
        RoadAccident.occurred_at >= window_start,
    )
    accidents = int(
        await session.scalar(select(func.count()).select_from(RoadAccident).where(*accident_window))
        or 0
    )
    injured, fatalities = (
        await session.execute(
            select(
                func.coalesce(func.sum(RoadAccident.injured_count), 0),
                func.coalesce(func.sum(RoadAccident.fatalities_count), 0),
            ).where(*accident_window)
        )
    ).one()
    violations = int(
        await session.scalar(
            select(func.count())
            .select_from(TrafficViolation)
            .where(
                TrafficViolation.tenant_id == tenant_id,
                TrafficViolation.deleted_at.is_(None),
                TrafficViolation.occurred_at >= window_start,
            )
        )
        or 0
    )

    window = f"за {_WINDOW_DAYS} дн."
    return {
        "bdd_report_vehicles": Suggestion(str(vehicles), "в эксплуатации сегодня по реестру ТС"),
        "bdd_report_drivers": Suggestion(str(drivers), "допущено сегодня по карточкам водителей"),
        "bdd_report_accidents": Suggestion(str(accidents), f"ДТП {window} по учёту ДТП"),
        # пострадавшие и погибшие в одном ответе, потому что и в форме они
        # одной строкой: разносить их по двум подсказкам значило бы
        # предлагать то, чего в документе нет
        "bdd_report_injured": Suggestion(
            f"{int(injured)} / {int(fatalities)}",
            f"пострадало / погибло {window} по учёту ДТП",
        ),
        "bdd_report_violations": Suggestion(
            str(violations), f"нарушений {window} по учёту нарушений"
        ),
    }


async def _ecology_suggestions(session: AsyncSession, tenant_id: str) -> dict[str, Suggestion]:
    """Подсказки для отчётности экологии — из реестров контура.

    ГОД БЕРЁТСЯ ПРОШЛЫЙ, И ЭТО РЕШЕНИЕ, А НЕ УМОЛЧАНИЕ. Экологическую
    отчётность сдают ЗА ПРОШЕДШИЙ год (2-ТП и декларация — до марта), и
    предлагать текущий, неполный, значило бы подсунуть заведомо неверное
    число. Год назван В ИСТОЧНИКЕ: если специалист отчитывается за другой, он
    это увидит и не подставит.

    ОТЛИЧИЕ ОТ БДД: там окно скользящее (365 дней), потому что аварийность
    смотрят «за последний год» в любой день. Здесь период — КАЛЕНДАРНЫЙ год,
    потому что таковы формы отчётности. Одинаковое окно для обеих дисциплин
    было бы удобнее в коде и неверно по существу.

    ПЛАТА ЗА НВОС НЕ ПОДСКАЗЫВАЕТСЯ: суммы считаются по ставкам и
    коэффициентам, а не по объёмам напрямую (разд. 55.3 прямо оставил расчёт
    специалисту). Подсказать сумму значило бы посчитать за него.
    """

    year = date.today().year - 1
    start, end = date(year, 1, 1), date(year, 12, 31)
    window = f"за {year} год"

    async def _waste_sum(kind: str) -> str:
        total = await session.scalar(
            select(func.coalesce(func.sum(WasteMovement.quantity_tons), 0)).where(
                WasteMovement.tenant_id == tenant_id,
                WasteMovement.deleted_at.is_(None),
                WasteMovement.kind == kind,
                WasteMovement.happened_on >= start,
                WasteMovement.happened_on <= end,
            )
        )
        return f"{float(total or 0):.3f}"

    generated = await _waste_sum("generated")
    transferred = await _waste_sum("transferred")
    disposed = await _waste_sum("disposed")

    sources = int(
        await session.scalar(
            select(func.count())
            .select_from(EmissionSource)
            .where(
                EmissionSource.tenant_id == tenant_id,
                EmissionSource.deleted_at.is_(None),
            )
        )
        or 0
    )
    measurements = int(
        await session.scalar(
            select(func.count())
            .select_from(EmissionMeasurement)
            .where(
                EmissionMeasurement.tenant_id == tenant_id,
                EmissionMeasurement.deleted_at.is_(None),
                EmissionMeasurement.measured_on >= start,
                EmissionMeasurement.measured_on <= end,
            )
        )
        or 0
    )

    suggestions: dict[str, Suggestion] = {
        "eco_waste_generated": Suggestion(
            generated, f"образование, тонн {window} по учёту движения отходов"
        ),
        "eco_waste_transferred": Suggestion(
            transferred, f"передано оператору, тонн {window} по учёту движения отходов"
        ),
        "eco_waste_disposed": Suggestion(
            disposed, f"размещено, тонн {window} по учёту движения отходов"
        ),
        "eco_air_sources": Suggestion(
            str(sources), "источников выбросов сегодня по реестру источников"
        ),
        "eco_pek_measurements": Suggestion(str(measurements), f"замеров {window} по журналу ПЭК"),
    }

    # Объект НВОС подсказывается ТОЛЬКО когда он ОДИН. У организации их бывает
    # несколько, и выбрать за специалиста, о котором из них отчёт, платформа
    # не может — а подсунуть первый попавшийся хуже, чем не подсказать вовсе.
    facilities = list(
        (
            await session.execute(
                select(EnvironmentalFacility).where(
                    EnvironmentalFacility.tenant_id == tenant_id,
                    EnvironmentalFacility.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(facilities) == 1:
        only = facilities[0]
        suggestions["eco_nvos_number"] = Suggestion(
            only.register_number, "единственный объект НВОС в реестре"
        )
        suggestions["eco_nvos_category"] = Suggestion(
            only.category, "категория единственного объекта НВОС"
        )

    # Забор и сброс — РАЗНЫЕ величины, и складывать их нельзя (так прямо
    # сказано у словаря видов точек). Тип лежит у ТОЧКИ, а объём у записи,
    # поэтому сумма берётся соединением, а не одним полем.
    async def _water_sum(kind: str) -> str:
        total = await session.scalar(
            select(func.coalesce(func.sum(WaterUsageRecord.volume_cubic_meters), 0))
            .select_from(WaterUsageRecord)
            .join(WaterUsagePoint, WaterUsagePoint.id == WaterUsageRecord.point_id)
            .where(
                WaterUsageRecord.tenant_id == tenant_id,
                WaterUsageRecord.deleted_at.is_(None),
                WaterUsageRecord.period_year == year,
                WaterUsagePoint.kind == kind,
            )
        )
        return f"{float(total or 0):.3f}"

    suggestions["eco_water_intake"] = Suggestion(
        await _water_sum("intake"), f"забор, м³ {window} по учёту водопользования"
    )
    suggestions["eco_water_discharge"] = Suggestion(
        await _water_sum("discharge"), f"сброс, м³ {window} по учёту водопользования"
    )
    return suggestions


async def _industrial_safety_suggestions(
    session: AsyncSession, tenant_id: str
) -> dict[str, Suggestion]:
    """Подсказки для отчётности ПромБез — из реестров контура.

    ДВА РАЗНЫХ ВРЕМЕНИ, и это не небрежность. Сведения об организации ПК
    подают ЗА ПРОШЕДШИЙ календарный год (Правила организации ПК — до 1
    апреля), поэтому ПОТОКИ — проведённые экспертизы, мероприятия плана —
    считаются за прошлый год, как у экологии. А ОПО, устройства и
    аттестации — это СОСТОЯНИЕ, у него нет «за год»: сколько объектов
    эксплуатируется, спрашивают на день составления. Считать состояние «на
    31 декабря прошлого года» платформа не может — истории состояний в
    реестрах нет, и число получилось бы выдуманным. Год и «сегодня» названы
    В ИСТОЧНИКЕ, чтобы специалист видел, что именно перед ним.

    МЕРОПРИЯТИЯ ПЛАНА ПК ПОДСКАЗЫВАЮТСЯ ТОЛЬКО ПРИ ПЛАНЕ НА ТОТ ГОД. Без
    плана «0 запланировано» читалось бы как «план был, но пустой» — а плана
    не было, и это другой факт.

    ИНЦИДЕНТЫ — ТОЛЬКО РАЗМЕЧЕННЫЕ ПРОМБЕЗОМ (in01). До разметки они не
    подсказывались вовсе: выдать все происшествия организации за инциденты
    на ОПО значило бы вписать в отчёт для Ростехнадзора чужие числа. Теперь
    считаются происшествия с дисциплиной «промышленная безопасность» за
    прошлый год; неразмеченные НЕ считаются — «не размечено» не значит «не
    промбез», но и не значит «промбез», а отчёт в надзор — не место для
    догадок. Отменённые не считаются: их зарегистрировали по ошибке.
    """

    today = date.today()
    year = today.year - 1
    start, end = date(year, 1, 1), date(year, 12, 31)
    window = f"за {year} год"

    facilities = (
        (
            await session.execute(
                select(HazardousFacility).where(
                    HazardousFacility.tenant_id == tenant_id,
                    HazardousFacility.deleted_at.is_(None),
                    HazardousFacility.status == "registered",
                )
            )
        )
        .scalars()
        .all()
    )
    by_class = {code: 0 for code in OPO_HAZARD_CLASSES}
    for facility in facilities:
        if facility.hazard_class in by_class:
            by_class[facility.hazard_class] += 1

    # только эксплуатируемые: списанное устройство ни в отчёт, ни в
    # просрочку не попадает (тот же отбор, что у сводки контура)
    devices = (
        (
            await session.execute(
                select(TechnicalDevice).where(
                    TechnicalDevice.tenant_id == tenant_id,
                    TechnicalDevice.deleted_at.is_(None),
                    TechnicalDevice.status != "decommissioned",
                )
            )
        )
        .scalars()
        .all()
    )
    epb_overdue = sum(
        1 for d in devices if d.epb_valid_until is not None and d.epb_valid_until < today
    )
    epb_done = int(
        await session.scalar(
            select(func.count())
            .select_from(DeviceWorkRecord)
            .where(
                DeviceWorkRecord.tenant_id == tenant_id,
                DeviceWorkRecord.deleted_at.is_(None),
                DeviceWorkRecord.kind == "epb",
                DeviceWorkRecord.performed_on >= start,
                DeviceWorkRecord.performed_on <= end,
            )
        )
        or 0
    )

    # аттестации СВОЕЙ дисциплины — по областям Ростехнадзора, а не по
    # заполненности поля: иначе проверка знаний водителя по «ПДД» попала бы
    # в отчёт по промбезопасности (прецедент сводки контура)
    attestations = (
        (
            await session.execute(
                select(Attestation.expires_at).where(
                    Attestation.tenant_id == tenant_id,
                    Attestation.deleted_at.is_(None),
                    Attestation.area_code.in_(areas_of_discipline(Discipline.INDUSTRIAL_SAFETY)),
                )
            )
        )
        .scalars()
        .all()
    )
    attestations_valid = sum(
        1 for expires_at in attestations if expires_at is not None and expires_at >= today
    )
    attestations_overdue = sum(
        1 for expires_at in attestations if expires_at is not None and expires_at < today
    )

    suggestions: dict[str, Suggestion] = {
        "opo_facilities_count": Suggestion(
            str(len(facilities)), "действующих ОПО сегодня по реестру ОПО"
        ),
        "opo_facilities_by_class": Suggestion(
            ", ".join(f"{code} класс — {count}" for code, count in by_class.items()),
            "действующие ОПО по классам сегодня по реестру ОПО",
        ),
        "opo_devices_count": Suggestion(
            str(len(devices)),
            "устройств в эксплуатации сегодня по реестру технических устройств",
        ),
        "opo_epb_done": Suggestion(
            str(epb_done), f"экспертиз ПБ {window} по журналу работ устройств"
        ),
        "opo_epb_overdue": Suggestion(
            str(epb_overdue),
            "устройств с истёкшим заключением ЭПБ сегодня по реестру устройств",
        ),
        "opo_attestations_count": Suggestion(
            str(attestations_valid),
            "действующих аттестаций по областям Ростехнадзора сегодня",
        ),
        "opo_attestations_overdue": Suggestion(
            str(attestations_overdue),
            "просроченных аттестаций по областям Ростехнадзора сегодня",
        ),
    }

    plan_id = await session.scalar(
        select(ProductionControlPlan.id).where(
            ProductionControlPlan.tenant_id == tenant_id,
            ProductionControlPlan.deleted_at.is_(None),
            ProductionControlPlan.year == year,
        )
    )
    if plan_id is not None:
        statuses = (
            (
                await session.execute(
                    select(ProductionControlMeasure.status).where(
                        ProductionControlMeasure.tenant_id == tenant_id,
                        ProductionControlMeasure.deleted_at.is_(None),
                        ProductionControlMeasure.plan_id == plan_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        # отменённое мероприятие — не запланированное: его сняли с плана
        planned = sum(1 for status in statuses if status != "cancelled")
        done = sum(1 for status in statuses if status == "done")
        suggestions["opo_pc_measures_planned"] = Suggestion(
            str(planned), f"мероприятий плана ПК на {year} год без отменённых"
        )
        suggestions["opo_pc_measures_done"] = Suggestion(
            str(done), f"выполненных мероприятий плана ПК на {year} год"
        )

    # Происшествие — ядровая сущность с ДАТОЙ-ВРЕМЕНЕМ; границы года берутся
    # по UTC, как хранится ``occurred_at``.
    year_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    year_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    incidents = int(
        await session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.tenant_id == tenant_id,
                Incident.deleted_at.is_(None),
                Incident.discipline == Discipline.INDUSTRIAL_SAFETY.value,
                Incident.status != IncidentStatus.CANCELLED,
                Incident.occurred_at >= year_start,
                Incident.occurred_at < year_end,
            )
        )
        or 0
    )
    suggestions["opo_incidents_count"] = Suggestion(
        str(incidents),
        f"происшествий {window} с дисциплиной «промышленная безопасность» по реестру "
        "происшествий (неразмеченные и отменённые не считаются)",
    )
    return suggestions


async def _civil_defense_suggestions(
    session: AsyncSession, tenant_id: str
) -> dict[str, Suggestion]:
    """Подсказки для отчётности ГО и ЧС — из реестров контура.

    ЭТО ЗАКРЫВАЕТ СТАРУЮ ГРАНИЦУ. Срез-6 честно записал: «формирования и
    личный состав в системе есть, но подставлять их в документ платформа не
    умеет». С решением #960 умеет — тем же способом, что БДД, экология и
    ПромБез: подсказкой с источником, а не ответом.

    Подсказываются ТОЛЬКО факты о внесённом на СЕГОДНЯ:

    * формирования — сколько их в реестре, с разбивкой по видам в источнике;
    * личный состав — строки состава БЕЗ даты вывода. Правило ТО ЖЕ, что у
      сводки готовности контура, иначе сводка и мастер показали бы разные
      числа за один и тот же день. Считаются строки, а не люди: один человек
      в двух формированиях — две строки, и сводка считает так же;
    * категория объекта и ответственный — ТОЛЬКО когда объект по ГО ОДИН
      (правило единственного объекта, как у НВОС в экологии): о котором из
      нескольких площадок положение, платформа за специалиста не решает.

    НЕ ПОДСКАЗЫВАЮТСЯ: обеспеченность СИЗ и средства оповещения (таких
    реестров у контура нет), всё о ЧС в донесении (событие описывает тот, кто
    его видел), период и составитель (решение специалиста).
    """

    formations = (
        (
            await session.execute(
                select(CivilDefenseFormation).where(
                    CivilDefenseFormation.tenant_id == tenant_id,
                    CivilDefenseFormation.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    by_kind = {code: 0 for code in CD_FORMATION_KINDS}
    for formation in formations:
        if formation.kind in by_kind:
            by_kind[formation.kind] += 1
    # В источнике вид назван коротко («НАСФ»), а не полным словарным именем:
    # подсказка должна читаться в одну строку.
    kinds_note = ", ".join(
        f"{label.split(' ', 1)[0]} — {by_kind[code]}" for code, label in CD_FORMATION_KINDS.items()
    )
    members_active = int(
        await session.scalar(
            select(func.count())
            .select_from(CivilDefenseFormationMember)
            .where(
                CivilDefenseFormationMember.tenant_id == tenant_id,
                CivilDefenseFormationMember.deleted_at.is_(None),
                CivilDefenseFormationMember.released_on.is_(None),
            )
        )
        or 0
    )
    suggestions = {
        "gochs_formations_count": Suggestion(
            str(len(formations)), f"формирований сегодня по реестру ГО и ЧС ({kinds_note})"
        ),
        "gochs_personnel_count": Suggestion(
            str(members_active),
            "в составе формирований сегодня по реестру (выведенные не считаются)",
        ),
    }

    profiles = (
        (
            await session.execute(
                select(CivilDefenseProfile).where(
                    CivilDefenseProfile.tenant_id == tenant_id,
                    CivilDefenseProfile.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(profiles) == 1:
        only = profiles[0]
        suggestions["facility_category"] = Suggestion(
            CD_GO_CATEGORIES.get(only.category, only.category),
            "категория единственного объекта в реестре ГО",
        )
        # Ответственный у объекта — свободная строка, и пустая означает «не
        # назначен», а не «неизвестен»: пустую подсказывать нечего.
        if only.responsible:
            suggestions["gochs_responsible"] = Suggestion(
                only.responsible, "ответственный единственного объекта в реестре ГО"
            )
    return suggestions


#: Комплекты, у которых есть источник в реестрах. Пусто для комплекта —
#: НЕ ошибка: у большинства документов числа берутся не из данных, а из
#: решения специалиста, и подсказывать там нечего.
_RESOLVERS = {
    PACK_CODE_BDD_REPORTS: _road_safety_suggestions,
    PACK_CODE_ECO_REPORTS: _ecology_suggestions,
    PACK_CODE_GOCHS_REPORTS: _civil_defense_suggestions,
    PACK_CODE_OPO_REPORTS: _industrial_safety_suggestions,
}


async def suggestions_for_pack(
    session: AsyncSession, tenant_id: str, pack_code: str
) -> dict[str, Suggestion]:
    """Подсказки к вопросам мастера или пустой словарь.

    Пустой словарь — законный ответ, а не «не нашли»: у комплекта может не
    быть ни одного вопроса, на который отвечает реестр.
    """

    resolver = _RESOLVERS.get(pack_code)
    if resolver is None:
        return {}
    return await resolver(session, tenant_id)
