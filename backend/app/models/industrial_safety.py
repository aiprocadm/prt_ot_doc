"""Промышленная безопасность — предметные модели дисциплины (Доп. №1 разд. 54.2).

Архитектурный принцип мультидисциплинарности (преамбула разд. 54): общее ядро
(площадки, люди, документы, проверки, задачи) НЕ дублируется — дисциплина
добавляет только своё. Первая собственная сущность контура ПромБеза — реестр
опасных производственных объектов (ОПО).

ПОЧЕМУ РЕЕСТР, А НЕ ПОЛЯ ПЛОЩАДКИ. До этого среза «ОПО» выражалось тремя
полями у ``Site``: булевым признаком, номером строкой и ``hazard_class`` —
свободной строкой на 32 знака. Два следствия, оба ломающие требование ТЗ
«идентификация, класс опасности, регистрационные сведения»:

1. **Свободная строка класса перегружена двумя смыслами.** В неё кладут и
   класс опасности ОПО («II»), и категорию пожарной опасности помещения
   («В2»). Вопрос «сколько у нас объектов I класса» не имел ответа.
2. **ОПО и площадка — не одно и то же.** На одной площадке бывает несколько
   зарегистрированных объектов (сеть газопотребления, склад ГСМ, подъёмные
   сооружения), у каждого свой регистрационный номер и свой класс опасности.
   Полями площадки этого не выразить в принципе.

``Site.hazard_class`` этот срез НЕ трогает: там лежат живые данные двух разных
смыслов, разбор которых — отдельное решение, а не побочный эффект.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Site

#: Классы опасности ОПО — ЗАКРЫТЫЙ словарь (ФЗ-116 «О промышленной
#: безопасности опасных производственных объектов», приложение 2). Ровно
#: четыре значения, римскими цифрами, как в свидетельстве о регистрации.
#: Именно от класса зависит режим надзора, поэтому величина обязана быть
#: считаемой, а не пересказываемой.
OPO_HAZARD_CLASSES: dict[str, str] = {
    "I": "I класс — чрезвычайно высокая опасность",
    "II": "II класс — высокая опасность",
    "III": "III класс — средняя опасность",
    "IV": "IV класс — низкая опасность",
}

#: Состояние объекта в государственном реестре. Исключение из реестра НЕ
#: удаляет запись: история эксплуатации и связанные документы остаются.
OPO_STATUSES: dict[str, str] = {
    "registered": "Зарегистрирован",
    "excluded": "Исключён из реестра",
}


class HazardousFacility(TenantBaseModel, SoftDeleteMixin):
    """Опасный производственный объект: идентификация и регистрационные сведения."""

    __tablename__ = "hazardous_facility"

    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id"), nullable=True, index=True)
    #: наименование как в свидетельстве о регистрации
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: регистрационный номер в госреестре (формат А01-12345-0001) — без него
    #: объекта в реестре не существует, это его удостоверение
    register_number: Mapped[str] = mapped_column(String(64), nullable=False)
    hazard_class: Mapped[str] = mapped_column(String(8), nullable=False)
    registered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    excluded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="registered", server_default="registered"
    )
    #: ответственный за производственный контроль на объекте
    responsible: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site | None] = relationship(backref="hazardous_facilities")

    __table_args__ = (
        # Один госномер — один объект. Дубль означает, что объект завели
        # дважды, и любой счёт по классам стал бы враньём.
        UniqueConstraint("tenant_id", "register_number", name="uq_hazardous_facility_register"),
        Index("ix_hazardous_facility_tenant_class", "tenant_id", "hazard_class"),
    )


#: Типы технических устройств, применяемых на ОПО — ЗАКРЫТЫЙ словарь по группам
#: федеральных норм и правил (ФНП). Свободная строка снова сделала бы разрезы
#: и отчётность невозможными, как это случилось с классом опасности площадки.
OPO_DEVICE_KINDS: dict[str, str] = {
    "pressure_vessel": "Сосуд, работающий под давлением",
    "boiler": "Котёл",
    "pipeline": "Трубопровод пара и горячей воды",
    "lifting": "Подъёмное сооружение",
    "gas_equipment": "Газовое оборудование",
    "other": "Иное техническое устройство",
}

#: Состояние устройства. Вывод из эксплуатации — это состояние, а НЕ удаление:
#: история устройства нужна и после списания.
OPO_DEVICE_STATUSES: dict[str, str] = {
    "in_operation": "В эксплуатации",
    "suspended": "Эксплуатация приостановлена",
    "decommissioned": "Выведено из эксплуатации",
}

#: Состояние заключения экспертизы промышленной безопасности.
#: «Заключения нет» — ОТДЕЛЬНОЕ состояние, а не разновидность просрочки: слить
#: их значило бы либо обвинить исправное новое устройство, либо спрятать то,
#: что отработало срок службы без экспертизы.
OPO_EPB_STATUS_TITLES: dict[str, str] = {
    "ok": "Заключение действует",
    "due_soon": "Заключение скоро истекает",
    "overdue": "Заключение просрочено",
    "absent": "Заключения нет",
}


class TechnicalDevice(TenantBaseModel, SoftDeleteMixin):
    """Техническое устройство на ОПО: учёт, назначенный срок службы, ЭПБ.

    ПОЧЕМУ СВОЯ СУЩНОСТЬ. Ядровые ``Asset``/``Equipment`` — это две и три
    колонки (имя, категория; серийный номер, статус) без единой ручки API и
    без единого поля срока; учитывать по ним экспертизу нечем. «Оборудование»
    не входит и в перечень общего ядра из преамбулы разд. 54, а ТЗ 54.2 прямо
    относит технические устройства к содержанию дисциплины.

    Привязка — к ОПО, а не к площадке: экспертиза и надзор идут по
    зарегистрированному объекту, а объектов на площадке бывает несколько.
    """

    __tablename__ = "opo_technical_device"

    facility_id: Mapped[str] = mapped_column(
        ForeignKey("hazardous_facility.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: заводской/учётный номер
    serial_number: Mapped[str | None] = mapped_column(String(64))
    commissioned_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: назначенный срок службы (из паспорта устройства)
    lifetime_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: номер заключения ЭПБ, внесённого в реестр Ростехнадзора
    epb_conclusion_number: Mapped[str | None] = mapped_column(String(64))
    epb_registered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: срок дальнейшей безопасной эксплуатации, установленный заключением
    epb_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="in_operation", server_default="in_operation"
    )
    notes: Mapped[str | None] = mapped_column(Text)

    facility: Mapped[HazardousFacility] = relationship(backref="technical_devices")

    __table_args__ = (Index("ix_opo_device_tenant_epb", "tenant_id", "epb_valid_until"),)


#: Виды работ по техническому устройству (разд. 54.2 «диагностика, история
#: работ»). ЗАКРЫТЫЙ словарь: свободная строка сделала бы историю
#: непересчитываемой, а отличить экспертизу от протирки — невозможным.
OPO_WORK_KINDS: dict[str, str] = {
    "diagnostics": "Техническое диагностирование",
    "technical_survey": "Техническое освидетельствование",
    "epb": "Экспертиза промышленной безопасности",
    "maintenance": "Техническое обслуживание",
    "repair": "Ремонт",
}

#: Вид работы, который ОДИН МОЖЕТ продлить эксплуатацию. Заключение о
#: возможности дальнейшей безопасной эксплуатации даёт только экспертиза;
#: если бы срок двигала любая работа, «протёрли и записали ТО» продлевало бы
#: жизнь устройству на бумаге.
OPO_WORK_KIND_EXTENDING_EPB = "epb"

#: Результат работы. Слова из области промышленной безопасности: экспертиза
#: отвечает на вопрос о ПРИГОДНОСТИ устройства к дальнейшей эксплуатации.
OPO_WORK_RESULTS: dict[str, str] = {
    "passed": "Пригодно к эксплуатации",
    "with_remarks": "Пригодно с условиями",
    "failed": "Не пригодно",
}

#: Результаты, при которых заключение продлевает эксплуатацию. «Не пригодно»
#: срок НЕ двигает: перенос означал бы «неисправно, но эксплуатировать ещё
#: пять лет» — это не вывод экспертизы (прецедент журнала работ контура ПБ).
OPO_WORK_PASSING_RESULTS: frozenset[str] = frozenset({"passed", "with_remarks"})


#: Состояние плана производственного контроля (разд. 54.2 «план ПК»).
PC_PLAN_STATUSES: dict[str, str] = {
    "draft": "Проект",
    "approved": "Утверждён",
    "archived": "Архивный",
}

#: Разделы плана ПК — ЗАКРЫТЫЙ словарь по составу производственного контроля
#: (ФЗ-116 ст. 11 и Правила организации ПК). Свободная строка сделала бы
#: отчётность непересчитываемой: «обучение», «Обучение персонала» и «учёба»
#: стали бы тремя разными разделами.
PC_MEASURE_SECTIONS: dict[str, str] = {
    "inspections": "Обследования и проверки состояния ОПО",
    "epb": "Экспертиза и диагностирование технических устройств",
    "training": "Обучение и аттестация персонала",
    "emergency": "Готовность к действиям при авариях",
    "violations": "Устранение выявленных нарушений",
    "reporting": "Отчётность в надзорные органы",
}

#: Состояние мероприятия. «Просрочено» — не хранится, а считается при чтении:
#: срок наступает сам, без запроса на изменение.
PC_MEASURE_STATUS_TITLES: dict[str, str] = {
    "planned": "Запланировано",
    "overdue": "Просрочено",
    "done": "Выполнено",
    "cancelled": "Отменено",
}

#: Состояния, которые МОЖНО выставить руками. «Просрочено» среди них нет — это
#: вычисляемое состояние, а не решение человека.
PC_MEASURE_WRITABLE_STATUSES: tuple[str, ...] = ("planned", "done", "cancelled")


class ProductionControlPlan(TenantBaseModel, SoftDeleteMixin):
    """План производственного контроля на год (разд. 54.2).

    Своя сущность, а не ядровая задача: план — это ДОКУМЕНТ организации,
    эксплуатирующей ОПО, со своим утверждением и ответственным за осуществление
    производственного контроля, и именно он предъявляется надзору. В ядре
    такого нет: там есть задачи (поручения), а не годовой документ.
    """

    __tablename__ = "opo_production_control_plan"

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: ответственный за осуществление производственного контроля
    responsible: Mapped[str | None] = mapped_column(String(255))
    approved_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # План ПК — ГОДОВОЙ документ: второй план на тот же год это дубль, от
        # которого вопрос «есть ли план на 2026 год» теряет смысл.
        UniqueConstraint("tenant_id", "year", name="uq_pc_plan_year"),
    )


class ProductionControlMeasure(TenantBaseModel, SoftDeleteMixin):
    """Мероприятие плана ПК: что, к какому сроку, кто и с каким результатом."""

    __tablename__ = "opo_production_control_measure"

    plan_id: Mapped[str] = mapped_column(
        ForeignKey("opo_production_control_plan.id"), nullable=False, index=True
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    responsible: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned", server_default="planned"
    )
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: что именно сделано — предъявляется надзору вместе с планом
    result: Mapped[str | None] = mapped_column(Text)

    plan: Mapped[ProductionControlPlan] = relationship(backref="measures")

    __table_args__ = (Index("ix_pc_measure_tenant_due", "tenant_id", "due_on"),)


#: Состояние срока аттестации словами. «Срока нет» — отдельное состояние, а не
#: «всё в порядке»: аттестация действует пять лет, и запись без даты окончания
#: означает неполные сведения, а не бессрочный допуск.
OPO_ATTESTATION_STATUS_TITLES: dict[str, str] = {
    "ok": "Действует",
    "due_soon": "Скоро истекает",
    "overdue": "Просрочена",
    "absent": "Срок не указан",
}


class DeviceWorkRecord(TenantBaseModel, SoftDeleteMixin):
    """Выполненная работа по техническому устройству: диагностика, ЭПБ, ремонт.

    До этой таблицы у устройства были только СРОКИ и ни одной записи о том, что
    с ним делали: отметить проведённую экспертизу можно было единственным
    способом — затереть срок правкой поля. Инспектор же спрашивает не «когда
    следующая экспертиза», а «покажите заключение по предыдущей».
    """

    __tablename__ = "opo_device_work"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("opo_technical_device.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: дата ФАКТИЧЕСКОГО выполнения — запись о работе это свидетельство, не план
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: кто выполнил: экспертная организация с реквизитами аттестата, подрядчик
    #: или свой персонал
    performer: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    #: номер заключения ЭПБ — обязателен для вида ``epb``: именно он вносится в
    #: реестр Ростехнадзора и предъявляется проверяющему
    conclusion_number: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    #: срок, установленный работой; у ЭПБ им переносится срок эксплуатации
    next_due: Mapped[date | None] = mapped_column(Date, nullable=True)

    device: Mapped[TechnicalDevice] = relationship(backref="work_records")

    __table_args__ = (Index("ix_opo_device_work_tenant_performed", "tenant_id", "performed_on"),)
