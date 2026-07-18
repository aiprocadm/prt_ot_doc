from __future__ import annotations

from app.domains.medical import lifecycle as lc
from app.domains.medical.psychiatric_defaults import PSYCHIATRIC_ACTIVITY_DEFAULTS

# catalog: (code, name, interval_days)
CAT = [("height", "Работы на высоте", 1825), ("transport", "Транспорт", 1095)]


def test_psychiatric_required():
    assert lc.psychiatric_required({"height"}, CAT) is True
    assert lc.psychiatric_required({"height", "unknown"}, CAT) is True
    assert lc.psychiatric_required(set(), CAT) is False
    assert lc.psychiatric_required({"unknown"}, CAT) is False  # code not in catalog
    assert lc.psychiatric_required({"height"}, []) is False  # empty catalog


def test_psychiatric_interval():
    # strictest (min) among mapped activities
    assert lc.psychiatric_interval({"height", "transport"}, CAT) == 1095
    assert lc.psychiatric_interval({"height"}, CAT) == 1825
    # fallback to 5y default when nothing matches
    assert lc.psychiatric_interval(set(), CAT) == 1825
    assert lc.psychiatric_interval({"unknown"}, CAT) == 1825


def test_defaults_constant_shape():
    assert len(PSYCHIATRIC_ACTIVITY_DEFAULTS) >= 8
    for code, name, days in PSYCHIATRIC_ACTIVITY_DEFAULTS:
        assert isinstance(code, str) and code
        assert isinstance(name, str) and name
        assert days == 1825
    # codes unique
    codes = [c for c, _, _ in PSYCHIATRIC_ACTIVITY_DEFAULTS]
    assert len(codes) == len(set(codes))
