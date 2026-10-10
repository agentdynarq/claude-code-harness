import unittest
from decimal import Decimal

from invoice_totals import Line, invoice_totals

STANDARD = Decimal("0.19")
REDUCED = Decimal("0.07")


def line(price: str, quantity: int, rate: Decimal) -> Line:
    return Line(description="item", unit_price=Decimal(price), quantity=quantity, vat_rate=rate)


class InvoiceTotalsTest(unittest.TestCase):
    def test_whole_cent_vat(self):
        totals = invoice_totals([line("10.00", 2, STANDARD)])
        self.assertEqual((totals.net, totals.vat, totals.gross),
                         (Decimal("20.00"), Decimal("3.80"), Decimal("23.80")))

    def test_half_cent_vat_rounds_away_from_zero(self):
        # 1.50 * 0.19 = 0.285. Half-even rounding gives 0.28; the rule is 0.29.
        totals = invoice_totals([line("1.50", 1, STANDARD)])
        self.assertEqual(totals.vat, Decimal("0.29"))
        self.assertEqual(totals.gross, Decimal("1.79"))

    def test_vat_is_rounded_per_rate(self):
        # 3.50 * 0.07 = 0.245 -> 0.25 and 1.50 * 0.19 = 0.285 -> 0.29.
        totals = invoice_totals([line("3.50", 1, REDUCED), line("1.50", 1, STANDARD)])
        self.assertEqual(totals.vat, Decimal("0.54"))
        self.assertEqual(totals.gross, Decimal("5.54"))

    def test_lines_with_the_same_rate_are_summed_before_rounding(self):
        # Per line: 0.04 * 0.19 = 0.0076 -> 0.01, three times 0.03.
        # Summed first, as required: 0.12 * 0.19 = 0.0228 -> 0.02.
        totals = invoice_totals([line("0.04", 1, STANDARD)] * 3)
        self.assertEqual(totals.vat, Decimal("0.02"))

    def test_quantity_below_one_is_rejected(self):
        for quantity in (0, -2):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                invoice_totals([line("5.00", quantity, STANDARD)])


if __name__ == "__main__":
    unittest.main()
