"""Числа дисциплин по ЛЮБОМУ набору людей (BIZ-54-57 срез-3).

Правила счёта родились в светофоре клиента (BIZ-51 срез-5) и считали ровно по
одной организации. Карточка площадки 360° (Доп. №1 разд. 57.1) показывает тот
же светофор, но по людям одной площадки — и второй экземпляр этих правил
разошёлся бы с первым: «медосмотр закрыт» на карточке клиента и на карточке
площадки стало бы означать разное. Поэтому счёт вынесен сюда и принимает
готовый список людей, а откуда он взялся — дело вызывающего.

## Решения о покрытии (важно не переиграть молча)

- **Экзамен без вида закрывает любую норму.** ``MedicalExam.exam_kind``
  появился позже самой таблицы, у старых записей он пуст. Строгое сравнение
  объявило бы разрыв каждому со старой картотекой — ложно-красный светофор,
  которому перестают верить.
- **Норма СИЗ закрыта, когда активных выдач НЕ МЕНЬШЕ нормы.** Норма задаёт
  количество (две пары перчаток); одна активная выдача из двух — разрыв. Имена
  сравниваются без учёта регистра (выдачи заводились и руками).
- **«Истекает» считается только у закрытых норм**: у разрыва истекать нечему,
  он уже красный.

Выборки помещаются в память намеренно: честная склейка пар «сотрудник × норма»
в Python читается и проверяется лучше, чем один нечитаемый мега-JOIN.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import DisciplineCounts
from app.core.feature_flags import as_utc
from app.models.master_data import Person
from app.models.medical import MedicalExam, MedicalNorm
from app.models.ppe import PPEIssue, PPENorm
from app.models.training import TrainingEnrollment

__all__ = ["DisciplineNumbers", "collect_people_numbers"]

#: Статусы обучения, у которых бывает срок (как в «Центре внимания»).
_ACTIVE_TRAINING_STATUSES = ("assigned", "in_progress")


@dataclass(frozen=True)
class DisciplineNumbers:
    """Числа трёх измеримых дисциплин по набору людей."""

    medical: DisciplineCounts
    ppe: DisciplineCounts
    training_overdue: int


def _medical_counts(
    people: list[Person],
    norms_by_position: dict[str, set],
    exams_by_person: dict[str, list[MedicalExam]],
    *,
    today: date,
    horizon: timedelta,
) -> DisciplineCounts:
    required = missing = lapsed = expiring = 0
    deadline = today + horizon
    for person in people:
        kinds = norms_by_position.get(str(person.position_id or ""), set())
        exams = exams_by_person.get(str(person.id), [])
        for kind in kinds:
            required += 1
            # Экзамен без вида закрывает любую норму (решение в docstring).
            matching = [e for e in exams if e.exam_kind is None or e.exam_kind == kind]
            valid = [e for e in matching if e.valid_until >= today]
            if valid:
                if max(e.valid_until for e in valid) < deadline:
                    expiring += 1
            elif matching:
                lapsed += 1
            else:
                missing += 1
    return DisciplineCounts(
        required=required, missing=missing, lapsed=lapsed, expiring=expiring
    )


def _ppe_counts(
    people: list[Person],
    norms_by_position: dict[str, list[PPENorm]],
    issues_by_person: dict[str, list[PPEIssue]],
    *,
    now: datetime,
    horizon: timedelta,
) -> DisciplineCounts:
    required = missing = lapsed = expiring = 0
    deadline = now + horizon
    for person in people:
        norms = norms_by_position.get(str(person.position_id or ""), [])
        issues = issues_by_person.get(str(person.id), [])
        for norm in norms:
            required += 1
            item = (norm.item_name or "").strip().lower()
            same_item = [
                i for i in issues if (i.item_name or "").strip().lower() == item
            ]
            # ``as_utc`` обязателен: SQLite отдаёт expires_at без зоны, и
            # сравнение с aware-now падало бы ровно в момент показа светофора.
            active = [
                i
                for i in same_item
                if i.returned_at is None
                and (i.expires_at is None or (as_utc(i.expires_at) or now) >= now)
            ]
            if len(active) >= max(int(norm.quantity or 1), 1):
                if any(
                    i.expires_at is not None
                    and (as_utc(i.expires_at) or deadline) < deadline
                    for i in active
                ):
                    expiring += 1
            elif same_item:
                lapsed += 1
            else:
                missing += 1
    return DisciplineCounts(
        required=required, missing=missing, lapsed=lapsed, expiring=expiring
    )


async def collect_people_numbers(
    session: AsyncSession,
    *,
    tenant_id: str,
    people: list[Person],
    today: date | None = None,
    now: datetime | None = None,
    horizon_days: int = 30,
) -> DisciplineNumbers:
    """Собрать числа трёх измеримых дисциплин по готовому набору людей."""

    today = today or datetime.now(tz=timezone.utc).date()
    now = now or datetime.now(tz=timezone.utc)
    horizon = timedelta(days=horizon_days)

    if not people:
        return DisciplineNumbers(DisciplineCounts(), DisciplineCounts(), 0)

    person_ids = [str(p.id) for p in people]
    position_ids = {str(p.position_id) for p in people if p.position_id}

    med_norms: dict[str, set] = defaultdict(set)
    ppe_norms: dict[str, list[PPENorm]] = defaultdict(list)
    if position_ids:
        for norm in (
            (
                await session.execute(
                    select(MedicalNorm).where(
                        MedicalNorm.tenant_id == tenant_id,
                        MedicalNorm.position_id.in_(list(position_ids)),
                    )
                )
            )
            .scalars()
            .all()
        ):
            med_norms[str(norm.position_id)].add(norm.exam_kind)
        for norm in (
            (
                await session.execute(
                    select(PPENorm).where(
                        PPENorm.tenant_id == tenant_id,
                        PPENorm.position_id.in_(list(position_ids)),
                    )
                )
            )
            .scalars()
            .all()
        ):
            ppe_norms[str(norm.position_id)].append(norm)

    exams_by_person: dict[str, list[MedicalExam]] = defaultdict(list)
    if med_norms:
        for exam in (
            (
                await session.execute(
                    select(MedicalExam).where(
                        MedicalExam.tenant_id == tenant_id,
                        MedicalExam.person_id.in_(person_ids),
                        MedicalExam.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            exams_by_person[str(exam.person_id)].append(exam)

    issues_by_person: dict[str, list[PPEIssue]] = defaultdict(list)
    if ppe_norms:
        for issue in (
            (
                await session.execute(
                    select(PPEIssue).where(
                        PPEIssue.tenant_id == tenant_id,
                        PPEIssue.person_id.in_(person_ids),
                        PPEIssue.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            issues_by_person[str(issue.person_id)].append(issue)

    training_overdue = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TrainingEnrollment)
                .where(
                    TrainingEnrollment.tenant_id == tenant_id,
                    TrainingEnrollment.person_id.in_(person_ids),
                    TrainingEnrollment.deleted_at.is_(None),
                    TrainingEnrollment.status.in_(_ACTIVE_TRAINING_STATUSES),
                    TrainingEnrollment.due_at.is_not(None),
                    TrainingEnrollment.due_at < now,
                )
            )
        ).scalar_one()
        or 0
    )

    return DisciplineNumbers(
        medical=_medical_counts(
            people, med_norms, exams_by_person, today=today, horizon=horizon
        ),
        ppe=_ppe_counts(people, ppe_norms, issues_by_person, now=now, horizon=horizon),
        training_overdue=training_overdue,
    )
