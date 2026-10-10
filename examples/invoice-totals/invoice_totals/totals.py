"""Net, VAT and gross totals for an invoice.

Synthetic example code for claude-code-harness. Not a billing system.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Line:
    description: str
    unit_price: Decimal  # net, in euro
    quantity: int
    vat_rate: Decimal  # 0.19 means 19 percent


@dataclass(frozen=True)
class Totals:
    net: Decimal
    vat: Decimal
    gross: Decimal


def invoice_totals(lines: list[Line]) -> Totals:
    """Sum net amounts per VAT rate, compute VAT per rate, round each rate's VAT to the cent."""
    net_by_rate: dict[Decimal, Decimal] = {}
    for line in lines:
        if line.quantity < 1:
            raise ValueError(f"quantity must be at least 1, got {line.quantity} for {line.description!r}")
        net_by_rate[line.vat_rate] = net_by_rate.get(line.vat_rate, Decimal("0")) + line.unit_price * line.quantity

    net = sum(net_by_rate.values(), Decimal("0"))
    vat = sum((round(amount * rate, 2) for rate, amount in net_by_rate.items()), Decimal("0"))
    return Totals(net=net.quantize(CENT), vat=vat.quantize(CENT), gross=(net + vat).quantize(CENT))
