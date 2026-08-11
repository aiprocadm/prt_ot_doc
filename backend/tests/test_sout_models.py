"""Pin: СОУТ срез-1 model shapes (P10-04 / TZ B.10)."""

from __future__ import annotations


def test_campaign_table_and_columns() -> None:
    from app.models.sout import SoutCampaign

    assert SoutCampaign.__tablename__ == "sout_campaign"
    cols = set(SoutCampaign.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "name",
        "expert_org_name",
        "report_number",
        "report_date",
        "status",
        "planned_date",
        "completed_date",
    } <= cols


def test_workplace_table_and_columns() -> None:
    from app.models.sout import SoutWorkplace

    assert SoutWorkplace.__tablename__ == "sout_workplace"
    cols = set(SoutWorkplace.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "deleted_at",
        "campaign_id",
        "workplace_code",
        "position_name",
        "person_id",
        "assessed_class",
        "assessment_date",
        "next_assessment_date",
    } <= cols


def test_child_tables_and_columns() -> None:
    from app.models.sout import SoutFactor, SoutGuarantee

    assert SoutFactor.__tablename__ == "sout_factor"
    assert {"workplace_id", "code", "name", "measured_class", "note"} <= set(
        SoutFactor.__table__.columns.keys()
    )
    assert SoutGuarantee.__tablename__ == "sout_guarantee"
    assert {"workplace_id", "kind", "detail"} <= set(SoutGuarantee.__table__.columns.keys())


def test_enums_use_value_labels() -> None:
    from app.models.sout import SoutCampaignStatus, SoutClass, SoutGuaranteeKind

    assert {m.value for m in SoutCampaignStatus} == {
        "planned",
        "in_progress",
        "completed",
        "declared",
        "cancelled",
    }
    assert {m.value for m in SoutClass} == {
        "optimal",
        "acceptable",
        "harmful_3_1",
        "harmful_3_2",
        "harmful_3_3",
        "harmful_3_4",
        "dangerous",
    }
    assert {m.value for m in SoutGuaranteeKind} == {
        "additional_leave",
        "extra_pay",
        "reduced_hours",
        "milk",
        "early_pension",
        "medical_exam",
    }


def test_soutclass_enum_shared_across_two_columns() -> None:
    """assessed_class + measured_class reference the SAME named enum type."""
    from app.models.sout import SoutFactor, SoutWorkplace

    wp_type = SoutWorkplace.__table__.columns["assessed_class"].type
    f_type = SoutFactor.__table__.columns["measured_class"].type
    assert wp_type.name == "soutclass"
    assert f_type.name == "soutclass"


def test_models_reexported_from_package() -> None:
    from app.models import SoutCampaign, SoutWorkplace  # noqa: F401


def test_workplace_has_nullable_position_bridge() -> None:
    from app.models.sout import SoutWorkplace

    col = SoutWorkplace.__table__.c.position_id
    assert col.nullable is True
    assert any(fk.column.table.name == "position" for fk in col.foreign_keys)


def test_factor_has_nullable_hazard_bridge() -> None:
    from app.models.sout import SoutFactor

    col = SoutFactor.__table__.c.hazard_id
    assert col.nullable is True
    assert any(fk.column.table.name == "risk_hazards" for fk in col.foreign_keys)
