"""Dataset registry integrity (P10-07 report builder)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select


def test_registry_shape() -> None:
    from app.modules.report_builder.datasets import DATASETS, OPS_BY_KIND

    assert set(DATASETS.keys()) == {"employees_training", "incidents", "risks", "ppe_warehouse"}
    for code, spec in DATASETS.items():
        assert spec.code == code
        assert spec.title  # RU-название непустое
        keys = [c.key for c in spec.columns]
        assert len(keys) == len(set(keys)), f"duplicate column keys in {code}"
        for col in spec.columns:
            assert col.kind in OPS_BY_KIND, f"{code}.{col.key}: unknown kind {col.kind}"
            assert col.label, f"{code}.{col.key}: empty label"
            if col.aggregatable:
                assert col.kind == "number", f"{code}.{col.key}: only numbers are aggregatable"
            if col.kind == "enum":
                assert col.enum_cls is not None and col.enum_values, f"{code}.{col.key}"
        stmt = spec.build_stmt("tenant-x", datetime.now(tz=timezone.utc))
        assert isinstance(stmt, Select)
        # labeled columns of the base select match the declared registry keys
        assert [c.key for c in stmt.selected_columns] == keys


def test_expected_columns_pinned() -> None:
    from app.modules.report_builder.datasets import DATASETS

    assert [c.key for c in DATASETS["employees_training"].columns] == [
        "person_name",
        "position_title",
        "course_name",
        "status",
        "scheduled_at",
        "completed_at",
        "expires_at",
        "is_overdue",
    ]
    assert [c.key for c in DATASETS["incidents"].columns] == [
        "title",
        "incident_type",
        "status",
        "severity",
        "occurred_at",
        "company_name",
        "site_name",
    ]
    assert [c.key for c in DATASETS["risks"].columns] == [
        "hazard",
        "probability",
        "severity",
        "level",
        "controls",
        "company_name",
        "site_name",
    ]
    assert [c.key for c in DATASETS["ppe_warehouse"].columns] == [
        "item_name",
        "code",
        "category",
        "min_stock",
        "on_hand",
        "below_min",
    ]
