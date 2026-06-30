"""Risk endpoints (ARCH-4 slice 6 — package split).

Public surface unchanged: ``from app.api.routes import risk`` -> ``risk.router`` (used by
route_groups) plus the error helpers imported by tests. Endpoint modules are imported in
registration order, then engine_router is mounted into router (as the original file did at
its end), so route/OpenAPI order is preserved.
"""

# isort: off
from app.api.routes.risk import _common  # noqa: F401  (defines router + engine_router)
from app.api.routes.risk import methodologies  # noqa: F401  (registers config routes first)
from app.api.routes.risk import assessments  # noqa: F401  (registers assessment routes)
from app.api.routes.risk import reports  # noqa: F401  (registers cards/plans/list routes)

# isort: on
from app.api.routes.risk._common import (  # noqa: F401  re-export for route_groups + tests
    _risk_bad_request,
    _risk_unprocessable,
    engine_router,
    router,
)

router.include_router(engine_router)

__all__ = ["router"]
