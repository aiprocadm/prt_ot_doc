"""Document generation API endpoints (ARCH-4 slice 5 — package split).

Public surface is unchanged: ``from app.api.routes.documents import router`` (used by
route_groups) plus the internals imported by tests. Endpoint modules are imported in
registration order (read then generate) so the route/OpenAPI order is preserved.
"""

# isort: off
from app.api.routes.documents import _common  # noqa: F401  (defines the shared router)
from app.api.routes.documents import read  # noqa: F401  (registers read routes first)
from app.api.routes.documents import generate  # noqa: F401  (registers generate routes)

# isort: on
from app.api.routes.documents._common import (  # noqa: F401  re-export for back-compat
    DocGenerateRequest,
    router,
)
from app.api.routes.documents._generate_helpers import (  # noqa: F401  re-export for tests
    _fetch_template,
    _normalize_scope_level,
    _scope_target_ids,
    _serialize_payload,
)

__all__ = ["router"]
