"""Схемы API согласованы с ORM по полям из docs/DOMAIN_MODEL.md (§ расхождения)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.document import DocumentStatus
from app.models.models import DocumentPackModule, DocumentPackScenario, EmploymentStatus
from app.schemas.document import DocumentRead
from app.schemas.pack import PackListItem
from app.schemas.person import PersonRead


def test_person_read_includes_employment_status() -> None:
    stub = SimpleNamespace(
        id="p1",
        company_id="c1",
        position_id=None,
        workplace_id=None,
        first_name="Иван",
        last_name="Иванов",
        middle_name=None,
        birth_date=None,
        personnel_number=None,
        hired_at=None,
        qualifications=[],
        snils=None,
        passport=None,
        email="i@example.com",
        phone="+79000000000",
        employment_status=EmploymentStatus.ON_LEAVE,
        current_ppe=[],
        working_conditions_class=None,
        hazardous_factors=[],
    )
    read = PersonRead.model_validate(stub)
    assert read.employment_status == EmploymentStatus.ON_LEAVE


def test_document_read_includes_storage_links() -> None:
    now = datetime.now(tz=timezone.utc)
    stub = SimpleNamespace(
        id="d1",
        company_id="c1",
        template_id="t1",
        person_id=None,
        site_id="s1",
        template_version_id="tv1",
        status=DocumentStatus.DRAFT,
        storage_key="k1",
        file_id="f1",
        signed_file_id="sf1",
        content_sha256="abc",
        job_id="j1",
        created_by="u1",
        created_at=now,
        updated_at=now,
    )
    read = DocumentRead.model_validate(stub)
    assert read.site_id == "s1"
    assert read.template_version_id == "tv1"
    assert read.file_id == "f1"
    assert read.signed_file_id == "sf1"
    assert read.content_sha256 == "abc"
    assert read.job_id == "j1"


def test_pack_list_item_requires_module_and_scenario() -> None:
    now = datetime.now(tz=timezone.utc)
    item = PackListItem(
        id="pack1",
        code="ot_starter",
        name="Стартовый набор",
        description=None,
        module=DocumentPackModule.OT.value,
        scenario_type=DocumentPackScenario.DOCUMENT_BATCH.value,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert item.module == "ot"
    assert item.scenario_type == "document_batch"


@pytest.mark.parametrize(
    "raw_module,raw_scenario",
    [
        (DocumentPackModule.FIRE_SAFETY, DocumentPackScenario.REPORT),
        ("custom", "workflow"),
    ],
)
def test_pack_list_item_accepts_enum_or_string(raw_module, raw_scenario) -> None:
    now = datetime.now(tz=timezone.utc)
    mod = raw_module.value if hasattr(raw_module, "value") else raw_module
    scen = raw_scenario.value if hasattr(raw_scenario, "value") else raw_scenario
    item = PackListItem(
        id="p",
        code="c",
        name="n",
        module=mod,
        scenario_type=scen,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert item.module == mod
    assert item.scenario_type == scen
