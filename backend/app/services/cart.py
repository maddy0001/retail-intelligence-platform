"""
cart.py — one cart document per customer (`_id` = customer id), items embedded.

Embedding fits: a cart is small, bounded, always read and written as a whole,
and owned by exactly one customer.
"""

from fastapi import HTTPException

from config import COLL_CARTS, COLL_PRODUCTS
from .common import PRODUCT_CARD_FIELDS, now, product_card
from .money import paise

MAX_QTY = 20


def get_cart_doc(db, customer_id: str, session=None) -> dict:
    return db[COLL_CARTS].find_one({"_id": customer_id}, session=session) or {"_id": customer_id, "items": []}


def cart_view(db, customer: dict) -> dict:
    """The cart with live prices from the catalog, delivery rules and totals, in store rupees."""
    from .checkout import FREE_DELIVERY_MIN, delivery_quote   # local import: checkout imports cart helpers
    cart = get_cart_doc(db, customer["_id"])
    ids = [i["product_id"] for i in cart.get("items", [])]
    products = {p["product_id"]: p for p in db[COLL_PRODUCTS].find({"product_id": {"$in": ids}}, PRODUCT_CARD_FIELDS)}
    items, subtotal, freight, mrp_total = [], 0.0, 0.0, 0.0
    for item in cart.get("items", []):
        p = products.get(item["product_id"])
        if not p or p.get("price") is None:
            continue
        qty = int(item["quantity"])
        card = product_card(p)
        line = paise(card["price"] * qty)
        subtotal += line
        freight += (card["freight"] or 0.0) * qty
        mrp_total += (card["mrp"] or card["price"]) * qty
        items.append({**card, "quantity": qty, "line_total": line})
    subtotal = paise(subtotal)
    quote = delivery_quote(subtotal, freight, customer)
    return {"items": items, "count": sum(i["quantity"] for i in items),
            "subtotal": subtotal, "freight": quote["freight"], "delivery": quote,
            "free_delivery_min": FREE_DELIVERY_MIN, "mrp_savings": paise(mrp_total - subtotal),
            "total": paise(subtotal + quote["freight"]), "currency": "INR"}


def add_item(db, customer_id: str, product_id: str, quantity: int) -> dict:
    product = db[COLL_PRODUCTS].find_one({"product_id": product_id}, {"product_id": 1, "category": 1, "price": 1})
    if not product or product.get("price") is None:
        raise HTTPException(404, "That product is not available.")
    ts = now()
    # Existing line: raise its quantity, capped at MAX_QTY, with an update pipeline ($map over items).
    res = db[COLL_CARTS].update_one(
        {"_id": customer_id, "items.product_id": product_id},
        [{"$set": {
            "items": {"$map": {"input": "$items", "as": "i", "in": {"$cond": [
                {"$eq": ["$$i.product_id", product_id]},
                {"$mergeObjects": ["$$i", {"quantity": {"$min": [MAX_QTY, {"$add": ["$$i.quantity", quantity]}]}}]},
                "$$i"]}}},
            "updated_at": ts,
        }}],
    )
    if res.matched_count == 0:
        db[COLL_CARTS].update_one(
            {"_id": customer_id},
            {"$push": {"items": {"product_id": product_id, "quantity": min(quantity, MAX_QTY), "added_at": ts}},
             "$set": {"updated_at": ts}, "$setOnInsert": {"created_at": ts}},
            upsert=True,
        )
    return product


def set_quantity(db, customer_id: str, product_id: str, quantity: int):
    if quantity <= 0:
        return remove_item(db, customer_id, product_id)
    res = db[COLL_CARTS].update_one({"_id": customer_id, "items.product_id": product_id},
                                    {"$set": {"items.$.quantity": min(quantity, MAX_QTY), "updated_at": now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "That item is not in your cart.")


def remove_item(db, customer_id: str, product_id: str):
    db[COLL_CARTS].update_one({"_id": customer_id},
                              {"$pull": {"items": {"product_id": product_id}}, "$set": {"updated_at": now()}})
