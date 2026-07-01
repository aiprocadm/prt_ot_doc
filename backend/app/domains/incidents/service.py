"""Deprecated compat-shim — incident/inspection ops moved to
:mod:`app.modules.incidents.operations` (ARCH-1).

Kept as a re-export so ``from app.domains.incidents.service import …`` keeps working until
the next major (POST-1 removes the ``domains/*`` shims). New code should import from
``app.modules.incidents``.
"""

from __future__ import annotations

from app.modules.incidents.operations import (  # noqa: F401  (compat re-export)
    add_inspection_result,
    append_log_entry,
    register_incident,
    register_inspection,
    update_incident,
    update_inspection,
)
