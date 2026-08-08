"""BIZ-49 срез-14: SQL-часть переноса данных клиента в его арендатор.

Чистые правила — в ``transfer.py``; здесь только копирование через доверенную
сессию (та же механика, что у перевода, — проверена PG-тестом фикса среза-13).

Копируются организация и сотрудники. Структурные ссылки на каталоги
аутсорсера (должность/рабочее место) обнуляются — каталоги не переносятся,
а «висячая» ссылка в чужой арендатор была бы дырой изоляции; текстовая
должность (``position_title``) сохраняется.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.transfer import is_person_transferable
from app.models.master_data import Company, Person, Position, Site, Workplace
from app.models.medical import MedicalExam, MedicalReferral, MedicalSuspension
from app.models.ppe import PPEIssue, PPEItem
from app.models.training import (
    Training,
    TrainingCertificate,
    TrainingCourse,
    TrainingProgram,
    TrainingSession,
)

__all__ = [
    "TransferResult",
    "copy_client_history",
    "copy_company_with_people",
    "copy_person_domains",
    "copy_training_history",
    "count_left_behind",
]


def _copy_value(value):
    """Значение для копии строки.

    JSON-колонки объявлены как ``MutableList``/``MutableDict``: присвоение
    ссылкой отдаёт копии ТОТ ЖЕ объект, и оба владельца начинают видеть
    чужие правки — правка у клиента меняла бы данные аутсорсера.
    """

    if isinstance(value, (list, dict)):
        return copy.deepcopy(value)
    return value


async def _company_rows(session: AsyncSession, model, *, tenant_id: str, company_id: str):
    """Живые строки, принадлежащие организации клиента."""

    stmt = select(model).where(model.tenant_id == tenant_id, model.company_id == company_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    return list((await session.execute(stmt)).scalars().all())


@dataclass
class TransferResult:
    company_map: dict[str, str] = field(default_factory=dict)
    people_map: dict[str, str] = field(default_factory=dict)
    people_skipped: int = 0
    #: Срез-16: структура организации клиента — площадки, должности, рабочие
    #: места. Это НЕ каталог аутсорсера: у всех трёх ``company_id`` NOT NULL,
    #: то есть они принадлежат организации клиента и едут вместе с ней.
    site_map: dict[str, str] = field(default_factory=dict)
    position_map: dict[str, str] = field(default_factory=dict)
    workplace_map: dict[str, str] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "company": len(self.company_map),
            "people": len(self.people_map),
            "people_skipped": self.people_skipped,
            "sites": len(self.site_map),
            "positions": len(self.position_map),
            "workplaces": len(self.workplace_map),
        }


_SITE_FIELDS = (
    "name",
    "address",
    "geo_json",
    "hazard_class",
    "site_type",
    "contact_name",
    "contact_phone",
    "contact_email",
    "is_hazardous_production_facility",
    "opo_register_number",
)

_POSITION_FIELDS = ("name", "description", "safety_category", "working_conditions_class")

_WORKPLACE_FIELDS = ("name", "description", "location", "working_conditions_class")

_PERSON_FIELDS = (
    "first_name",
    "last_name",
    "middle_name",
    "birth_date",
    "email",
    "phone",
    "personnel_number",
    "hired_at",
    "qualifications",
    "snils",
    "passport",
    "current_ppe",
    "ppe_sizes",
    "working_conditions_class",
    "hazardous_factors",
    "position_title",
    "employment_status",
)

_COMPANY_FIELDS = (
    "name",
    "inn",
    "kpp",
    "ogrn",
    "activity_type",
    "okved_codes",
    "legal_address",
    "actual_address",
    "director",
    "phone_numbers",
)


async def copy_company_with_people(
    session: AsyncSession,
    *,
    source_tenant_id: str,
    source_company_id: str,
    target_tenant_id: str,
) -> TransferResult:
    """Скопировать организацию клиента и её сотрудников в целевой арендатор."""

    result = TransferResult()

    src_company = (
        await session.execute(
            select(Company).where(
                Company.id == source_company_id,
                Company.tenant_id == source_tenant_id,
            )
        )
    ).scalar_one()

    new_company = Company(
        tenant_id=target_tenant_id,
        **{f: _copy_value(getattr(src_company, f)) for f in _COMPANY_FIELDS},
    )
    session.add(new_company)
    await session.flush()
    result.company_map[src_company.id] = new_company.id

    # Срез-16: структура организации ДО людей — иначе нечем перевешивать
    # position_id/workplace_id, и они снова обнулились бы.
    for site in await _company_rows(
        session, Site, tenant_id=source_tenant_id, company_id=source_company_id
    ):
        copy = Site(
            tenant_id=target_tenant_id,
            company_id=new_company.id,
            # Филиал — структура аутсорсера (строковая ссылка без FK).
            branch_id=None,
            **{f: _copy_value(getattr(site, f)) for f in _SITE_FIELDS},
        )
        session.add(copy)
        await session.flush()
        result.site_map[site.id] = copy.id

    for position in await _company_rows(
        session, Position, tenant_id=source_tenant_id, company_id=source_company_id
    ):
        copy = Position(
            tenant_id=target_tenant_id,
            company_id=new_company.id,
            **{f: _copy_value(getattr(position, f)) for f in _POSITION_FIELDS},
        )
        session.add(copy)
        await session.flush()
        result.position_map[position.id] = copy.id

    for workplace in await _company_rows(
        session, Workplace, tenant_id=source_tenant_id, company_id=source_company_id
    ):
        copy = Workplace(
            tenant_id=target_tenant_id,
            company_id=new_company.id,
            site_id=result.site_map.get(workplace.site_id) if workplace.site_id else None,
            **{f: _copy_value(getattr(workplace, f)) for f in _WORKPLACE_FIELDS},
        )
        session.add(copy)
        await session.flush()
        result.workplace_map[workplace.id] = copy.id

    people = (
        (
            await session.execute(
                select(Person).where(
                    Person.tenant_id == source_tenant_id,
                    Person.company_id == source_company_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for person in people:
        if not is_person_transferable(
            deleted_at=person.deleted_at, anonymized_at=person.anonymized_at
        ):
            result.people_skipped += 1
            continue
        copy = Person(
            tenant_id=target_tenant_id,
            company_id=new_company.id,
            # Срез-16: должность и рабочее место принадлежат организации
            # клиента (company_id NOT NULL), поэтому они переехали вместе с
            # ней — ссылки ПЕРЕВЕШИВАЮТСЯ, а не обнуляются. Обнуление
            # (срез-14) ослабляло контроль допуска: правила медосмотров и
            # норм СИЗ считаются по должности.
            position_id=result.position_map.get(person.position_id) if person.position_id else None,
            workplace_id=(
                result.workplace_map.get(person.workplace_id) if person.workplace_id else None
            ),
            **{f: _copy_value(getattr(person, f)) for f in _PERSON_FIELDS},
        )
        session.add(copy)
        await session.flush()
        result.people_map[person.id] = copy.id

    return result


# --- Срез-15: доменная история людей -----------------------------------------
#
# Копируются ТОЛЬКО записи, висящие на человеке. Каталоги и склад аутсорсера
# (нормы, партии, поставщики, справочники медфакторов) не переносятся: ссылка
# из чужого арендатора на каталог аутсорсера — не «неудобство», а дыра
# изоляции, через которую JOIN читает чужие данные.
#
# Исключение — КАРТОЧКИ каталога, без которых запись физически невозможна
# (курс у сессии обучения, программа у удостоверения: там FK NOT NULL) или
# ломается работа с копией (номенклатура у выдачи СИЗ: без неё замену СИЗ
# API отвергает). Копируется только карточка-справка, без методического
# содержания: модули, уроки, тесты остаются у аутсорсера.
#
# Ссылки на пользователей аутсорсера (кто выдал направление, кто снял
# отстранение, чья программа) обнуляются: в арендаторе клиента их нет.
#
# Служебные created_at/updated_at копий = даты оригинала: карточка сотрудника
# (766н) читает updated_at выдачи как дату события «списан/заменён/утерян».

#: Размер порции для ``IN (...)``: у клиента с тысячей сотрудников один список
#: параметров упирается в лимит переменных SQLite и раздувает план на PG.
_IN_CHUNK = 400

_EXAM_FIELDS = (
    "exam_type",
    "exam_date",
    "conclusion",
    "valid_until",
    "exam_kind",
    "fitness",
    "restrictions",
    "contraindications",
    "medical_org_name",
    "psychiatric_protocol_no",
    "psychiatric_activity_codes",
)

_REFERRAL_FIELDS = ("exam_kind", "due_at", "status", "medical_org_name")

_SUSPENSION_FIELDS = ("reason", "started_at", "lifted_at", "status")

_PPE_ISSUE_FIELDS = (
    "item_name",
    "quantity",
    "issued_at",
    "expires_at",
    "returned_at",
    "wear_days",
    "status",
    "certificate_no",
    "wear_percent",
    "return_wear_percent",
    "signature_doc_ref",
    "writeoff_reason",
)

#: Карточка номенклатуры: чем выдавали. Склад (min_stock, поставщик) не едет.
_PPE_ITEM_CARD_FIELDS = ("name", "code", "category", "default_wear_days")

#: Карточка курса: чему учили. Описание и metadata_json — методика аутсорсера.
_COURSE_CARD_FIELDS = ("title", "code", "duration_hours", "valid_period_days")

#: Карточка программы: структурные поля NOT NULL + часы/срок. Без описания.
_PROGRAM_CARD_FIELDS = (
    "code",
    "title",
    "category",
    "kind",
    "status",
    "duration_hours",
    "validity_months",
)

_LEGACY_TRAINING_FIELDS = ("course_name", "status", "scheduled_at", "completed_at", "expires_at")

_SESSION_FIELDS = ("status", "started_at", "completed_at", "score", "notes")

_CERTIFICATE_FIELDS = ("code", "number", "issued_at", "valid_until", "status")


def _history_stamps(row) -> dict[str, object]:
    """Служебные даты копии = даты оригинала (см. комментарий выше)."""

    return {"created_at": row.created_at, "updated_at": row.updated_at}


def _fields(row, names: tuple[str, ...]) -> dict[str, object]:
    return {name: _copy_value(getattr(row, name)) for name in names}


async def _live_rows(session: AsyncSession, model, *, tenant_id: str, person_ids: list[str]):
    """Живые (не удалённые) строки домена по перенесённым людям.

    ``tenant_id`` в условии обязателен: перенос идёт доверенной сессией
    (bypass RLS), и запрос без него прочитал бы строки ВСЕХ арендаторов.
    """

    rows: list = []
    for start in range(0, len(person_ids), _IN_CHUNK):
        chunk = person_ids[start : start + _IN_CHUNK]
        stmt = select(model).where(
            model.tenant_id == tenant_id,
            model.person_id.in_(chunk),
        )
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        rows.extend((await session.execute(stmt)).scalars().all())
    return rows


async def _copy_cards(
    session: AsyncSession,
    model,
    ids: set[str],
    *,
    source_tenant_id: str,
    target_tenant_id: str,
    fields: tuple[str, ...],
    dedupe_field: str,
    extra: dict[str, object] | None = None,
) -> dict[str, str]:
    """Скопировать карточки каталога, использованные переносимой историей.

    Дедупликация по ``dedupe_field``: уникальность каталогов объявлена на
    (tenant_id, name/title/code) и НЕ исключает мягко удалённые строки —
    поэтому существующая карточка ищется без фильтра ``deleted_at``, иначе
    вставка упала бы на констрейнте.
    """

    mapping: dict[str, str] = {}
    if not ids:
        return mapping
    id_list = list(ids)
    rows: list = []
    for start in range(0, len(id_list), _IN_CHUNK):
        rows.extend(
            (
                await session.execute(
                    select(model).where(
                        model.tenant_id == source_tenant_id,
                        model.id.in_(id_list[start : start + _IN_CHUNK]),
                    )
                )
            )
            .scalars()
            .all()
        )
    for row in rows:
        key = getattr(row, dedupe_field)
        existing = None
        if key is not None:
            existing = (
                (
                    await session.execute(
                        select(model).where(
                            model.tenant_id == target_tenant_id,
                            getattr(model, dedupe_field) == key,
                        )
                    )
                )
                .scalars()
                .first()
            )
        if existing is not None:
            mapping[row.id] = existing.id
            continue
        copy_row = model(
            tenant_id=target_tenant_id,
            **(extra or {}),
            **_fields(row, fields),
        )
        session.add(copy_row)
        await session.flush()
        mapping[row.id] = copy_row.id
    return mapping


async def copy_person_domains(
    session: AsyncSession,
    *,
    source_tenant_id: str,
    target_tenant_id: str,
    people_map: dict[str, str],
) -> dict[str, int]:
    """Скопировать медосмотры и выдачи СИЗ перенесённых людей."""

    counts: dict[str, int] = {}
    if not people_map:
        return counts
    person_ids = list(people_map)

    # Медосмотры. У exam и referral ВЗАИМНЫЕ внешние ключи (exam.referral_id ↔
    # referral.result_exam_id) — настоящий цикл: сначала направления без
    # результата, затем осмотры со ссылкой на направление, и только потом
    # обратная ссылка проставляется точечным UPDATE.
    referrals = await _live_rows(
        session, MedicalReferral, tenant_id=source_tenant_id, person_ids=person_ids
    )
    referral_map: dict[str, str] = {}
    for row in referrals:
        copy_row = MedicalReferral(
            tenant_id=target_tenant_id,
            person_id=people_map[row.person_id],
            # Пользователь аутсорсера в арендаторе клиента не существует.
            issued_by=None,
            result_exam_id=None,
            **_fields(row, _REFERRAL_FIELDS),
            **_history_stamps(row),
        )
        session.add(copy_row)
        await session.flush()
        referral_map[row.id] = copy_row.id
    counts["medical_referrals"] = len(referral_map)

    exams = await _live_rows(
        session, MedicalExam, tenant_id=source_tenant_id, person_ids=person_ids
    )
    exam_map: dict[str, str] = {}
    for row in exams:
        copy_row = MedicalExam(
            tenant_id=target_tenant_id,
            person_id=people_map[row.person_id],
            referral_id=referral_map.get(row.referral_id) if row.referral_id else None,
            **_fields(row, _EXAM_FIELDS),
            **_history_stamps(row),
        )
        session.add(copy_row)
        await session.flush()
        exam_map[row.id] = copy_row.id
    counts["medical_exams"] = len(exam_map)

    # Обратная ссылка — Core-UPDATE с ЯВНЫМИ updated_at/version: ORM-присваивание
    # подняло бы версию и переписало updated_at у только что скопированной
    # строки, то есть исказило бы дату события.
    dropped = 0
    for row in referrals:
        if not row.result_exam_id:
            continue
        new_exam_id = exam_map.get(row.result_exam_id)
        if new_exam_id is None:
            # Осмотр-результат не скопирован (мягко удалён): направление
            # остаётся без результата — случай видимый, а не молчаливый.
            dropped += 1
            continue
        await session.execute(
            update(MedicalReferral)
            .where(MedicalReferral.id == referral_map[row.id])
            .values(result_exam_id=new_exam_id, updated_at=row.updated_at, version=1)
        )
    await session.flush()
    counts["medical_referrals_result_dropped"] = dropped

    suspensions = await _live_rows(
        session, MedicalSuspension, tenant_id=source_tenant_id, person_ids=person_ids
    )
    for row in suspensions:
        session.add(
            MedicalSuspension(
                tenant_id=target_tenant_id,
                person_id=people_map[row.person_id],
                source_exam_id=exam_map.get(row.source_exam_id) if row.source_exam_id else None,
                lifted_by=None,
                **_fields(row, _SUSPENSION_FIELDS),
                **_history_stamps(row),
            )
        )
    await session.flush()
    counts["medical_suspensions"] = len(suspensions)

    # СИЗ: выдачи + КАРТОЧКИ использованной номенклатуры. Обнулить item_id было
    # бы дешевле, но тогда замену такой выдачи API отвергает («cannot replace an
    # issue without item_id») — копия выглядела бы живой, а работать бы не
    # могла. Склад (партии, поставщики, движения) не едет.
    issues = await _live_rows(session, PPEIssue, tenant_id=source_tenant_id, person_ids=person_ids)
    item_map = await _copy_cards(
        session,
        PPEItem,
        {row.item_id for row in issues if row.item_id},
        source_tenant_id=source_tenant_id,
        target_tenant_id=target_tenant_id,
        fields=_PPE_ITEM_CARD_FIELDS,
        dedupe_field="name",
    )
    counts["ppe_items"] = len(item_map)

    # Цепочка замен (replaces_issue_id — строковая ссылка на другую выдачу)
    # сшивается ПОРЯДКОМ вставки, а не вторым UPDATE: UPDATE поднял бы version
    # и переписал updated_at, из которого карточка 766н читает дату события.
    pending = {row.id: row for row in issues}
    issue_map: dict[str, str] = {}
    progressed = True
    while pending and progressed:
        progressed = False
        for old_id, row in list(pending.items()):
            ref = row.replaces_issue_id
            if ref and ref in pending:
                continue  # предшественник ещё не скопирован
            copy_row = PPEIssue(
                tenant_id=target_tenant_id,
                person_id=people_map[row.person_id],
                item_id=item_map.get(row.item_id) if row.item_id else None,
                replaces_issue_id=issue_map.get(ref) if ref else None,
                **_fields(row, _PPE_ISSUE_FIELDS),
                **_history_stamps(row),
            )
            session.add(copy_row)
            await session.flush()
            issue_map[old_id] = copy_row.id
            del pending[old_id]
            progressed = True
    for old_id, row in pending.items():  # цикл в данных — рвём цепочку явно
        copy_row = PPEIssue(
            tenant_id=target_tenant_id,
            person_id=people_map[row.person_id],
            item_id=item_map.get(row.item_id) if row.item_id else None,
            replaces_issue_id=None,
            **_fields(row, _PPE_ISSUE_FIELDS),
            **_history_stamps(row),
        )
        session.add(copy_row)
        await session.flush()
        issue_map[old_id] = copy_row.id
    counts["ppe_issues"] = len(issue_map)

    return counts


async def copy_training_history(
    session: AsyncSession,
    *,
    source_tenant_id: str,
    target_tenant_id: str,
    people_map: dict[str, str],
) -> dict[str, int]:
    """Скопировать историю обучения перенесённых людей.

    Переносится ЗАВЕРШЁННАЯ история (легаси-записи, сессии, удостоверения) с
    карточками использованных курсов и программ. «Живой» рантайм LMS (записи
    на курсы, попытки, группы, планы) не переносится осознанно: без модулей и
    тестов такая запись выглядела бы возобновляемой, а продолжить обучение в
    новом арендаторе было бы нечем.
    """

    counts: dict[str, int] = {}
    if not people_map:
        return counts
    person_ids = list(people_map)

    legacy = await _live_rows(session, Training, tenant_id=source_tenant_id, person_ids=person_ids)
    for row in legacy:
        session.add(
            Training(
                tenant_id=target_tenant_id,
                person_id=people_map[row.person_id],
                **_fields(row, _LEGACY_TRAINING_FIELDS),
                **_history_stamps(row),
            )
        )
    await session.flush()
    counts["trainings_legacy"] = len(legacy)

    sessions = await _live_rows(
        session, TrainingSession, tenant_id=source_tenant_id, person_ids=person_ids
    )
    certificates = await _live_rows(
        session, TrainingCertificate, tenant_id=source_tenant_id, person_ids=person_ids
    )

    course_ids = {row.course_id for row in sessions if row.course_id}
    course_ids |= {row.course_id for row in certificates if row.course_id}
    course_map = await _copy_cards(
        session,
        TrainingCourse,
        course_ids,
        source_tenant_id=source_tenant_id,
        target_tenant_id=target_tenant_id,
        fields=_COURSE_CARD_FIELDS,
        dedupe_field="title",
    )
    counts["training_courses"] = len(course_map)

    program_map = await _copy_cards(
        session,
        TrainingProgram,
        {row.training_program_id for row in certificates if row.training_program_id},
        source_tenant_id=source_tenant_id,
        target_tenant_id=target_tenant_id,
        fields=_PROGRAM_CARD_FIELDS,
        dedupe_field="code",
        # Владелец программы — пользователь аутсорсера, в новом арендаторе его нет.
        extra={"owner_user_id": None},
    )
    counts["training_programs"] = len(program_map)

    session_map: dict[str, str] = {}
    sessions_skipped = 0
    for row in sessions:
        new_course = course_map.get(row.course_id)
        if new_course is None:
            # course_id NOT NULL: без карточки курса сессия невозможна.
            sessions_skipped += 1
            continue
        copy_row = TrainingSession(
            tenant_id=target_tenant_id,
            person_id=people_map[row.person_id],
            course_id=new_course,
            # План обучения — инструмент аутсорсера, он не переносится.
            plan_id=None,
            **_fields(row, _SESSION_FIELDS),
            **_history_stamps(row),
        )
        session.add(copy_row)
        await session.flush()
        session_map[row.id] = copy_row.id
    counts["training_sessions"] = len(session_map)
    counts["training_sessions_skipped"] = sessions_skipped

    cert_count = 0
    certs_skipped = 0
    for row in certificates:
        new_program = program_map.get(row.training_program_id) if row.training_program_id else None
        # В БАЗЕ training_program_id и code — NOT NULL (модель говорит иначе:
        # на SQLite такая копия прошла бы, а на PostgreSQL упала). Строку без
        # программы или без кода не переносим и показываем числом.
        if new_program is None or not row.code:
            certs_skipped += 1
            continue
        session.add(
            TrainingCertificate(
                tenant_id=target_tenant_id,
                person_id=people_map[row.person_id],
                training_program_id=new_program,
                course_id=course_map.get(row.course_id) if row.course_id else None,
                session_id=session_map.get(row.session_id) if row.session_id else None,
                plan_id=None,
                # Файл удостоверения лежит в хранилище аутсорсера; копирование
                # объектов хранилища — отдельная работа, ссылку не тащим.
                file_id=None,
                **_fields(row, _CERTIFICATE_FIELDS),
                **_history_stamps(row),
            )
        )
        cert_count += 1
    await session.flush()
    counts["training_certificates"] = cert_count
    counts["training_certificates_skipped"] = certs_skipped

    return counts


async def count_left_behind(
    session: AsyncSession,
    *,
    source_tenant_id: str,
    source_company_id: str,
    people_map: dict[str, str],
) -> dict[str, int]:
    """Что этот перенос НЕ забрал — числом, а не молчанием.

    Ноль в отчёте читается как «этого не было», поэтому осознанно оставленное
    показывается отдельными счётчиками ``*_left_behind``: документы (нужны
    шаблоны и копирование объектов хранилища), допуски и журналы инструктажей,
    инциденты, «живой» рантайм обучения. Каждый из них — отдельная работа, и
    клиент должен видеть её объём, а не догадываться о ней.
    """

    from app.models.document import Document
    from app.models.training import TrainingEnrollment

    person_ids = list(people_map)
    counts: dict[str, int] = {}

    async def _count(model, *, by_person: bool) -> int:
        total = 0
        if by_person:
            for start in range(0, len(person_ids), _IN_CHUNK):
                chunk = person_ids[start : start + _IN_CHUNK]
                stmt = (
                    select(func.count())
                    .select_from(model)
                    .where(model.tenant_id == source_tenant_id, model.person_id.in_(chunk))
                )
                total += int((await session.execute(stmt)).scalar_one())
            return total
        stmt = (
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == source_tenant_id, model.company_id == source_company_id)
        )
        return int((await session.execute(stmt)).scalar_one())

    # Срез-16 забрал допуски, журналы инструктажей и происшествия — они больше
    # не «остались». Осталось ровно два класса, и оба по причине, а не по
    # недосмотру: документы (нужны шаблоны и копирование объектов хранилища) и
    # «живой» рантайм обучения (без модулей и тестов он не возобновляем).
    counts["documents_left_behind"] = await _count(Document, by_person=False)
    counts["training_enrollments_left_behind"] = await _count(TrainingEnrollment, by_person=True)
    return counts


# --- Срез-16: оставшаяся история клиента -------------------------------------
#
# Допуски, журналы инструктажей и происшествия. Все три висят на организации
# клиента или на его людях, то есть это его данные, а не инструменты
# аутсорсера. Ссылки на пользователей аутсорсера (автор записи) и на его
# пакеты документов обнуляются.

_PERMIT_FIELDS = ("permit_type", "issued_at", "valid_until", "status")

_JOURNAL_FIELDS = ("title", "journal_type", "started_at", "closed_at", "metadata_json")

_JOURNAL_ENTRY_FIELDS = ("entry_type", "entry_date", "instructor", "notes", "metadata_json")

_INCIDENT_FIELDS = (
    "title",
    "description",
    "incident_type",
    "occurred_at",
    "location_description",
    "severity",
    "status",
    "investigation_stage",
)

_INCIDENT_LOG_FIELDS = ("stage", "status", "message", "metadata_json")


async def copy_client_history(
    session: AsyncSession,
    *,
    source_tenant_id: str,
    source_company_id: str,
    target_tenant_id: str,
    company_map: dict[str, str],
    site_map: dict[str, str],
    position_map: dict[str, str],
    people_map: dict[str, str],
) -> dict[str, int]:
    """Скопировать допуски, журналы инструктажей и происшествия клиента."""

    from app.models.field_ops import Permit
    from app.models.incidents import Incident, IncidentLog, IncidentPerson
    from app.models.journals import Journal, JournalEntry

    counts: dict[str, int] = {}
    new_company_id = company_map.get(source_company_id)
    if new_company_id is None:
        return counts
    person_ids = list(people_map)

    # Допуски: висят на человеке, должность теперь переезжает вместе с
    # организацией — ссылка перевешивается, а не теряется.
    permits = await _live_rows(session, Permit, tenant_id=source_tenant_id, person_ids=person_ids)
    for row in permits:
        session.add(
            Permit(
                tenant_id=target_tenant_id,
                person_id=people_map[row.person_id],
                position_id=position_map.get(row.position_id) if row.position_id else None,
                **_fields(row, _PERMIT_FIELDS),
                **_history_stamps(row),
            )
        )
    await session.flush()
    counts["permits"] = len(permits)

    # Журналы инструктажей: сам журнал висит на организации, записи — на людях.
    journals = await _company_rows(
        session, Journal, tenant_id=source_tenant_id, company_id=source_company_id
    )
    journal_map: dict[str, str] = {}
    for row in journals:
        copy_row = Journal(
            tenant_id=target_tenant_id,
            company_id=new_company_id,
            **_fields(row, _JOURNAL_FIELDS),
            **_history_stamps(row),
        )
        session.add(copy_row)
        await session.flush()
        journal_map[row.id] = copy_row.id
    counts["journals"] = len(journal_map)

    entries = await _live_rows(
        session, JournalEntry, tenant_id=source_tenant_id, person_ids=person_ids
    )
    entries_copied = 0
    entries_skipped = 0
    for row in entries:
        new_journal = journal_map.get(row.journal_id)
        if new_journal is None:
            # Запись из журнала другой организации аутсорсера: journal_id
            # NOT NULL, подставить нечего — строка остаётся у аутсорсера.
            entries_skipped += 1
            continue
        session.add(
            JournalEntry(
                tenant_id=target_tenant_id,
                journal_id=new_journal,
                person_id=people_map[row.person_id],
                **_fields(row, _JOURNAL_ENTRY_FIELDS),
                **_history_stamps(row),
            )
        )
        entries_copied += 1
    await session.flush()
    counts["journal_entries"] = entries_copied
    counts["journal_entries_skipped"] = entries_skipped

    # Происшествия: висят на организации И на площадке (site_id NOT NULL),
    # поэтому переносятся только после площадок (срез-16 их и переносит).
    incidents = await _company_rows(
        session, Incident, tenant_id=source_tenant_id, company_id=source_company_id
    )
    incident_map: dict[str, str] = {}
    incidents_skipped = 0
    for row in incidents:
        new_site = site_map.get(row.site_id)
        if new_site is None:
            # Площадка чужой организации: site_id NOT NULL, подставить нечего.
            incidents_skipped += 1
            continue
        copy_row = Incident(
            tenant_id=target_tenant_id,
            company_id=new_company_id,
            site_id=new_site,
            # Пакет документов — инструмент аутсорсера, он не переносится.
            pack_id=None,
            **_fields(row, _INCIDENT_FIELDS),
            **_history_stamps(row),
        )
        session.add(copy_row)
        await session.flush()
        incident_map[row.id] = copy_row.id
    counts["incidents"] = len(incident_map)
    counts["incidents_skipped"] = incidents_skipped

    if incident_map:
        old_ids = list(incident_map)
        participants: list = []
        logs: list = []
        for start in range(0, len(old_ids), _IN_CHUNK):
            chunk = old_ids[start : start + _IN_CHUNK]
            participants.extend(
                (
                    await session.execute(
                        select(IncidentPerson).where(
                            IncidentPerson.tenant_id == source_tenant_id,
                            IncidentPerson.incident_id.in_(chunk),
                        )
                    )
                )
                .scalars()
                .all()
            )
            logs.extend(
                (
                    await session.execute(
                        select(IncidentLog).where(
                            IncidentLog.tenant_id == source_tenant_id,
                            IncidentLog.incident_id.in_(chunk),
                        )
                    )
                )
                .scalars()
                .all()
            )
        participants_copied = 0
        participants_skipped = 0
        for row in participants:
            new_person = people_map.get(row.person_id)
            if new_person is None:
                # Участник — обезличенный или удалённый человек: его копии в
                # новом арендаторе нет (разд. 66.2), связку не создаём.
                participants_skipped += 1
                continue
            session.add(
                IncidentPerson(
                    tenant_id=target_tenant_id,
                    incident_id=incident_map[row.incident_id],
                    person_id=new_person,
                    role=row.role,
                    **_history_stamps(row),
                )
            )
            participants_copied += 1
        for row in logs:
            session.add(
                IncidentLog(
                    tenant_id=target_tenant_id,
                    incident_id=incident_map[row.incident_id],
                    # Автор записи — пользователь аутсорсера.
                    author_id=None,
                    **_fields(row, _INCIDENT_LOG_FIELDS),
                    **_history_stamps(row),
                )
            )
        await session.flush()
        counts["incident_participants"] = participants_copied
        counts["incident_participants_skipped"] = participants_skipped
        counts["incident_logs"] = len(logs)

    return counts
