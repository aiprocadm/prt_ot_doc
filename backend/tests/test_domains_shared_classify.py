from datetime import date
import pytest
from app.domains.shared import ContingentItemStatus, classify


@pytest.mark.parametrize(
    "valid_until, expected",
    [
        (None, ContingentItemStatus.MISSING),
        (date(2026, 1, 1), ContingentItemStatus.OVERDUE),
        (date(2026, 6, 20), ContingentItemStatus.DUE_SOON),
        (date(2026, 12, 31), ContingentItemStatus.OK),
    ],
)
def test_classify_buckets(valid_until, expected):
    assert classify(valid_until, date(2026, 6, 8)) == expected


def test_medical_lifecycle_reexports_shared():
    from app.domains.medical import lifecycle as lc
    assert lc.classify is classify
    assert lc.ContingentItemStatus is ContingentItemStatus
