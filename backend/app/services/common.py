"""common.py — small helpers shared by the services: time, ids, and JSON-safe shapes."""

import uuid
from datetime import datetime, timezone

from bson import ObjectId

from .money import store_price

PRODUCT_CARD_FIELDS = {
    "_id": 0, "product_id": 1, "name": 1, "category": 1, "category_label": 1, "price": 1,
    "freight": 1, "rating_avg": 1, "review_count": 1, "sales_count": 1, "seller": 1,
    "price_range": 1, "delivery_days": 1,
}

# "M.R.P." in the store = the HIGHEST price this product actually sold for in the
# Olist data. It is only shown when today's price is 5-60% below it: smaller gaps
# are noise, and bigger ones are usually a one-off outlier sale. Both prices are
# compared as the shopper sees them (store rupees), so the % off always matches.
MRP_MIN_GAP, MRP_MAX_GAP = 0.05, 0.60
MAX_PROMISE_DAYS = 30


def mrp_and_discount(doc: dict):
    price = store_price(doc.get("price"))
    top = store_price((doc.get("price_range") or {}).get("max"))
    if not price or not top or top <= price:
        return None, None
    gap = (top - price) / top
    if not MRP_MIN_GAP <= gap <= MRP_MAX_GAP:
        return None, None
    return top, int(round(gap * 100))


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def clean(value):
    """Recursively make a Mongo document JSON-safe (ObjectId -> str, datetime -> ISO)."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    return value


def product_card(doc: dict) -> dict:
    """A product as the store shows it. Prices are store rupees (see money.py)."""
    seller = doc.get("seller") or {}
    mrp, discount = mrp_and_discount(doc)
    days = doc.get("delivery_days")
    return {
        "product_id": doc["product_id"],
        "name": doc.get("name"),
        "category": doc.get("category"),
        "category_label": doc.get("category_label"),
        "price": store_price(doc.get("price")),
        "mrp": mrp,
        "discount_pct": discount,
        "delivery_days": min(int(days), MAX_PROMISE_DAYS) if days else None,
        "freight": store_price(doc.get("freight")),
        "rating_avg": doc.get("rating_avg"),
        "review_count": doc.get("review_count", 0),
        "sales_count": doc.get("sales_count", 0),
        "seller_city": seller.get("city"),
        "seller_state": seller.get("state"),
    }
