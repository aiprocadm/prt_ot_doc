from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class InvoiceCalculator:
    vat_rate: Decimal = Decimal("0.20")

    def calculate(self, amount: Decimal) -> dict[str, Decimal]:
        vat = (amount * self.vat_rate).quantize(Decimal("0.01"))
        total = amount + vat
        return {"amount": amount, "vat": vat, "total": total}
