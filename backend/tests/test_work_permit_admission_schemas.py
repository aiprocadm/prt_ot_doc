from datetime import date

from app.schemas.work_permit import WorkPermitDailyAdmissionCreate, WorkPermitEventRead


def test_admission_create_minimal():
    a = WorkPermitDailyAdmissionCreate(admission_date=date(2026, 6, 18))
    assert a.admission_date == date(2026, 6, 18)
    assert a.note is None


def test_event_read_has_meta_field():
    assert "meta" in WorkPermitEventRead.model_fields
