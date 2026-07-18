from __future__ import annotations

from app.api.routes.invoices import _INVOICE_READ_ROLES, _INVOICE_WRITE_ROLES


def test_invoices_access_roles_read_write_parity() -> None:
    read_roles = set(_INVOICE_READ_ROLES)
    write_roles = set(_INVOICE_WRITE_ROLES)

    # Any write-capable role must also be allowed to read invoice surfaces.
    assert write_roles.issubset(read_roles)
