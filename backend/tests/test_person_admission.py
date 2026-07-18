"""Task 7.1 regression: verify the shared helper exists and is delegated to."""
import inspect

from app.services import person_admission, tasks


def test_shared_helper_exists_and_is_used():
    assert hasattr(person_admission, "enforce_person_admission")
    assert "enforce_person_admission" in inspect.getsource(tasks._enforce_person_invariants)
