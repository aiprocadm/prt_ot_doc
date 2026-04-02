from __future__ import annotations

from app.api.routes.invoices import _invoice_bad_request, _invoice_unprocessable


def test_invoices_bad_request_has_structured_error_detail() -> None:
    exc = _invoice_bad_request("order mismatch")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "invoice_validation_error",
        "message": "order mismatch",
    }


def test_invoices_unprocessable_has_structured_error_detail() -> None:
    exc = _invoice_unprocessable("unsupported invoice status")

    assert exc.status_code == 422
    assert exc.detail == {
        "code": "invoice_validation_error",
        "message": "unsupported invoice status",
    }
