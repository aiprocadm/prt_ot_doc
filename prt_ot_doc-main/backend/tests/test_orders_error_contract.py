from __future__ import annotations

from app.api.routes.orders import _order_unprocessable


def test_orders_unprocessable_has_structured_error_detail() -> None:
    exc = _order_unprocessable("unsupported order status")

    assert exc.status_code == 422
    assert exc.detail == {
        "code": "order_validation_error",
        "message": "unsupported order status",
    }
