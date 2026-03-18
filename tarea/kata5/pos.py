"""
Kata 5 – Point of Sale kata.

Implements a minimal barcode scanner with support for a total command.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List


def _to_decimal(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


class PointOfSaleTerminal:
    """
    Processes barcode commands and keeps track of scanned totals.
    """

    def __init__(self, price_catalog: Dict[str, str | Decimal] | None = None):
        default_catalog = {
            "12345": Decimal("7.25"),
            "23456": Decimal("12.50"),
        }
        self._catalog: Dict[str, Decimal] = {
            code: _to_decimal(price) for code, price in (price_catalog or default_catalog).items()
        }
        self._scanned: List[Decimal] = []

    def process(self, command: str) -> str:
        """
        Scan a barcode or execute the 'total' command.
        """

        code = (command or "").strip()
        if not code:
            return "Error: empty barcode"

        if code.lower() == "total":
            total = sum(self._scanned, Decimal("0"))
            return f"Total: ${self._format(total)}"

        price = self._catalog.get(code)
        if price is None:
            return "Error: barcode not found"

        self._scanned.append(price)
        return f"${self._format(price)}"

    @staticmethod
    def _format(amount: Decimal) -> str:
        quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{quantized:.2f}"
