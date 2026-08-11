"""ed03 migration guard: unique-индекс briefing_signatures + дедуп-семантика.

down_revision намеренно НЕ ассертится: в репо many-heads by design, оркестратор
может ре-парентнуть миграцию при интеграции параллельных срезов.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260612_ed03_briefing_signature_unique.py"
)

INDEX_NAME = "uq_briefing_signatures_entry_signer"
INDEX_COLUMNS = ["briefing_entry_id", "signer_type"]


def _load_module():
    spec = importlib.util.spec_from_file_location("ed03_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_and_literal_table_name():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260612_ed03_briefing_signature_unique"' in src
    # Грабля AST-аудита (трижды подтверждена): имя таблицы в op.* — литералом.
    assert '"briefing_signatures"' in src
    assert "depends_on = None" in src


def test_upgrade_dedups_before_creating_unique_index(monkeypatch):
    """Порядок обязателен: сначала дедуп, потом unique-индекс."""
    module = _load_module()
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(module.op, "execute", lambda sql, *a, **k: events.append(("execute", str(sql))))
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table, columns, **kw: events.append(("create_index", (name, table, tuple(columns), kw))),
    )
    module.upgrade()

    kinds = [kind for kind, _ in events]
    assert "execute" in kinds and "create_index" in kinds
    assert kinds.index("execute") < kinds.index("create_index")

    dedup_sql = next(payload for kind, payload in events if kind == "execute")
    assert "DELETE FROM briefing_signatures" in dedup_sql

    name, table, columns, kw = next(payload for kind, payload in events if kind == "create_index")
    assert name == INDEX_NAME
    assert table == "briefing_signatures"
    assert list(columns) == INDEX_COLUMNS
    assert kw.get("unique") is True


def test_downgrade_drops_only_the_index(monkeypatch):
    module = _load_module()
    dropped: list[tuple[str, str | None]] = []
    deleted: list[str] = []
    monkeypatch.setattr(
        module.op, "drop_index", lambda name, table_name=None, **k: dropped.append((name, table_name))
    )
    monkeypatch.setattr(module.op, "execute", lambda *a, **k: deleted.append(str(a)))
    module.downgrade()
    assert dropped == [(INDEX_NAME, "briefing_signatures")]
    # Удалённые дубли не восстанавливаются (честно зафиксировано в docstring) —
    # downgrade не выполняет никаких DML.
    assert deleted == []


def test_dedup_semantics_on_real_sqlite(monkeypatch):
    """Вставить дубли «до», прогнать upgrade-логику, проверить «после».

    Остаётся самая ранняя запись по signed_at (tie-break: меньший id);
    уникальные пары не затрагиваются; индекс реально блокирует новый дубль.
    """
    module = _load_module()
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE briefing_signatures ("
        "id TEXT PRIMARY KEY, briefing_entry_id TEXT NOT NULL, "
        "signer_type TEXT NOT NULL, signed_at TEXT NOT NULL)"
    )
    rows = [
        # entry-1 / employee: три дубля — выживает самый ранний по signed_at (sig-b)
        ("sig-a", "entry-1", "employee", "2026-06-10T10:00:00"),
        ("sig-b", "entry-1", "employee", "2026-06-09T09:00:00"),
        ("sig-c", "entry-1", "employee", "2026-06-11T11:00:00"),
        # entry-1 / instructor: уникальна — не трогаем
        ("sig-d", "entry-1", "instructor", "2026-06-10T10:00:00"),
        # entry-2 / employee: одинаковый signed_at — tie-break по меньшему id (sig-e)
        ("sig-e", "entry-2", "employee", "2026-06-10T10:00:00"),
        ("sig-f", "entry-2", "employee", "2026-06-10T10:00:00"),
    ]
    conn.executemany("INSERT INTO briefing_signatures VALUES (?, ?, ?, ?)", rows)
    conn.commit()

    monkeypatch.setattr(module.op, "execute", lambda sql, *a, **k: conn.execute(str(sql)))
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table, columns, unique=False, **k: conn.execute(
            f"CREATE {'UNIQUE ' if unique else ''}INDEX {name} ON {table} ({', '.join(columns)})"
        ),
    )
    module.upgrade()
    conn.commit()

    survivors = {
        row[0]
        for row in conn.execute("SELECT id FROM briefing_signatures ORDER BY id").fetchall()
    }
    assert survivors == {"sig-b", "sig-d", "sig-e"}

    # Unique-индекс реально стоит: повторная вставка пары падает.
    try:
        conn.execute(
            "INSERT INTO briefing_signatures VALUES ('sig-x', 'entry-1', 'employee', '2026-06-12T12:00:00')"
        )
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "unique index must reject a duplicate (briefing_entry_id, signer_type)"
    conn.close()
