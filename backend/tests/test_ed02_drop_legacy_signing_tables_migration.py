"""ed02 migration guard: легаси-таблицы signatures/edo_envelopes дропнуты точно и обратимо.

После ЭДО Срез-1 (ПЭП-ядро на signature_requests) у таблиц ``signatures`` и
``edo_envelopes`` не осталось ни писателей, ни читателей; их ORM-классы
(Signature, EdoEnvelope) удалены из кодовой базы. ed02 дропает таблицы.
Эти тесты пинят:

  * цепочку ревизий ed01 → ed02 (литералами);
  * что upgrade дропает РОВНО эти две таблицы — и имена переданы строковыми
    ЛИТЕРАЛАМИ (AST-аудит ORM↔миграций не видит модульные константы);
  * что дропнутые таблицы исчезли из обоих declarative-реестров, а живые
    signature_requests / edo_messages остались;
  * симметрию downgrade: обе таблицы воссоздаются в состоянии «на позиции
    ed02» — у edo_envelopes есть iter29-колонка ``version`` (default "1") и
    iter38-default "queued" на ``status``; у signatures колонки version НЕТ
    (iter29 её не ретрофитил); все 4 индекса восстановлены.
"""

from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path

# Hermetic env defaults (как в test_orm_mapper_configuration.py): импорт
# модельного графа не должен зависеть от ambient-конфига / .env.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260612_ed02_drop_legacy_signing_tables.py"
)

LEGACY_TABLES = {"signatures", "edo_envelopes"}


def _load_module():
    spec = importlib.util.spec_from_file_location("ed02_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260612_ed02_drop_legacy_signing_tables"' in src
    assert 'down_revision = "20260611_ed01_pep_signing_columns"' in src
    assert "depends_on = None" in src


def test_dropped_tables_have_no_orm_mapping():
    """Обе дропаемые таблицы отсутствуют в declarative-реестрах, а живой
    ПЭП/ЭДО-контур (signature_requests, edo_messages) остаётся замаплен."""
    import app.db.base  # noqa: F401  # side-effect: регистрирует все модели
    from app.db.session import SharedBase, TenantBase

    mapped = set(SharedBase.metadata.tables) | set(TenantBase.metadata.tables)
    leaked = LEGACY_TABLES & mapped
    assert not leaked, f"ed02 дропает таблицы, всё ещё замапленные ORM: {sorted(leaked)}"

    for live in ("signature_requests", "edo_messages"):
        assert live in mapped, f"живая таблица {live!r} пропала из ORM-метаданных"


def test_upgrade_drops_exactly_the_two_legacy_tables(monkeypatch):
    module = _load_module()

    dropped: list[str] = []
    monkeypatch.setattr(module.op, "drop_table", lambda name, *a, **k: dropped.append(name))
    monkeypatch.setattr(module.op, "get_bind", lambda: None)
    # enum.drop(bind=None, checkfirst=True) на None-bind упадёт — глушим:
    monkeypatch.setattr(
        type(module.signature_type), "drop", lambda self, bind, checkfirst=True: None
    )

    module.upgrade()

    assert set(dropped) == LEGACY_TABLES
    assert len(dropped) == len(LEGACY_TABLES), "таблица дропается дважды"


def test_upgrade_table_names_are_string_literals():
    """AST-аудит ORM↔миграций не видит модульные константы — имена таблиц в
    op.drop_table обязаны быть строковыми литералами (грабля, трижды
    подтверждённая в этом репо)."""
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    upgrade_fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
        None,
    )
    assert upgrade_fn is not None, "ed02: нет upgrade()"
    drop_args: list[str] = []
    for node in ast.walk(upgrade_fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_table"
        ):
            assert (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ), "op.drop_table должен получать имя таблицы строковым литералом"
            drop_args.append(node.args[0].value)
    assert set(drop_args) == LEGACY_TABLES


def test_downgrade_recreates_tables_at_ed02_chain_position(monkeypatch):
    module = _load_module()

    created: dict[str, dict] = {}
    indexes: list[tuple[str, str]] = []

    def fake_create_table(name, *cols, **kw):
        created[name] = {c.name: c for c in cols if hasattr(c, "name") and c.name}

    monkeypatch.setattr(module.op, "create_table", fake_create_table)
    monkeypatch.setattr(
        module.op, "create_index", lambda idx, table, *a, **k: indexes.append((idx, table))
    )
    monkeypatch.setattr(module.op, "get_bind", lambda: None)
    monkeypatch.setattr(
        type(module.signature_type), "create", lambda self, bind, checkfirst=True: None
    )

    module.downgrade()

    # обе таблицы возвращаются, лишних нет
    assert set(created) == LEGACY_TABLES

    # signatures — verbatim из mvp-миграции: БЕЗ version (iter29 не ретрофитил)
    assert set(created["signatures"]) == {
        "document_version_id",
        "type",
        "status",
        "signer_user_id",
        "cert_info_json",
        "signed_at",
        "receipts_s3_key",
        "id",
        "tenant_id",
        "created_at",
        "updated_at",
    }
    assert "version" not in created["signatures"]

    # edo_envelopes — next30 + iter29 version + iter38 default
    assert set(created["edo_envelopes"]) == {
        "object_type",
        "object_id",
        "provider",
        "status",
        "external_id",
        "last_event_at",
        "id",
        "tenant_id",
        "created_at",
        "updated_at",
        "version",
    }
    version = created["edo_envelopes"]["version"]
    assert version.server_default is not None
    assert str(version.server_default.arg) == "1"
    status = created["edo_envelopes"]["status"]
    assert status.server_default is not None
    assert str(status.server_default.arg) == "queued"

    # создающие миграции дропают эти индексы явно в своих downgrade —
    # ed02.downgrade обязан их восстановить, иначе `downgrade base` ломается.
    assert ("ix_signatures_document", "signatures") in indexes
    assert ("ix_signatures_status", "signatures") in indexes
    assert ("ix_edo_envelopes_status", "edo_envelopes") in indexes
    assert ("ix_edo_envelopes_object", "edo_envelopes") in indexes


def test_orphaned_pg_enum_types_are_cleaned_and_restored():
    """signaturetype/signaturestatus/edoenvelopestatus использовались только
    колонками дропаемых таблиц: upgrade их дропает (guarded), downgrade —
    воссоздаёт (на SQLite оба вызова — no-op, enum там VARCHAR)."""
    module = _load_module()
    assert module.signature_type.name == "signaturetype"
    assert module.signature_status.name == "signaturestatus"
    assert module.edo_envelope_status.name == "edoenvelopestatus"

    src = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(src)

    def _calls(fn_name: str, attr: str) -> int:
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn_name)
        return sum(
            1
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr
        )

    assert _calls("upgrade", "drop") == 3, "upgrade должен дропнуть 3 осиротевших enum-типа"
    assert _calls("downgrade", "create") >= 3, "downgrade должен воссоздать 3 enum-типа"
