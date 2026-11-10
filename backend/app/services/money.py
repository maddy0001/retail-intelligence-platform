"""
money.py — the store's currency.

The catalogue is the real Olist dataset, so every price in MongoDB is in
Brazilian reais (BRL), and the analytics pipelines and models work in BRL.
Kartiq shows and charges Indian rupees (INR):

  * a catalogue price becomes a store price at ONE fixed rate (INR_PER_BRL),
    rounded to the whole rupee the way Indian stores price things;
  * totals, discounts and delivery are then worked out in rupees, so the
    numbers a shopper sees always add up (paise appear only where a
    percentage creates them, e.g. 10% off ₹1,475 = ₹147.50);
  * an app order stores what was charged in rupees (`charged`) AND the same
    amounts in reais in the Olist-shaped fields (`unit_price`, `total`,
    `payment.total_value`), so Pipelines A and B read app orders exactly like
    Olist orders.

Rule of thumb: BRL in the database, INR on the wire.
"""

import os
from decimal import ROUND_HALF_UP, Decimal

# About ₹17.8 per R$1 at the end of October 2026 (mid-market). Fixed on purpose:
# a store does not reprice its catalogue every time the exchange rate moves.
INR_PER_BRL = float(os.environ.get("INR_PER_BRL", "17.8"))
_RATE = Decimal(str(INR_PER_BRL))

CURRENCY = {"code": "INR", "symbol": "₹", "locale": "en-IN",
            "source_code": "BRL", "inr_per_brl": INR_PER_BRL}


def _half_up(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def store_price(brl):
    """Catalogue price (BRL) -> store price in whole rupees (float, e.g. 1600.0)."""
    if brl is None:
        return None
    return float(_half_up(Decimal(str(brl)) * _RATE, "1"))


def inr(brl, rate: float = None):
    """Any BRL amount -> rupees with paise (used for stored totals of older orders)."""
    if brl is None:
        return None
    r = _RATE if rate is None else Decimal(str(rate))
    return float(_half_up(Decimal(str(brl)) * r, "0.01"))


def to_brl(amount_inr, rate: float = None):
    """Rupees -> reais, for the Olist-shaped fields of an app order."""
    if amount_inr is None:
        return None
    r = _RATE if rate is None else Decimal(str(rate))
    return float(_half_up(Decimal(str(amount_inr)) / r, "0.01"))


def paise(value: float) -> float:
    """Round a rupee amount to the paisa."""
    return float(_half_up(Decimal(str(value)), "0.01"))


def brl_floor(min_inr: float) -> float:
    """Lowest BRL catalogue price whose store price is >= min_inr (for a $gte query)."""
    return (float(min_inr) - 0.5) / INR_PER_BRL


def brl_ceiling(max_inr: float) -> float:
    """BRL bound such that price < bound  <=>  store price <= max_inr (for a $lt query)."""
    return (float(max_inr) + 0.5) / INR_PER_BRL


def _indian_grouping(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def rupees(amount) -> str:
    """₹1,23,456 or ₹1,326.60 — Indian digit grouping, paise only when there are some."""
    if amount is None:
        return "—"
    value = _half_up(Decimal(str(amount)), "0.01")
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = int(value)
    p = int((value - whole) * 100)
    return f"{sign}₹{_indian_grouping(whole)}" + (f".{p:02d}" if p else "")
