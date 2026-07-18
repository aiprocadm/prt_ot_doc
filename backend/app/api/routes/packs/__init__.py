"""Document-pack endpoints (ARCH-4 slice 8 — package split).

Public surface unchanged: ``from app.api.routes import packs`` -> ``packs.router`` (used by
route_groups) plus the role constants / error helpers imported by tests and
``generate_document_task`` (whose ``.apply_async`` several tests monkeypatch via
``app.api.routes.packs.generate_document_task``). Endpoint modules are imported in
registration order so route/OpenAPI order is preserved.
"""

# isort: off
from app.api.routes.packs import _common  # noqa: F401  (defines the shared router)
from app.api.routes.packs import management  # noqa: F401  (scenarios/list/generate)
from app.api.routes.packs import run  # noqa: F401  (run/downloads/summary)

# isort: on
from app.api.routes.packs._common import (  # noqa: F401  re-export for route_groups + tests
    _PACK_READ_ROLES,
    _PACK_WRITE_ROLES,
    _pack_bad_request,
    _validate_pack_output_selection,
    router,
)
from app.services.tasks import generate_document_task  # noqa: F401  (mock-patch target)

__all__ = ["router"]
