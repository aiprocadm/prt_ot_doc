"""Удаление данных из резервных копий: обязательство, а не обещание (OPS-72, разд. 72.3).

ЧТО БЫЛО. Акт офбординга честно перечислял, что удалено из живой базы и
хранилища файлов. Про резервные копии в нём не было ничего, и строка матрицы
держала остаток «удаление из бэкапов (организационная политика)».

ПОЧЕМУ ЭТО НЕ МЕЛОЧЬ. Клиент ушёл, данные из базы удалены, акт подписан — а
копии за последние N дней всё ещё содержат всё. Формально обязательство «данные
удалены» не исполнено, и никто не знает, КОГДА оно исполнится.

ЧЕГО ЗДЕСЬ СОЗНАТЕЛЬНО НЕТ. Кода, который «удаляет данные из резервных копий».
Выборочное удаление строки из копии технически невозможно без того, чтобы
сделать копию непригодной для восстановления. Написать такую функцию значило бы
соврать — ровно тот класс, за который платформа уже платила.

ЧТО ЕСТЬ ВМЕСТО ЭТОГО. Копии живут ограниченный срок и вытесняются ротацией.
Значит, у обязательства есть ВЫЧИСЛИМАЯ ДАТА исполнения: день удаления плюс
срок хранения копий. Эта дата записывается в акт, а незакрытые обязательства
можно перечислить и увидеть просроченные.

Таким образом «организационная политика» превращается в проверяемое
утверждение: срок хранения объявлен настройкой, дата посчитана, просрочка
видна. Закрывает обязательство человек — отметкой с указанием, кто и когда
подтвердил вытеснение копий.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

#: Сколько дней живут резервные копии. Значение объявляет тот, кто настраивал
#: резервное копирование: из кода это не видно, а угаданный срок, поданный как
#: измеренный, — худший из возможных ответов.
DEFAULT_RETENTION_DAYS = 35

STATE_PENDING = "pending"
STATE_DUE = "due"
STATE_OVERDUE = "overdue"
STATE_CLOSED = "closed"

#: Через сколько дней после наступления срока обязательство считается
#: просроченным. Неделя — чтобы обычная задержка дежурного не поднимала тревогу,
#: но забытое обязательство всплывало само.
OVERDUE_GRACE_DAYS = 7


@dataclass(frozen=True)
class BackupObligation:
    """Обязательство: к какой дате копии с данными арендатора вытеснятся."""

    tenant_id: str
    tenant_slug: str
    purged_at: datetime
    due_at: datetime
    retention_days: int
    state: str
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant_slug,
            "purged_at": self.purged_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "retention_days": self.retention_days,
            "state": self.state,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "confirmed_by": self.confirmed_by,
        }


def retention_days(settings) -> int:
    raw = getattr(settings, "backup_retention_days", None)
    try:
        value = int(raw) if raw is not None else DEFAULT_RETENTION_DAYS
    except (TypeError, ValueError):
        value = DEFAULT_RETENTION_DAYS
    return max(1, value)


def build_obligation(*, purged_at: datetime, settings) -> dict[str, object]:
    """Блок для акта: когда копии с данными этого арендатора вытеснятся."""

    days = retention_days(settings)
    due = _as_utc(purged_at) + timedelta(days=days)
    return {
        "retention_days": days,
        "due_at": due.isoformat(),
        "confirmed_at": None,
        "confirmed_by": None,
        "note": (
            "Выборочное удаление из резервных копий невозможно без того, чтобы "
            "сделать копию непригодной для восстановления. Копии вытесняются "
            "ротацией: к указанной дате данных арендатора в них не останется. "
            "После этой даты обязательство закрывает человек, подтверждая "
            "вытеснение."
        ),
    }


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str) and value:
        try:
            return _as_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


def obligation_state(block: dict, *, now: datetime) -> str:
    if block.get("confirmed_at"):
        return STATE_CLOSED
    due = _parse(block.get("due_at"))
    if due is None:
        # Акт старого образца, без блока: срок неизвестен, и молчать об этом
        # нельзя — иначе обязательство просто исчезнет из виду.
        return STATE_OVERDUE
    if now < due:
        return STATE_PENDING
    if now < due + timedelta(days=OVERDUE_GRACE_DAYS):
        return STATE_DUE
    return STATE_OVERDUE


def collect(records, *, now: datetime | None = None) -> list[BackupObligation]:
    """Обязательства по всем удалённым арендаторам.

    ``records`` — записи офбординга со статусом ``purged`` и полем ``purge_act``.
    """

    moment = now or datetime.now(tz=timezone.utc)
    out: list[BackupObligation] = []
    for record in records:
        if getattr(record, "status", None) != "purged":
            continue
        act = getattr(record, "purge_act", None) or {}
        block = act.get("backup_purge") or {}
        purged_at = _parse(act.get("executed_at")) or moment
        due = _parse(block.get("due_at")) or purged_at
        out.append(
            BackupObligation(
                tenant_id=str(getattr(record, "tenant_id", "")),
                tenant_slug=str(getattr(record, "tenant_slug", "") or ""),
                purged_at=purged_at,
                due_at=due,
                retention_days=int(block.get("retention_days") or 0),
                state=obligation_state(block, now=moment),
                confirmed_at=_parse(block.get("confirmed_at")),
                confirmed_by=block.get("confirmed_by") or None,
            )
        )
    return out


def summarize(obligations: list[BackupObligation]) -> dict[str, object]:
    by_state: dict[str, int] = {}
    for item in obligations:
        by_state[item.state] = by_state.get(item.state, 0) + 1
    return {
        "total": len(obligations),
        "pending": by_state.get(STATE_PENDING, 0),
        "due": by_state.get(STATE_DUE, 0),
        "overdue": by_state.get(STATE_OVERDUE, 0),
        "closed": by_state.get(STATE_CLOSED, 0),
        # В выдаче только то, на что надо смотреть: закрытые и ещё не наступившие
        # не шумят, иначе список перестанут читать.
        "items": [
            item.as_dict() for item in obligations if item.state in (STATE_DUE, STATE_OVERDUE)
        ],
    }


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "OVERDUE_GRACE_DAYS",
    "STATE_CLOSED",
    "STATE_DUE",
    "STATE_OVERDUE",
    "STATE_PENDING",
    "BackupObligation",
    "build_obligation",
    "collect",
    "obligation_state",
    "retention_days",
    "summarize",
]
