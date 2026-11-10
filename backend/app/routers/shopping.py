"""Cart, checkout, orders, notifications, the home feed and app events."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config import COLL_CARTS, COLL_CUSTOMERS, COLL_NOTIFICATIONS, COLL_ORDERS, COLL_PRODUCTS
from ..db import get_client, get_db
from ..schemas import CartItemIn, CartQuantityIn, CheckoutIn, EventIn
from ..security import current_user, optional_user
from ..services import cart as cart_service
from ..services.activity import record_event
from ..services.checkout import CANCELLABLE, cancel_order, charged_amounts, offer_for, place_order, price_order
from ..services.common import clean
from ..services.personalization import home_feed, recommendations, taste_graph

router = APIRouter(prefix="/api", tags=["shopping"])


def _customer(db, user):
    customer = db[COLL_CUSTOMERS].find_one({"_id": user.get("customer_id")}) if user.get("customer_id") else None
    if not customer:
        raise HTTPException(403, "This account has no shopping profile.")
    return customer


# ---- home & recommendations -------------------------------------------------
@router.get("/home")
def home(user=Depends(optional_user), db=Depends(get_db)):
    customer = db[COLL_CUSTOMERS].find_one({"_id": user["customer_id"]}) if user and user.get("customer_id") else None
    return home_feed(db, customer)


@router.get("/recommendations")
def my_recommendations(user=Depends(current_user), db=Depends(get_db)):
    return recommendations(db, _customer(db, user)["_id"], n_categories=4, per_category=4)


@router.get("/taste-graph")
def my_taste_graph(user=Depends(optional_user), db=Depends(get_db)):
    """Categories + Module 2 similarities for the home page's 3-D taste map."""
    customer = db[COLL_CUSTOMERS].find_one({"_id": user["customer_id"]}) if user and user.get("customer_id") else None
    return taste_graph(db, customer)


# ---- cart -------------------------------------------------------------------
@router.get("/cart")
def get_cart(user=Depends(current_user), db=Depends(get_db)):
    return cart_service.cart_view(db, _customer(db, user))


@router.post("/cart/items")
def add_to_cart(body: CartItemIn, user=Depends(current_user), db=Depends(get_db)):
    customer = _customer(db, user)
    product = cart_service.add_item(db, customer["_id"], body.product_id, body.quantity)
    record_event(db, customer["_id"], "add_to_cart", product_id=body.product_id, category=product.get("category"))
    return cart_service.cart_view(db, customer)


@router.patch("/cart/items/{product_id}")
def change_quantity(product_id: str, body: CartQuantityIn, user=Depends(current_user), db=Depends(get_db)):
    customer = _customer(db, user)
    cart_service.set_quantity(db, customer["_id"], product_id, body.quantity)
    return cart_service.cart_view(db, customer)


@router.delete("/cart/items/{product_id}")
def remove_from_cart(product_id: str, user=Depends(current_user), db=Depends(get_db)):
    customer = _customer(db, user)
    cart_service.remove_item(db, customer["_id"], product_id)
    product = db[COLL_PRODUCTS].find_one({"product_id": product_id}, {"category": 1}) or {}
    record_event(db, customer["_id"], "remove_from_cart", product_id=product_id, category=product.get("category"))
    return cart_service.cart_view(db, customer)


@router.post("/events", status_code=201)
def app_event(body: EventIn, user=Depends(current_user), db=Depends(get_db)):
    """Front-end signals the server can't see by itself, e.g. leaving checkout
    with a full cart (cart_abandon) — the Change Stream counts these."""
    cid = _customer(db, user)["_id"]
    if body.event_type == "cart_abandon":
        cart = db[COLL_CARTS].find_one({"_id": cid}, {"items": 1}) or {}
        if not cart.get("items"):
            return {"recorded": False}
    record_event(db, cid, body.event_type, category=body.category)
    return {"recorded": True}


# ---- checkout & orders ------------------------------------------------------
@router.get("/checkout/preview")
def checkout_preview(coupon_code: Optional[str] = None, user=Depends(current_user), db=Depends(get_db)):
    customer = _customer(db, user)
    cart = db[COLL_CARTS].find_one({"_id": customer["_id"]}) or {"items": []}
    if not cart.get("items"):
        raise HTTPException(400, "Your cart is empty.")
    ids = [i["product_id"] for i in cart["items"]]
    products = {p["product_id"]: p for p in db[COLL_PRODUCTS].find({"product_id": {"$in": ids}})}
    priced = price_order(cart["items"], products, customer, coupon_code)
    return {**priced, "offer": offer_for(customer)}


@router.post("/checkout", status_code=201)
def checkout(body: CheckoutIn, user=Depends(current_user), db=Depends(get_db)):
    order = place_order(db, get_client(), user, _customer(db, user), body)
    return order_out(order)


def order_out(o: dict, detail: bool = True) -> dict:
    """An order as the shopper sees it. Amounts are rupees (see charged_amounts)."""
    paid = charged_amounts(o)
    out = {
        "id": o["_id"], "status": o.get("order_status"), "placed_at": o.get("order_purchase_timestamp"),
        "total": paid["total"], "items_total": paid["items_total"], "freight_total": paid["freight_total"],
        "discount": paid["discount"], "currency": "INR", "source": o.get("source"),
        "items_count": sum(li.get("quantity", 1) for li in o.get("line_items", [])),
        "can_cancel": o.get("source") == "app" and o.get("order_status") in CANCELLABLE,
    }
    if detail:
        lines = [{**li, "unit_price": paid["unit_prices"].get(li["product_id"])} for li in o.get("line_items", [])]
        out.update({"line_items": lines, "payment": o.get("payment"),
                    "timeline": o.get("timeline"), "status_history": o.get("status_history", []),
                    "shipping_address": o.get("shipping_address"), "customer_id": o.get("customer_id")})
    return clean(out)


@router.get("/orders")
def my_orders(user=Depends(current_user), db=Depends(get_db)):
    cid = _customer(db, user)["_id"]
    cursor = db[COLL_ORDERS].find({"customer_id": cid}).sort("order_purchase_timestamp", -1).limit(50)
    return [order_out(o, detail=False) | {"preview": [li.get("name") or li.get("category")
                                                      for li in o.get("line_items", [])[:3]]}
            for o in cursor]


def _own_order(db, user, order_id):
    order = db[COLL_ORDERS].find_one({"_id": order_id})
    if not order or (order.get("customer_id") != user.get("customer_id") and user.get("role") != "admin"):
        raise HTTPException(404, "Order not found.")
    return order


@router.get("/orders/{order_id}")
def order_detail(order_id: str, user=Depends(current_user), db=Depends(get_db)):
    order = _own_order(db, user, order_id)
    ids = [li["product_id"] for li in order.get("line_items", [])]
    names = {p["product_id"]: p for p in db[COLL_PRODUCTS].find({"product_id": {"$in": ids}},
                                                                 {"product_id": 1, "name": 1, "category_label": 1})}
    out = order_out(order)
    for li in out["line_items"]:
        p = names.get(li["product_id"], {})
        li.setdefault("name", p.get("name"))
        li["name"] = li.get("name") or p.get("name")
        li["category_label"] = li.get("category_label") or p.get("category_label")
    return out


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: str, user=Depends(current_user), db=Depends(get_db)):
    order = _own_order(db, user, order_id)
    updated = cancel_order(db, get_client(), order, str(user["_id"]), "Canceled by the customer")
    return order_out(updated)


# ---- notifications ----------------------------------------------------------
@router.get("/notifications")
def notifications(user=Depends(current_user), db=Depends(get_db)):
    uid = str(user["_id"])
    items = list(db[COLL_NOTIFICATIONS].find({"user_id": uid}).sort("created_at", -1).limit(30))
    unread = db[COLL_NOTIFICATIONS].count_documents({"user_id": uid, "read": False})
    return {"unread": unread, "items": clean(items)}


@router.post("/notifications/read")
def mark_read(user=Depends(current_user), db=Depends(get_db)):
    db[COLL_NOTIFICATIONS].update_many({"user_id": str(user["_id"]), "read": False}, {"$set": {"read": True}})
    return {"unread": 0}
