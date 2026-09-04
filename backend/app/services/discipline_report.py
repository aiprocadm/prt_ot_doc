"""Авто-отчёт о состоянии по дисциплинам для арендатора (Доп. №1 разд. 57.4).

ТЗ: «авто-отчёты о состоянии по каждой дисциплине (для клиента при аренде /
для заказчика при аутсорсинге)». Для заказчика при аутсорсинге такой отчёт
уже есть — авто-аудит клиента (BIZ-51 срез-7). Для клиента при аренде, то
есть для самого арендатора, не было ничего: разрез «по дисциплинам» на
управленческом дашборде (срез-48) отвечает про «сейчас», а «что было неделю
назад и куда движемся» — нет. Здесь тот же разрез сохраняется НА ДАТУ и
сравнивается с прошлым отчётом (срез-50).

## Решения

**1. Числа — ТЕ ЖЕ, что на дашборде, а не свой расчёт.** Строки отчёта
берутся из ``compute_breakdown(..., "discipline")``: происшествия по разметке,
просрочки формулой Центра внимания, «не считается» — ``None``, а не ноль.
Второй расчёт рядом разошёлся бы с дашбордом на первой правке, и директор
читал бы в отчёте одно, а на экране — другое.

**2. Отчёт всегда о трёх вещах, даже когда ответ «ничего».** Что по
дисциплинам, что изменилось, что делать. «Нарушений не найдено» и «действий
не требуется» — содержание отчёта, а не повод его не писать: молчание
неотличимо от неработающего тика (довод отчёта авто-аудита).

**3. Один отчёт на дату.** Тик ретраится, а «собрать сейчас» можно нажать
после тика — второй отчёт за ту же дату превратил бы динамику в шум.

**4. «Хуже/лучше» — только к предыдущему отчёту, и его дата названа.** Первый
отчёт честно говорит «сравнивать не с чем», а не рисует ноль как «было».

**5. Новый отчёт сам находит читателя (срез-51).** Сборка и доставка — один
шаг: отчёт, о котором никому не сказали, «авто-отчётом для клиента» не
является. Кому и как — в ``discipline_report_delivery``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discipline_reports import DisciplineStatusReport
from app.modules.analytics.breakdown import NO_DISCIPLINE_BUCKET_ID, compute_breakdown
from app.services.discipline_report_delivery import deliver_discipline_report

__all__ = [
    "REPORT_PERIOD_DAYS",
    "DisciplineReportContent",
    "DisciplineReportOutcome",
    "build_discipline_report",
    "latest_report",
    "list_reports",
    "run_discipline_report",
]

#: Неделя — как у авто-аудита клиента (ТЗ: «напр. еженедельно»).
REPORT_PERIOD_DAYS = 7

_INCIDENTS = ("происшествие", "происшествия", "происшествий")
_OVERDUE = ("просрочка", "просрочки", "просрочек")


@dataclass(frozen=True)
class DisciplineReportContent:
    total_issues: int
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DisciplineReportOutcome:
    """Честный итог: создан новый отчёт или за эту дату уже был.

    ``notified`` — сколько уведомлений ушло; у повторного запуска ноль:
    отчёт тот же, второй раз о нём не говорят.
    """

    created: bool
    report: DisciplineStatusReport
    notified: int = 0


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    tail = abs(count) % 100
    unit = tail % 10
    if 11 <= tail <= 19 or unit == 0 or unit >= 5:
        word = forms[2]
    elif unit == 1:
        word = forms[0]
    else:
        word = forms[1]
    return f"{count} {word}"


def _fmt(value: str | date) -> str:
    day = date.fromisoformat(value) if isinstance(value, str) else value
    return day.strftime("%d.%m.%Y")


def _describe(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    if row["incidents_open"]:
        parts.append(_plural(int(row["incidents_open"]), _INCIDENTS))
    if row["overdue_items"]:
        parts.append(_plural(int(row["overdue_items"]), _OVERDUE))
    return ", ".join(parts)


def _dynamics(delta: int | None, previous_total: int | None, previous_end: str | None) -> str:
    if delta is None or previous_total is None or previous_end is None:
        return "первый отчёт — сравнивать не с чем"
    if delta > 0:
        movement = f"хуже на {delta}"
    elif delta < 0:
        movement = f"лучше на {-delta}"
    else:
        movement = "без изменений"
    return f"в отчёте за {_fmt(previous_end)} было {previous_total}, {movement}"


def build_discipline_report(
    *,
    period_start: date,
    period_end: date,
    rows: Sequence[Mapping[str, Any]],
    previous: Mapping[str, Any] | None,
    not_applicable: str | None = None,
) -> DisciplineReportContent:
    """Собрать отчёт из строк разреза «по дисциплинам» и прошлого отчёта.

    ``rows`` — ``items`` из ``compute_breakdown``: худшее сверху, строка
    ``id == ""`` — неразмеченные происшествия. ``previous`` — ``payload``
    прошлого отчёта или ``None``. ``not_applicable`` — фраза разреза про
    дисциплины вне редакции (срез-56): в отчёте она звучит отдельным
    предложением, чтобы семь строк вместо восьми не читались как недоделка.
    Правила чистые, без базы.
    """

    previous = previous or {}
    previous_rows = {row["discipline"]: row for row in previous.get("rows", [])}
    previous_end = (previous.get("period") or {}).get("end")

    report_rows: list[dict[str, Any]] = []
    unmarked = 0
    for row in rows:
        if row["id"] == NO_DISCIPLINE_BUCKET_ID:
            unmarked = int(row["incidents_open"] or 0)
            continue
        earlier = previous_rows.get(row["id"])
        previous_total = int(earlier["total_issues"]) if earlier else None
        total = int(row["total_issues"] or 0)
        report_rows.append(
            {
                "discipline": row["id"],
                "title": row["name"],
                "incidents_open": int(row["incidents_open"] or 0),
                # None здесь — «не считается», и он должен доехать до отчёта
                # таким же: ноль читался бы как «нарушений нет».
                "overdue_items": row["overdue_items"],
                "total_issues": total,
                "previous_total_issues": previous_total,
                "delta": total - previous_total if previous_total is not None else None,
            }
        )

    incidents_open = sum(r["incidents_open"] for r in report_rows) + unmarked
    overdue_items = sum(int(r["overdue_items"] or 0) for r in report_rows)
    total_issues = sum(r["total_issues"] for r in report_rows) + unmarked
    previous_total = (previous.get("totals") or {}).get("total_issues")
    previous_total = int(previous_total) if previous_total is not None else None
    delta = total_issues - previous_total if previous_total is not None else None

    worst = next((r for r in report_rows if r["total_issues"] > 0), None)
    actions = [f"{r['title']}: {_describe(r)}" for r in report_rows if r["total_issues"] > 0]
    if unmarked:
        actions.append(
            f"Разметить дисциплиной в реестре происшествий: {_plural(unmarked, _INCIDENTS)}"
        )

    summary_parts = [
        (
            f"Состояние на {_fmt(period_end)}: открытых происшествий {incidents_open}, "
            f"просрочек по учтённым источникам {overdue_items} — всего {total_issues} "
            f"({_dynamics(delta, previous_total, previous_end)})."
        ),
        (
            f"Хуже всего: {worst['title']} — {_describe(worst)}."
            if worst
            else "Нарушений по учтённым источникам не найдено."
        ),
    ]
    if unmarked:
        summary_parts.append(
            f"Не размечено дисциплиной: {_plural(unmarked, _INCIDENTS)} — "
            "ни один контур их не видит."
        )
    if not_applicable:
        summary_parts.append(f"{not_applicable}.")
    summary_parts.append(
        "Что нужно сделать: " + "; ".join(actions) + "." if actions else "Действий не требуется."
    )

    payload: dict[str, Any] = {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "rows": report_rows,
        "unmarked_incidents": unmarked,
        "totals": {
            "incidents_open": incidents_open,
            "overdue_items": overdue_items,
            "total_issues": total_issues,
            "previous_total_issues": previous_total,
            "delta": delta,
        },
        "previous_period_end": previous_end,
        "worst": ({"discipline": worst["discipline"], "title": worst["title"]} if worst else None),
        "actions": actions,
        "not_applicable": not_applicable,
    }
    return DisciplineReportContent(
        total_issues=total_issues, summary=" ".join(summary_parts), payload=payload
    )


async def latest_report(
    session: AsyncSession, tenant_id: str, *, before: date | None = None
) -> DisciplineStatusReport | None:
    stmt = (
        select(DisciplineStatusReport)
        .where(DisciplineStatusReport.tenant_id == tenant_id)
        .order_by(
            DisciplineStatusReport.period_end.desc(), DisciplineStatusReport.created_at.desc()
        )
        .limit(1)
    )
    if before is not None:
        stmt = stmt.where(DisciplineStatusReport.period_end < before)
    return (await session.execute(stmt)).scalars().first()


async def _report_for_date(
    session: AsyncSession, tenant_id: str, period_end: date
) -> DisciplineStatusReport | None:
    return (
        (
            await session.execute(
                select(DisciplineStatusReport)
                .where(
                    DisciplineStatusReport.tenant_id == tenant_id,
                    DisciplineStatusReport.period_end == period_end,
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def run_discipline_report(
    session: AsyncSession, tenant_id: str, *, today: date | None = None
) -> DisciplineReportOutcome:
    """Собрать отчёт на дату. Ничего не коммитит — транзакцией владеет вызывающий."""

    today = today or datetime.now(tz=timezone.utc).date()
    existing = await _report_for_date(session, tenant_id, today)
    if existing is not None:
        return DisciplineReportOutcome(created=False, report=existing)

    breakdown = await compute_breakdown(session, tenant_id, "discipline")
    previous = await latest_report(session, tenant_id, before=today)
    content = build_discipline_report(
        period_start=today - timedelta(days=REPORT_PERIOD_DAYS),
        period_end=today,
        rows=breakdown["items"],
        previous=previous.payload if previous is not None else None,
        not_applicable=breakdown.get("not_applicable"),
    )
    report = DisciplineStatusReport(
        tenant_id=tenant_id,
        period_start=today - timedelta(days=REPORT_PERIOD_DAYS),
        period_end=today,
        total_issues=content.total_issues,
        summary=content.summary,
        payload=content.payload,
    )
    session.add(report)
    await session.flush()
    notified = await deliver_discipline_report(session, report)
    return DisciplineReportOutcome(created=True, report=report, notified=notified)


async def list_reports(
    session: AsyncSession, tenant_id: str, *, limit: int, offset: int = 0
) -> tuple[list[DisciplineStatusReport], int]:
    """Отчёты арендатора: свежие сверху, с общим числом."""

    where = (DisciplineStatusReport.tenant_id == tenant_id,)
    total = int((await session.execute(select(func.count()).where(*where))).scalar_one() or 0)
    rows = (
        (
            await session.execute(
                select(DisciplineStatusReport)
                .where(*where)
                .order_by(
                    DisciplineStatusReport.period_end.desc(),
                    DisciplineStatusReport.created_at.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total
