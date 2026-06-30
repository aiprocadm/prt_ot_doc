"""Medical requirement endpoints (ARCH-4 slice 7 — package split).

Public surface unchanged: ``from app.api.routes import medical`` -> ``medical.router`` (used by
route_groups) plus the role constants imported by tests. Endpoint modules are imported in
registration order so route/OpenAPI order is preserved.
"""

# isort: off
from app.api.routes.medical import _common  # noqa: F401  (defines the shared router)
from app.api.routes.medical import exams  # noqa: F401  (registers exam routes first)
from app.api.routes.medical import catalog  # noqa: F401  (norms/referrals/factors)
from app.api.routes.medical import contingent  # noqa: F401  (mappings/contingent/summary)

# isort: on
from app.api.routes.medical._common import (  # noqa: F401  re-export for route_groups + tests
    _MEDICAL_READ_ROLES,
    _MEDICAL_WRITE_ROLES,
    router,
)

__all__ = ["router"]
