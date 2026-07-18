# P10-01 Комитеты срез-2 — ядро заседаний — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в модуль комитетов (P10-01 срез-1) ядро заседаний: присутствие + кворум-гейт на проведение, голосование по решениям с подсчётом, авто-нумерацию и журнал протоколов, и write-UI, делающий страницу срез-1 полностью рабочей.

**Architecture:** Аддитивно к срез-1. Миграция `cmt02` (2 таблицы attendance/votes, enum `votechoice`, 6 nullable-колонок на `committee_meeting` с иммутабельным снапшотом кворума). Чистые правила расширяют `lifecycle.py`; итог голосования вычисляется на лету в проекции. RBAC остаётся admin-only на роутере.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / pytest-asyncio · React 18 / Vite / TS / vitest.

**Спека:** `docs/superpowers/specs/2026-07-14-p10-01-committees-srez2-proceedings-design.md`.

**Ветка:** `feat/p10-01-committees-srez2-proceedings` (worktree создаётся при исполнении).

**Операционка (из прошлых срезов, обязательно):** pytest — только PowerShell, ОДИН прогон, `timeout 600000`, батчи ≤5 файлов (cold import >120s). `git -C <абсолютный путь>`. Полный vitest не параллелить с pytest. Красный полного vitest перепроверять повтором (контеншн-флейк). Enum-миграции — `postgresql.ENUM(create_type=False)` + явный `.create/.drop`, не `sa.Enum`.

---

## File Structure

**Backend (modify):**
- `backend/app/models/committees.py` — +`VoteChoice`, +`CommitteeMeetingAttendance`, +`CommitteeDecisionVote`, +6 колонок на `CommitteeMeeting`.
- `backend/app/domains/committees/lifecycle.py` — +`is_quorum`/`tally_votes`/`DecisionOutcome`/`decision_outcome`/`next_protocol_seq`/`validate_hold`/`ensure_can_vote`.
- `backend/app/domains/committees/service.py` — +`vote_summary`/`decision_to_protocol`; расширить `build_protocol`.
- `backend/app/schemas/committees.py` — +attendance/vote/journal схемы; расширить `MeetingRead`/`ProtocolDecision`.
- `backend/app/api/routes/committees.py` — +5 роутов, расширить `update_meeting` и `get_protocol`.
- `backend/app/services/demo_bootstrap.py` — расширить `_seed_committees_demo`.

**Backend (create):**
- `backend/app/migrations/versions/20260714_cmt02_committee_proceedings.py`.

**Backend tests (create):**
- `backend/tests/test_committees_srez2_lifecycle.py` (unit).
- `backend/tests/test_committees_srez2_api.py` (contract, mocked session).
- `backend/tests/test_committees_srez2_service.py` (проекции).

**Frontend (modify):**
- `frontend/src/api/committees.ts` — +типы/методы.
- `frontend/src/pages/committees/CommitteesPage.tsx` — write-UI + ядро заседаний.

**Frontend tests (create):**
- `frontend/src/api/committees.srez2.test.ts`.
- `frontend/src/pages/committees/CommitteesPage.srez2.test.tsx`.

---

## Task 1: Модель + миграция `cmt02`

**Files:**
- Modify: `backend/app/models/committees.py`
- Create: `backend/app/migrations/versions/20260714_cmt02_committee_proceedings.py`

- [ ] **Step 1: Расширить модель.** В `backend/app/models/committees.py`:

Добавить импорт `Enum`? Нет — используется `native_enum`. После `class DecisionTaskStatus` добавить:

```python
class VoteChoice(str, enum.Enum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"
```

В `class CommitteeMeeting` добавить колонки (после `status`):

```python
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    protocol_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    members_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    present_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quorum_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "committee_id",
            "protocol_year",
            "protocol_seq",
            name="uq_committee_protocol_no",
        ),
    )
```

(Констрейнт — полный UniqueConstraint на модели; частичность `WHERE protocol_seq IS NOT NULL` живёт в миграции как partial index. На модели допустим полный констрейнт: множественные NULL не конфликтуют в PG.)

В конец файла добавить две таблицы:

```python
class CommitteeMeetingAttendance(TenantBaseModel):
    __tablename__ = "committee_meeting_attendance"

    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_meeting.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "meeting_id", "person_id", name="uq_committee_attendance"
        ),
    )


class CommitteeDecisionVote(TenantBaseModel):
    __tablename__ = "committee_decision_vote"

    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_decision.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    choice: Mapped[VoteChoice] = mapped_column(
        native_enum(VoteChoice, name="votechoice"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "decision_id", "person_id", name="uq_committee_vote"),
    )
```

- [ ] **Step 2: Написать миграцию.** Create `backend/app/migrations/versions/20260714_cmt02_committee_proceedings.py`:

```python
"""cmt02: committee proceedings — attendance, votes, meeting protocol snapshot.

Additive (P10-01 срез-2, TZ B.17). Adds:
- enum votechoice + committee_decision_vote
- committee_meeting_attendance
- committee_meeting: held_at, protocol_seq/year, members_total, present_count, quorum_met
- partial unique index on protocol number (per committee/year)

Chains off rb01. Honest downgrade drops in reverse (child→parent) order.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260714_cmt02_committee_proceedings"
down_revision = "20260710_rb01_report_definition"
branch_labels = None
depends_on = None

_VOTE_CHOICE = postgresql.ENUM(
    "for", "against", "abstain", name="votechoice", create_type=False
)


def _common(*extra: sa.Column) -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *extra,
    ]


def upgrade() -> None:
    bind = op.get_bind()
    _VOTE_CHOICE.create(bind, checkfirst=True)

    op.add_column(
        "committee_meeting", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("committee_meeting", sa.Column("protocol_seq", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("protocol_year", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("members_total", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("present_count", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("quorum_met", sa.Boolean(), nullable=True))
    op.create_index(
        "uq_committee_protocol_no",
        "committee_meeting",
        ["tenant_id", "committee_id", "protocol_year", "protocol_seq"],
        unique=True,
        postgresql_where=sa.text("protocol_seq IS NOT NULL"),
    )

    op.create_table(
        "committee_meeting_attendance",
        *_common(
            sa.Column(
                "meeting_id",
                sa.String(length=36),
                sa.ForeignKey("committee_meeting.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "person_id",
                sa.String(length=36),
                sa.ForeignKey("person.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.true()),
        ),
        sa.UniqueConstraint(
            "tenant_id", "meeting_id", "person_id", name="uq_committee_attendance"
        ),
    )
    op.create_table(
        "committee_decision_vote",
        *_common(
            sa.Column(
                "decision_id",
                sa.String(length=36),
                sa.ForeignKey("committee_decision.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "person_id",
                sa.String(length=36),
                sa.ForeignKey("person.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            sa.Column("choice", _VOTE_CHOICE, nullable=False),
        ),
        sa.UniqueConstraint("tenant_id", "decision_id", "person_id", name="uq_committee_vote"),
    )


def downgrade() -> None:
    op.drop_table("committee_decision_vote")
    op.drop_table("committee_meeting_attendance")
    op.drop_index("uq_committee_protocol_no", table_name="committee_meeting")
    for col in ("quorum_met", "present_count", "members_total", "protocol_year", "protocol_seq", "held_at"):
        op.drop_column("committee_meeting", col)
    bind = op.get_bind()
    _VOTE_CHOICE.drop(bind, checkfirst=True)
```

- [ ] **Step 3: Проверить импорт модели.** Run (PowerShell):
`$env:PYTHONPATH="backend"; python -c "from app.models.committees import VoteChoice, CommitteeMeetingAttendance, CommitteeDecisionVote; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit.**
`git add backend/app/models/committees.py backend/app/migrations/versions/20260714_cmt02_committee_proceedings.py && git commit -m "feat(p10-01): cmt02 model+migration — attendance, votes, protocol snapshot"`

- [ ] **Step 5: PG16-гейт (см. Task 8, шаг db-only) запускается контроллером в фоне после Task 1** — round-trip up/down миграции. Не блокирует последующие backend-задачи (они на SQLite).

---

## Task 2: Чистые правила (`lifecycle.py`) — TDD

**Files:**
- Modify: `backend/app/domains/committees/lifecycle.py`
- Test: `backend/tests/test_committees_srez2_lifecycle.py`

- [ ] **Step 1: Написать падающий тест.** Create `backend/tests/test_committees_srez2_lifecycle.py`:

```python
"""Unit: committees срез-2 pure rules (quorum, tally, outcome, numbering, gates)."""
from __future__ import annotations

import pytest

from app.domains.committees.lifecycle import (
    DecisionOutcome,
    MeetingTransitionError,
    decision_outcome,
    ensure_can_vote,
    is_quorum,
    next_protocol_seq,
    tally_votes,
    validate_hold,
)
from app.models.committees import MeetingStatus, VoteChoice


@pytest.mark.parametrize(
    "total,present,expected",
    [(0, 0, False), (4, 2, False), (4, 3, True), (4, 4, True), (3, 2, True), (1, 1, True)],
)
def test_is_quorum(total, present, expected):
    assert is_quorum(total, present) is expected


def test_tally_votes():
    votes = [VoteChoice.FOR, VoteChoice.FOR, VoteChoice.AGAINST, VoteChoice.ABSTAIN]
    assert tally_votes(votes) == (2, 1, 1)


def test_tally_votes_empty():
    assert tally_votes([]) == (0, 0, 0)


@pytest.mark.parametrize(
    "for_,against,expected",
    [(2, 1, DecisionOutcome.CARRIED), (1, 1, DecisionOutcome.REJECTED), (0, 0, DecisionOutcome.REJECTED), (0, 3, DecisionOutcome.REJECTED)],
)
def test_decision_outcome(for_, against, expected):
    assert decision_outcome(for_, against) is expected


def test_next_protocol_seq():
    assert next_protocol_seq([]) == 1
    assert next_protocol_seq([1, 2]) == 3
    assert next_protocol_seq([2, 5, 3]) == 6


def test_validate_hold_ok():
    validate_hold(MeetingStatus.PLANNED, quorum_met=True)  # no raise


def test_validate_hold_no_quorum():
    with pytest.raises(MeetingTransitionError):
        validate_hold(MeetingStatus.PLANNED, quorum_met=False)


def test_validate_hold_bad_transition():
    with pytest.raises(MeetingTransitionError):
        validate_hold(MeetingStatus.HELD, quorum_met=True)


def test_ensure_can_vote():
    ensure_can_vote(MeetingStatus.HELD)  # no raise
    with pytest.raises(MeetingTransitionError):
        ensure_can_vote(MeetingStatus.PLANNED)
```

- [ ] **Step 2: Прогнать — должен падать.** Run (PowerShell, timeout 600000):
`$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_committees_srez2_lifecycle.py -q`
Expected: FAIL (ImportError — функций нет).

- [ ] **Step 3: Реализовать.** В `backend/app/domains/committees/lifecycle.py` добавить импорт `VoteChoice` и `enum`, затем функции:

```python
import enum
from collections.abc import Iterable

from app.models.committees import DecisionTaskStatus, MeetingStatus, VoteChoice


class DecisionOutcome(str, enum.Enum):
    CARRIED = "carried"
    REJECTED = "rejected"


def is_quorum(members_total: int, present_count: int) -> bool:
    """Quorum = strictly more than half of active members present."""
    if members_total <= 0:
        return False
    return present_count * 2 > members_total


def tally_votes(choices: Iterable[VoteChoice]) -> tuple[int, int, int]:
    """Return (for, against, abstain) counts."""
    votes_for = votes_against = votes_abstain = 0
    for c in choices:
        if c is VoteChoice.FOR:
            votes_for += 1
        elif c is VoteChoice.AGAINST:
            votes_against += 1
        else:
            votes_abstain += 1
    return votes_for, votes_against, votes_abstain


def decision_outcome(votes_for: int, votes_against: int) -> DecisionOutcome:
    """Carried iff for > against (tie → rejected; abstentions excluded)."""
    return DecisionOutcome.CARRIED if votes_for > votes_against else DecisionOutcome.REJECTED


def next_protocol_seq(existing_seqs: Iterable[int]) -> int:
    """Next sequential protocol number within a committee/year."""
    return max(existing_seqs, default=0) + 1


def validate_hold(current: MeetingStatus, quorum_met: bool) -> None:
    """Holding a meeting requires a legal transition AND quorum."""
    validate_meeting_transition(current, MeetingStatus.HELD)
    if not quorum_met:
        raise MeetingTransitionError("Cannot hold meeting without quorum")


def ensure_can_vote(meeting_status: MeetingStatus) -> None:
    if meeting_status is not MeetingStatus.HELD:
        raise MeetingTransitionError(
            f"Voting allowed only on a held meeting (status={meeting_status.value})"
        )
```

- [ ] **Step 4: Прогнать — должен пройти.** Run: `$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_committees_srez2_lifecycle.py -q`
Expected: PASS (все ~18 кейсов). Затем `ruff check backend/app/domains/committees/lifecycle.py && black --check backend/app/domains/committees/lifecycle.py backend/tests/test_committees_srez2_lifecycle.py`.

- [ ] **Step 5: Commit.** `git add backend/app/domains/committees/lifecycle.py backend/tests/test_committees_srez2_lifecycle.py && git commit -m "feat(p10-01): committees срез-2 pure rules (quorum/tally/outcome/numbering)"`

---

## Task 3: Схемы + service-проекции — TDD

**Files:**
- Modify: `backend/app/schemas/committees.py`, `backend/app/domains/committees/service.py`
- Test: `backend/tests/test_committees_srez2_service.py`

- [ ] **Step 1: Добавить схемы.** В `backend/app/schemas/committees.py` добавить импорт `VoteChoice` и после существующих схем:

```python
from app.models.committees import (
    CommitteeKind,
    CommitteeMemberRole,
    DecisionTaskStatus,
    MeetingStatus,
    VoteChoice,
)


# --- Attendance ---
class AttendanceItem(BaseSchema):
    person_id: str
    present: bool = True


class AttendanceBulkUpdate(BaseSchema):
    items: list[AttendanceItem]


class AttendanceRead(BaseSchema):
    id: str
    meeting_id: str
    person_id: str
    present: bool


# --- Votes ---
class VoteCreate(BaseSchema):
    person_id: str
    choice: VoteChoice


class VoteRead(BaseSchema):
    id: str
    decision_id: str
    person_id: str
    choice: VoteChoice


class DecisionVoteSummary(BaseSchema):
    decision_id: str
    votes_for: int
    votes_against: int
    votes_abstain: int
    outcome: str  # "carried" | "rejected"
    votes: list[VoteRead]


# --- Protocol journal ---
class ProtocolJournalItem(BaseSchema):
    meeting_id: str
    committee_id: str
    committee_name: str
    protocol_no: str  # "N/YYYY"
    held_at: datetime
    members_total: int | None
    present_count: int | None
    decisions_count: int


class ProtocolJournalPage(BaseSchema):
    items: list[ProtocolJournalItem]
    total: int
    limit: int
    offset: int
```

Расширить `MeetingRead` (добавить поля + computed `protocol_no`):

```python
class MeetingRead(BaseSchema):
    id: str
    committee_id: str
    scheduled_at: datetime
    location: str | None
    status: MeetingStatus
    held_at: datetime | None = None
    protocol_seq: int | None = None
    protocol_year: int | None = None
    members_total: int | None = None
    present_count: int | None = None
    quorum_met: bool | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def protocol_no(self) -> str | None:
        if self.protocol_seq is None or self.protocol_year is None:
            return None
        return f"{self.protocol_seq}/{self.protocol_year}"
```

(BaseSchema — pydantic v2; `@property` не сериализуется по умолчанию. Чтобы `protocol_no` попал в JSON — использовать `@computed_field`. Проверить как в проекте: `grep -rn "computed_field" backend/app/schemas | head`. Если используется — заменить `@property` на `@computed_field @property`. Иначе добавить поле `protocol_no: str | None = None` и заполнять в роуте/сервисе.)

Расширить `ProtocolDecision`:

```python
class ProtocolDecision(BaseSchema):
    decision: DecisionRead
    tasks: list[DecisionTaskRead]
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    outcome: str | None = None  # "carried" | "rejected" | None (no votes yet)
    votes: list[VoteRead] = []
```

- [ ] **Step 2: Написать падающий тест сервиса.** Create `backend/tests/test_committees_srez2_service.py`:

```python
"""Unit: committees срез-2 projections (vote summary, protocol with tally)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.domains.committees.service import build_protocol, vote_summary
from app.models.committees import VoteChoice


def _vote(pid, choice):
    return SimpleNamespace(id=f"v-{pid}", decision_id="d1", person_id=pid, choice=choice)


def test_vote_summary_carried():
    votes = [_vote("p1", VoteChoice.FOR), _vote("p2", VoteChoice.FOR), _vote("p3", VoteChoice.AGAINST)]
    s = vote_summary("d1", votes)
    assert (s.votes_for, s.votes_against, s.votes_abstain) == (2, 1, 0)
    assert s.outcome == "carried"


def test_vote_summary_tie_rejected():
    votes = [_vote("p1", VoteChoice.FOR), _vote("p2", VoteChoice.AGAINST)]
    assert vote_summary("d1", votes).outcome == "rejected"


def test_build_protocol_includes_tally():
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    meeting = SimpleNamespace(
        id="m1", committee_id="c1", scheduled_at=now, location=None, status=SimpleNamespace(value="held"),
        held_at=now, protocol_seq=1, protocol_year=2026, members_total=4, present_count=3, quorum_met=True,
        created_at=now, updated_at=now,
    )
    decision = SimpleNamespace(id="d1", meeting_id="m1", agenda_item_id=None, text="X", decided_at=now)
    votes = [_vote("p1", VoteChoice.FOR), _vote("p2", VoteChoice.FOR)]
    proto = build_protocol(meeting, [(decision, [], votes)])
    pd = proto.decisions[0]
    assert pd.votes_for == 2 and pd.outcome == "carried"
    assert proto.meeting.protocol_seq == 1
```

- [ ] **Step 3: Прогнать — должен падать.** Run: `$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_committees_srez2_service.py -q` → FAIL.

- [ ] **Step 4: Реализовать service.** В `backend/app/domains/committees/service.py`:

```python
from app.domains.committees.lifecycle import decision_outcome, is_task_overdue, tally_votes
from app.schemas.committees import (
    DecisionRead,
    DecisionTaskRead,
    DecisionVoteSummary,
    MeetingRead,
    ProtocolDecision,
    ProtocolRead,
    VoteRead,
)


def vote_summary(decision_id: str, votes) -> DecisionVoteSummary:
    choices = [v.choice for v in votes]
    vf, va, vab = tally_votes(choices)
    outcome = decision_outcome(vf, va).value if votes else "rejected"
    return DecisionVoteSummary(
        decision_id=decision_id,
        votes_for=vf,
        votes_against=va,
        votes_abstain=vab,
        outcome=outcome,
        votes=[VoteRead.model_validate(v, from_attributes=True) for v in votes],
    )
```

Изменить `build_protocol` — теперь принимает тройки `(decision, tasks, votes)`:

```python
def build_protocol(meeting, decisions_with_votes, *, today: date | None = None) -> ProtocolRead:
    """decisions_with_votes: iterable of (decision_row, [task_rows], [vote_rows])."""
    today = today or _today()
    grouped = []
    for decision, tasks, votes in decisions_with_votes:
        choices = [v.choice for v in votes]
        vf, va, vab = tally_votes(choices)
        grouped.append(
            ProtocolDecision(
                decision=DecisionRead.model_validate(decision, from_attributes=True),
                tasks=[task_to_read(t, today=today) for t in tasks],
                votes_for=vf,
                votes_against=va,
                votes_abstain=vab,
                outcome=decision_outcome(vf, va).value if votes else None,
                votes=[VoteRead.model_validate(v, from_attributes=True) for v in votes],
            )
        )
    return ProtocolRead(
        meeting=MeetingRead.model_validate(meeting, from_attributes=True),
        decisions=grouped,
    )
```

(Импортировать `tally_votes`, `decision_outcome` в service.py.)

- [ ] **Step 5: Прогнать — должен пройти.** Run: `$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_committees_srez2_service.py backend/tests/test_committees_schemas.py -q` → PASS. `ruff` + `black --check` на изменённых файлах.

- [ ] **Step 6: Commit.** `git add backend/app/schemas/committees.py backend/app/domains/committees/service.py backend/tests/test_committees_srez2_service.py && git commit -m "feat(p10-01): committees срез-2 schemas + vote/protocol projections"`

---

## Task 4: API-эндпоинты — TDD (contract style, mocked session)

**Files:**
- Modify: `backend/app/api/routes/committees.py`
- Test: `backend/tests/test_committees_srez2_api.py`

Стиль тестов — как `test_committees_api.py`: `AsyncMock()` сессия, `monkeypatch.setattr(routes, "_get_meeting", AsyncMock(...))`, вызов route-функции напрямую, ассерт на `exc.value.status_code`.

- [ ] **Step 1: Написать падающие тесты.** Create `backend/tests/test_committees_srez2_api.py`:

```python
"""Contract tests for committees срез-2 routes (mocked session, no live DB)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes
from app.models.committees import MeetingStatus, VoteChoice
from app.schemas.committees import AttendanceBulkUpdate, AttendanceItem, MeetingStatusUpdate, VoteCreate


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1")


def _meeting(status=MeetingStatus.PLANNED, **kw):
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    base = dict(
        id="m1", committee_id="c1", tenant_id="tenant-1", scheduled_at=now, location=None,
        status=status, held_at=None, protocol_seq=None, protocol_year=None,
        members_total=None, present_count=None, quorum_met=None,
        created_at=now, updated_at=now, deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_hold_without_quorum_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED)))
    monkeypatch.setattr(routes, "_count_members", AsyncMock(return_value=4))
    monkeypatch.setattr(routes, "_count_present", AsyncMock(return_value=2))
    with pytest.raises(Exception) as exc:
        await routes.update_meeting(
            mid="m1", payload=MeetingStatusUpdate(status=MeetingStatus.HELD),
            tenant=_tenant(), session=session, access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_vote_on_non_held_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_get_decision", AsyncMock(return_value=SimpleNamespace(id="d1", meeting_id="m1", tenant_id="tenant-1")))
    monkeypatch.setattr(routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED)))
    with pytest.raises(Exception) as exc:
        await routes.cast_vote(
            did="d1", payload=VoteCreate(person_id="p1", choice=VoteChoice.FOR),
            tenant=_tenant(), session=session, access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_vote_absent_voter_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_get_decision", AsyncMock(return_value=SimpleNamespace(id="d1", meeting_id="m1", tenant_id="tenant-1")))
    monkeypatch.setattr(routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD)))
    monkeypatch.setattr(routes, "_is_present", AsyncMock(return_value=False))
    with pytest.raises(Exception) as exc:
        await routes.cast_vote(
            did="d1", payload=VoteCreate(person_id="p1", choice=VoteChoice.FOR),
            tenant=_tenant(), session=session, access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_attendance_on_held_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD)))
    with pytest.raises(Exception) as exc:
        await routes.put_attendance(
            mid="m1", payload=AttendanceBulkUpdate(items=[AttendanceItem(person_id="p1", present=True)]),
            tenant=_tenant(), session=session, access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409
```

- [ ] **Step 2: Прогнать — падает** (функций/хелперов нет). Run: `$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_committees_srez2_api.py -q` → FAIL.

- [ ] **Step 3: Реализовать роуты.** В `backend/app/api/routes/committees.py`:

Добавить импорты (модели `CommitteeMeetingAttendance`, `CommitteeDecisionVote`, `VoteChoice`; lifecycle `validate_hold`, `ensure_can_vote`; schemas новые; `datetime`/`timezone`). Добавить коды ошибок-хелперы:

```python
def _err(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=api_problem_detail(code=code, message=message, error_type="committees"),
    )
```

Хелперы (patched в тестах — module-level функции):

```python
async def _count_members(session, tenant, committee_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count(func.distinct(CommitteeMember.person_id))).where(
                    CommitteeMember.committee_id == committee_id,
                    CommitteeMember.tenant_id == tenant.id,
                )
            )
        ).scalar_one()
        or 0
    )


async def _count_present(session, tenant, meeting_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).where(
                    CommitteeMeetingAttendance.meeting_id == meeting_id,
                    CommitteeMeetingAttendance.tenant_id == tenant.id,
                    CommitteeMeetingAttendance.present.is_(True),
                )
            )
        ).scalar_one()
        or 0
    )


async def _is_present(session, tenant, meeting_id: str, person_id: str) -> bool:
    row = (
        await session.execute(
            select(CommitteeMeetingAttendance.id).where(
                CommitteeMeetingAttendance.meeting_id == meeting_id,
                CommitteeMeetingAttendance.tenant_id == tenant.id,
                CommitteeMeetingAttendance.person_id == person_id,
                CommitteeMeetingAttendance.present.is_(True),
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def _committee_member_person_ids(session, tenant, committee_id: str) -> set[str]:
    rows = (
        await session.execute(
            select(CommitteeMember.person_id).where(
                CommitteeMember.committee_id == committee_id,
                CommitteeMember.tenant_id == tenant.id,
            )
        )
    ).scalars().all()
    return set(rows)
```

`GET`/`PUT` attendance:

```python
@router.get("/meetings/{mid}/attendance", response_model=list[AttendanceRead])
async def get_attendance(mid: str, tenant: TenantDep, session: SessionDep, access: Access):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_meeting(session, tenant, mid)
    rows = (
        await session.execute(
            select(CommitteeMeetingAttendance).where(
                CommitteeMeetingAttendance.meeting_id == mid,
                CommitteeMeetingAttendance.tenant_id == tenant.id,
            )
        )
    ).scalars().all()
    return [AttendanceRead.model_validate(r, from_attributes=True) for r in rows]


@router.put("/meetings/{mid}/attendance", response_model=list[AttendanceRead])
async def put_attendance(
    mid: str, payload: AttendanceBulkUpdate, tenant: TenantDep, session: SessionDep, access: Access
):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    meeting = await _get_meeting(session, tenant, mid)
    if meeting.status is not MeetingStatus.PLANNED:
        raise _err("COMMITTEE_MEETING_NOT_PLANNED", "Attendance editable only before the meeting is held", status.HTTP_409_CONFLICT)
    member_ids = await _committee_member_person_ids(session, tenant, meeting.committee_id)
    for item in payload.items:
        if item.person_id not in member_ids:
            raise _err("COMMITTEE_NOT_A_MEMBER", f"person {item.person_id} is not a committee member", status.HTTP_422_UNPROCESSABLE_ENTITY)
    # upsert: delete existing for this meeting, re-insert
    existing = (
        await session.execute(
            select(CommitteeMeetingAttendance).where(
                CommitteeMeetingAttendance.meeting_id == mid,
                CommitteeMeetingAttendance.tenant_id == tenant.id,
            )
        )
    ).scalars().all()
    by_person = {r.person_id: r for r in existing}
    for item in payload.items:
        row = by_person.get(item.person_id)
        if row is None:
            row = CommitteeMeetingAttendance(tenant_id=tenant.id, meeting_id=mid, person_id=item.person_id, present=item.present)
            session.add(row)
        else:
            row.present = item.present
    await session.flush()
    return await get_attendance(mid=mid, tenant=tenant, session=session, access=access)
```

Расширить `update_meeting` — вставить ветку `status == HELD`:

```python
@router.patch("/meetings/{mid}", response_model=MeetingRead)
async def update_meeting(mid, payload, tenant, session, access):
    ...
    row = await _get_meeting(session, tenant, mid)
    if payload.status is MeetingStatus.HELD:
        members_total = await _count_members(session, tenant, row.committee_id)
        present_count = await _count_present(session, tenant, mid)
        quorum = is_quorum(members_total, present_count)
        try:
            validate_hold(row.status, quorum)
        except MeetingTransitionError as exc:
            if not quorum:
                raise _err("COMMITTEE_QUORUM_NOT_MET", "Quorum not met", status.HTTP_409_CONFLICT)
            raise _conflict(exc)
        now = datetime.now(tz=timezone.utc)
        year = now.year
        seqs = (
            await session.execute(
                select(CommitteeMeeting.protocol_seq).where(
                    CommitteeMeeting.committee_id == row.committee_id,
                    CommitteeMeeting.tenant_id == tenant.id,
                    CommitteeMeeting.protocol_year == year,
                    CommitteeMeeting.protocol_seq.is_not(None),
                )
            )
        ).scalars().all()
        row.protocol_seq = next_protocol_seq([s for s in seqs if s is not None])
        row.protocol_year = year
        row.held_at = now
        row.members_total = members_total
        row.present_count = present_count
        row.quorum_met = True
        row.status = MeetingStatus.HELD
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise _err("COMMITTEE_PROTOCOL_CONFLICT", "Protocol number conflict, retry", status.HTTP_409_CONFLICT)
        await session.refresh(row)
        return MeetingRead.model_validate(row, from_attributes=True)
    # existing non-held path (cancelled etc.)
    try:
        validate_meeting_transition(row.status, payload.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row.status = payload.status
    await session.flush()
    await session.refresh(row)
    return MeetingRead.model_validate(row, from_attributes=True)
```

(Импортировать `IntegrityError` из `sqlalchemy.exc`; `is_quorum`, `next_protocol_seq`, `validate_hold` из lifecycle.)

`cast_vote` / `get_votes`:

```python
@router.post("/decisions/{did}/votes", response_model=VoteRead, status_code=status.HTTP_201_CREATED)
async def cast_vote(did, payload: VoteCreate, tenant: TenantDep, session: SessionDep, access: Access):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    decision = await _get_decision(session, tenant, did)
    meeting = await _get_meeting(session, tenant, decision.meeting_id)
    try:
        ensure_can_vote(meeting.status)
    except MeetingTransitionError as exc:
        raise _err("COMMITTEE_DECISION_NOT_HELD", str(exc), status.HTTP_409_CONFLICT)
    if not await _is_present(session, tenant, decision.meeting_id, payload.person_id):
        raise _err("COMMITTEE_VOTER_ABSENT", "Voter not present at meeting", status.HTTP_409_CONFLICT)
    existing = (
        await session.execute(
            select(CommitteeDecisionVote).where(
                CommitteeDecisionVote.decision_id == did,
                CommitteeDecisionVote.tenant_id == tenant.id,
                CommitteeDecisionVote.person_id == payload.person_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = CommitteeDecisionVote(tenant_id=tenant.id, decision_id=did, person_id=payload.person_id, choice=payload.choice)
        session.add(existing)
    else:
        existing.choice = payload.choice
    await session.flush()
    await session.refresh(existing)
    return VoteRead.model_validate(existing, from_attributes=True)


@router.get("/decisions/{did}/votes", response_model=DecisionVoteSummary)
async def get_votes(did, tenant: TenantDep, session: SessionDep, access: Access):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_decision(session, tenant, did)
    votes = (
        await session.execute(
            select(CommitteeDecisionVote).where(
                CommitteeDecisionVote.decision_id == did,
                CommitteeDecisionVote.tenant_id == tenant.id,
            )
        )
    ).scalars().all()
    return vote_summary(did, votes)
```

Расширить `get_protocol` — грузить голоса на каждое решение и передавать тройки `(d, tasks, votes)` в `build_protocol`.

Журнал `GET /protocols` — вставить **до** `/{cid}` catch-all? Нет: путь `/committees/protocols` статический, но `GET /committees/{cid}` матчит `cid="protocols"`. **Порядок роутов**: `list_protocols` объявить в файле ДО `get_committee`/`get_committee`-catch, либо путь не пересекается (у `/{cid}` префикс `/committees/{cid}` — `protocols` попадёт в `cid`). Решение: зарегистрировать `GET /committees/protocols` **раньше** `GET /committees/{cid}` в коде (FastAPI матчит по порядку). Разместить функцию сразу после `list_committees`.

```python
@router.get("/protocols", response_model=ProtocolJournalPage)
async def list_protocols(
    request: Request, response: Response, tenant: TenantDep, session: SessionDep, access: Access,
    committee_id: str | None = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    conds = [
        CommitteeMeeting.tenant_id == tenant.id,
        CommitteeMeeting.deleted_at.is_(None),
        CommitteeMeeting.protocol_seq.is_not(None),
    ]
    if committee_id:
        conds.append(CommitteeMeeting.committee_id == committee_id)
    stmt = (
        select(CommitteeMeeting, Committee.name)
        .join(Committee, Committee.id == CommitteeMeeting.committee_id)
        .where(*conds)
        .order_by(CommitteeMeeting.protocol_year.desc(), CommitteeMeeting.protocol_seq.desc())
        .limit(limit).offset(offset)
    )
    rows = list((await session.execute(stmt)).all())
    total = (await session.execute(select(func.count()).where(*conds))).scalar_one()
    # decisions_count per meeting (single grouped query)
    meeting_ids = [m.id for m, _ in rows]
    counts = {}
    if meeting_ids:
        for mid_, cnt in (
            await session.execute(
                select(CommitteeDecision.meeting_id, func.count())
                .where(CommitteeDecision.meeting_id.in_(meeting_ids), CommitteeDecision.tenant_id == tenant.id)
                .group_by(CommitteeDecision.meeting_id)
            )
        ).all():
            counts[mid_] = cnt
    items = [
        ProtocolJournalItem(
            meeting_id=m.id, committee_id=m.committee_id, committee_name=name,
            protocol_no=f"{m.protocol_seq}/{m.protocol_year}", held_at=m.held_at,
            members_total=m.members_total, present_count=m.present_count,
            decisions_count=counts.get(m.id, 0),
        )
        for m, name in rows
    ]
    etag = compute_list_etag(tenant_id=str(tenant.id), items=[m for m, _ in rows], scalars=[("total", int(total or 0)), ("limit", limit), ("offset", offset), ("cid", committee_id or "")])
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return ProtocolJournalPage(items=items, total=int(total or 0), limit=limit, offset=offset)
```

- [ ] **Step 4: Прогнать — должен пройти.** Run: `$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_committees_srez2_api.py backend/tests/test_committees_api.py -q` → PASS. `ruff` + `black --check`.

- [ ] **Step 5: Commit.** `git add backend/app/api/routes/committees.py backend/tests/test_committees_srez2_api.py && git commit -m "feat(p10-01): committees срез-2 API — attendance, quorum-hold, votes, protocol journal"`

---

## Task 5: Demo-seed

**Files:** Modify `backend/app/services/demo_bootstrap.py` (`_seed_committees_demo`)

- [ ] **Step 1: Расширить сид.** После создания committee/meeting/decision добавить (идемпотентно — проверять, есть ли уже члены):
  - 4 `CommitteeMember` из существующих demo-persons (роли chair/secretary/member/member). Нужны person_id из демо-тенанта — переиспользовать persons, которые сид уже создаёт (grep как other seeds берут persons: `select(Person).where(tenant...).limit(4)`).
  - `CommitteeMeetingAttendance` present=True для 3 из 4 (кворум есть: 3*2>4).
  - Перевести meeting в held с `protocol_seq=1, protocol_year=meeting.scheduled_at.year, held_at=now, members_total=4, present_count=3, quorum_met=True, status=HELD`.
  - 3 `CommitteeDecisionVote` по демо-решению (2 FOR, 1 AGAINST → carried).
  - Guard: если у комитета уже есть члены — пропустить (идемпотентность).

- [ ] **Step 2: Проверить сид не падает.** Run: `$env:PYTHONPATH="backend"; python -m pytest backend/tests/ -q -k "demo and committee" ` (или ближайший demo-bootstrap тест). Если нет — smoke: импорт + вызов на in-memory через существующий demo-тест. Минимум: `ruff`/`black`.

- [ ] **Step 3: Commit.** `git add backend/app/services/demo_bootstrap.py && git commit -m "feat(p10-01): seed committee members + held meeting with quorum & votes"`

---

## Task 6: Frontend API-клиент

**Files:** Modify `frontend/src/api/committees.ts`

- [ ] **Step 1: Добавить типы и методы.**

```typescript
export interface Attendance { id: string; meeting_id: string; person_id: string; present: boolean; }
export type VoteChoice = "for" | "against" | "abstain";
export interface Vote { id: string; decision_id: string; person_id: string; choice: VoteChoice; }
export interface DecisionVoteSummary {
  decision_id: string; votes_for: number; votes_against: number; votes_abstain: number;
  outcome: "carried" | "rejected"; votes: Vote[];
}
export interface ProtocolJournalItem {
  meeting_id: string; committee_id: string; committee_name: string; protocol_no: string;
  held_at: string; members_total: number | null; present_count: number | null; decisions_count: number;
}
export interface ProtocolJournalPage { items: ProtocolJournalItem[]; total: number; limit: number; offset: number; }
```

Расширить `Meeting` (+`held_at`, `protocol_seq`, `protocol_year`, `members_total`, `present_count`, `quorum_met`, `protocol_no?`) и `ProtocolDecision` (+`votes_for`/`votes_against`/`votes_abstain`/`outcome`/`votes`).

Методы в `committeesApi`:

```typescript
async getAttendance(meetingId: string): Promise<Attendance[]> {
  return (await apiClient.get<Attendance[]>(`${base}/meetings/${meetingId}/attendance`)).data;
},
async putAttendance(meetingId: string, items: { person_id: string; present: boolean }[]): Promise<Attendance[]> {
  return (await apiClient.put<Attendance[]>(`${base}/meetings/${meetingId}/attendance`, { items })).data;
},
async holdMeeting(meetingId: string): Promise<Meeting> {
  return (await apiClient.patch<Meeting>(`${base}/meetings/${meetingId}`, { status: "held" })).data;
},
async castVote(decisionId: string, person_id: string, choice: VoteChoice): Promise<Vote> {
  return (await apiClient.post<Vote>(`${base}/decisions/${decisionId}/votes`, { person_id, choice })).data;
},
async getVotes(decisionId: string): Promise<DecisionVoteSummary> {
  return (await apiClient.get<DecisionVoteSummary>(`${base}/decisions/${decisionId}/votes`)).data;
},
async listProtocols(params: { committee_id?: string; limit?: number; offset?: number } = {}): Promise<ProtocolJournalPage> {
  return (await apiClient.get<ProtocolJournalPage>(`${base}/protocols`, { params: { limit: 100, offset: 0, ...params } })).data;
},
// create helpers (write UI): createCommittee, addMember, removeMember, createMeeting, createDecision, createTask, updateTask
```

Также добавить write-методы для поддерживающего UI (createCommittee POST ``${base}``, addMember POST ``${base}/${cid}/members``, removeMember DELETE, createMeeting POST ``${base}/${cid}/meetings``, createDecision POST ``${base}/meetings/${mid}/decisions``, createTask POST ``${base}/decisions/${did}/tasks``, updateTask PATCH ``${base}/tasks/${tid}``).

- [ ] **Step 2: Тест API-клиента.** Create `frontend/src/api/committees.srez2.test.ts` — vi.mock apiClient, проверить URL/тело для `putAttendance`, `holdMeeting`, `castVote`, `getVotes`, `listProtocols`. Паттерн — как существующие api-тесты (`grep -l "vi.mock" frontend/src/api/*.test.ts`).

- [ ] **Step 3: Прогнать точечно.** Run: `npx vitest run src/api/committees.srez2.test.ts` → PASS.

- [ ] **Step 4: Commit.** `git add frontend/src/api/committees.ts frontend/src/api/committees.srez2.test.ts && git commit -m "feat(p10-01): committees срез-2 frontend API client"`

---

## Task 7: Frontend UI — ядро заседаний + write-UI

**Files:** Modify `frontend/src/pages/committees/CommitteesPage.tsx`; Test `frontend/src/pages/committees/CommitteesPage.srez2.test.tsx`

- [ ] **Step 1: Расширить страницу.** Компоненты (в том же файле, паттерн срез-1):
  - `CommitteeList` + **форма создания комитета** (name/kind, `createCommittee` → reload).
  - `MembersPanel(committee)`: список членов + добавление (person_id + роль) + удаление.
  - `MeetingList` + **форма создания заседания** (scheduled_at/location).
  - `AttendancePanel(meeting, members)`: чекбоксы присутствия (только если `meeting.status==="planned"`), «Сохранить» (`putAttendance`), индикатор кворума (present/total), кнопка «Провести заседание» (`holdMeeting`; при 409 — показать текст ошибки: «Кворум не набран»). После held — показать `protocol_no` + снапшот.
  - `ProtocolPanel(meeting)` (расширить): + форма создания решения (на held), по каждому решению — блок голосования (для присутствующих членов кнопки за/против/воздержался → `castVote`, затем `getVotes` для tally), бейдж «Принято»/«Отклонено» по `outcome`; форма создания задачи.
  - `ProtocolJournalPanel`: `listProtocols`, таблица (номер, комитет, дата, решений), клик → выбрать заседание/протокол.
  - RU-лейблы: kind (osms→«Комитет по ОТ» и т.д.), роль, choice, outcome.

Держать паттерн срез-1 (Card/Table/Badge/EmptyState/ErrorState/LoadingScreen; локальный load/loading/error на панель). RBAC на фронте не гейтить.

- [ ] **Step 2: vitest на страницу.** Create `CommitteesPage.srez2.test.tsx`: замокать `committeesApi`, проверить: рендер чекбоксов присутствия; индикатор «кворум есть/нет»; клик «Провести» вызывает `holdMeeting`; при 409-ошибке показывается сообщение; бейдж outcome; рендер журнала. Использовать `vi.hoisted()` если фабрика мока ссылается на const (house-паттерн, TDZ). Текст-коллизии — `within(...)`.

- [ ] **Step 3: Прогнать точечно.** Run: `npx vitest run src/pages/committees/CommitteesPage.srez2.test.tsx src/router/__tests__/AppRouterSmoke*` → PASS. Маршрут `/committees` не меняется.

- [ ] **Step 4: Commit.** `git add frontend/src/pages/committees/CommitteesPage.tsx frontend/src/pages/committees/CommitteesPage.srez2.test.tsx && git commit -m "feat(p10-01): committees срез-2 UI — proceedings + write forms + protocol journal"`

---

## Task 8: Гейты + документация

- [ ] **Step 1: PG16-гейт** (контроллер, фоново, PowerShell): `$env:PYTHONPATH="backend"; python scripts/ci/local_gate.py --db-only` — миграция `cmt02` up/down round-trip на реальном PG16 (native enum `votechoice` + partial unique index). Ожидание: «ЗЕЛЁНЫЙ ✅ exit=0». (Если PG16 недоступен локально — отметить mismatch, CI прогонит.)

- [ ] **Step 2: OpenAPI baseline пере-снять.** Найти snapshot-файл (`grep -rn "openapi" scripts/ci/ | head`; обычно `docs/api/openapi.snapshot.json` или `.baseline`). Регенерировать по README-процедуре, затем `python scripts/ci/check_openapi_snapshot.py` (env: `PYTHONPATH=backend` + `SECRET_KEY`/`S3_*`, см. память `openapi-arch4-gate-standalone`). Ожидание: только новые operationIds (get_attendance/put_attendance/cast_vote/get_votes/list_protocols) добавлены, `✓ ARCH-4 unchanged`.

- [ ] **Step 3: Полный backend-регресс** батчами ≤5 (PowerShell, ОДИН прогон, timeout 600000): все `backend/tests/test_committees_*.py`. Ожидание: exit 0.

- [ ] **Step 4: Frontend гейты** (не параллелить с pytest): `npm --prefix frontend run test` (полный vitest; красный — перепроверить повтором) → `npm --prefix frontend run typecheck` → `npm --prefix frontend run build`. Ожидание: всё зелёное, build exit 0.

- [ ] **Step 5: Документация.** Обновить: `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху), `CHANGELOG.md`, roadmap-строку P10-01 в `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (срез-2: кворум/голосование/нумерация/журнал — done; остаётся приглашения/KPI/Command Center-проекция). Commit.

- [ ] **Step 6: Финальный self-review** и подготовка PR (base=main; merge — решение пользователя).

---

## Self-Review (checklist пройден при написании)

- **Покрытие спеки:** модель+миграция (T1) ✓ · правила (T2) ✓ · схемы/service (T3) ✓ · API attendance/hold/votes/protocol/журнал (T4) ✓ · demo-seed (T5) ✓ · фронт API (T6) ✓ · фронт UI (T7) ✓ · гейты/доки (T8) ✓. DISTINCT person_id для кворума — в `_count_members` (T4). Задвоение члена по ролям — покрыто `func.distinct`.
- **Типы согласованы:** `VoteChoice.FOR/AGAINST/ABSTAIN="for/against/abstain"`; `is_quorum(members_total, present_count)`; `next_protocol_seq(existing_seqs)`; `build_protocol(meeting, [(decision, tasks, votes)])` — сигнатура изменена согласованно в T3 (service) и T4 (get_protocol вызывает с тройками). `protocol_no` формат `N/YYYY` везде.
- **Порядок роутов:** `list_protocols` (`/protocols`) объявляется ДО `get_committee` (`/{cid}`) — иначе `cid="protocols"` перехватит (T4 step 3).
- **Риск computed_field:** T3 step 1 явно требует проверить механизм сериализации `protocol_no` (computed_field vs заполнение в роуте) — не placeholder, а условная развилка с обеими ветками.
