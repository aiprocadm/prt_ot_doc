import pytest

pytestmark = pytest.mark.skip(reason="tenant routing fixture mismatch in isolated CI environment")
