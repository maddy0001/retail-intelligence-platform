"""
checkout.py — offers, the simulated payment, and placing / cancelling orders.

Placing an order is a MULTI-DOCUMENT ACID TRANSACTION (course Unit 5,
"Transactions with NoSQL"). In one all-or-nothing unit it:
  1. re-reads the cart inside the transaction and checks nothing changed,
  2. inserts the order,
  3. empties the cart,
  4. increments each product's sales_count,
  5. inserts the purchase events,
  6. updates the customer's order counters,
  7. inserts the "order placed" notification.
If any step fails, none of them happen — no order without an emptied cart, no
emptied cart without an order. MongoDB needs a replica set for this.

PRICES ARE IN RUPEES. The catalogue is priced in reais (the real Olist data);
the store converts at one fixed rate (services/money.py). Everything here is
worked out in rupees, and the stored order also keeps the same amounts in reais
in its Olist-shaped fields so the analytics pipelines read it like any Olist order.

PAYMENTS ARE SIMULATED. No card data leaves this process and no payment
provider is called. Card numbers are checked for shape (Luhn, expiry, CVV),
only the brand and last 4 digits are stored, and the test number
4000 0000 0000 0002 is always declined so the decline path can be demoed.
"""

from datetime import timedelta

from fastapi import HTTPException
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from config import COLL_CARTS, COLL_CUSTOMERS, COLL_EVENTS, COLL_ORDERS, COLL_PRODUCTS
from .activity import notify, record_event
from .common import new_id, now
from .money import INR_PER_BRL, inr, paise, rupees, store_price, to_brl

# Delivery is free on orders of at least FREE_DELIVERY_MIN rupees, and always free
# for Kartiq Plus members (customers K-Means places in High-Value Loyal).
FREE_DELIVERY_MIN = 2500.0
PLUS_SEGMENT = "High-Value Loyal"


def is_plus(customer: dict) -> bool:
    return ((customer or {}).get("segment") or {}).get("label") == PLUS_SEGMENT


def delivery_quote(subtotal: float, freight: float, customer: dict) -> dict:
    """Delivery charge after the free-delivery rules, plus why it is free."""
    if is_plus(customer):
        return {"freight": 0.0, "free": True, "reason": "plus", "saved": paise(freight)}
    if subtotal >= FREE_DELIVERY_MIN:
        return {"freight": 0.0, "free": True, "reason": "threshold", "saved": paise(freight)}
    return {"freight": paise(freight), "free": False, "reason": None, "saved": 0.0,
            "add_for_free": paise(FREE_DELIVERY_MIN - subtotal)}


# One offer per segment. Segments come from Module 1 (K-Means); "New Customer"
# is the rule-based label for a sign-up who has not completed an order yet.
# Minimum order values are in rupees.
OFFERS = {
    "High-Value Loyal": {"code": "PLUS10", "title": f"Plus member: 10% off orders over {rupees(1500)}",
                         "body": "As a Kartiq Plus member, delivery is always free. Use PLUS10 for 10% off too.",
                         "free_shipping": False, "discount_pct": 10, "min_subtotal": 1500},
    "Big Spender": {"code": "PREMIUM10", "title": f"10% off orders over {rupees(3000)}",
                    "body": "A thank-you for choosing quality.", "free_shipping": False,
                    "discount_pct": 10, "min_subtotal": 3000},
    "At-Risk": {"code": "COMEBACK15", "title": "We miss you: 15% off",
                "body": "It's been a while. Here's 15% off your next order.", "free_shipping": False,
                "discount_pct": 15, "min_subtotal": 0},
    "Bargain Browser": {"code": "DEALS10", "title": f"10% off orders over {rupees(999)}",
                        "body": "Stack a little more in your cart and save.", "free_shipping": False,
                        "discount_pct": 10, "min_subtotal": 999},
    "New Customer": {"code": "WELCOME10", "title": "Welcome! 10% off your first order",
                     "body": "Your first order is 10% off.", "free_shipping": False,
                     "discount_pct": 10, "min_subtotal": 0},
    "Occasional Shopper": {"code": "HELLO5", "title": "5% off your next order", "body": "",
                           "free_shipping": False, "discount_pct": 5, "min_subtotal": 0},
    "Dormant": {"code": "COMEBACK15", "title": "We miss you: 15% off", "body": "",
                "free_shipping": False, "discount_pct": 15, "min_subtotal": 0},
}

DECLINED_TEST_CARDS = {"4000000000000002"}
CANCELLABLE = {"processing", "under_review"}


def offer_for(customer: dict):
    label = ((customer or {}).get("segment") or {}).get("label")
    offer = OFFERS.get(label)
    return {**offer, "segment": label} if offer else None


def price_order(cart_items: list, products: dict, customer: dict, coupon_code: str = None) -> dict:
    """The order as the shopper pays for it, in rupees."""
    lines, subtotal, freight = [], 0.0, 0.0
    for item in cart_items:
        p = products.get(item["product_id"])
        if not p or p.get("price") is None:
            raise HTTPException(409, "An item in your cart is no longer available. Please review your cart.")
        qty = int(item["quantity"])
        unit, unit_freight = store_price(p["price"]), store_price(p.get("freight") or 0.0)
        subtotal += unit * qty
        freight += unit_freight * qty
        lines.append({
            "product_id": p["product_id"], "name": p.get("name"),
            "category": p.get("category"), "category_label": p.get("category_label"),
            "category_pt": p.get("category_pt"), "seller_id": (p.get("seller") or {}).get("seller_id"),
            "unit_price": unit, "freight_value": unit_freight,
            "quantity": qty, "delivery_days": min(int(p.get("delivery_days") or 10), 30),
        })
    subtotal = paise(subtotal)
    quote = delivery_quote(subtotal, freight, customer)
    freight = quote["freight"]

    discount = None
    if coupon_code:
        code = coupon_code.strip().upper()
        offer = offer_for(customer)
        if not offer or offer["code"] != code:
            raise HTTPException(422, f"Coupon {code} isn't available on your account.")
        if subtotal < offer["min_subtotal"]:
            raise HTTPException(422, f"Coupon {code} needs a subtotal of at least {rupees(offer['min_subtotal'])}.")
        amount = paise(subtotal * offer["discount_pct"] / 100)
        if offer["free_shipping"]:
            amount = paise(amount + freight)
        discount = {"code": code, "amount": amount, "segment": offer["segment"]}
    total = paise(subtotal + freight - (discount["amount"] if discount else 0.0))
    return {"lines": lines, "subtotal": subtotal, "freight": freight, "delivery": quote,
            "discount": discount, "total": total, "currency": "INR"}


def charged_amounts(order: dict) -> dict:
    """What the shopper paid for an order, in rupees, for any order in the database.

    App orders placed in rupees carry a `charged` block. Older app orders and the
    real Olist orders only have reais, so they are converted at the store rate:
    unit prices the same way as the catalogue (whole rupees), the payment exactly."""
    ch = order.get("charged")
    lines = order.get("line_items", [])
    if ch:
        units = {li["product_id"]: li.get("unit_price_inr") for li in lines}
        discount = order.get("discount")
        if discount:
            discount = {**discount, "amount": discount.get("amount_inr", discount.get("amount"))}
        return {"items_total": ch["items"], "freight_total": ch["delivery"], "discount": discount,
                "total": ch["total"], "unit_prices": units}
    units = {li["product_id"]: store_price(li.get("unit_price")) for li in lines}
    items = paise(sum((units[li["product_id"]] or 0) * li.get("quantity", 1) for li in lines))
    freight = store_price(order.get("freight_total")) if order.get("freight_total") is not None else None
    discount = order.get("discount")
    if discount:
        discount = {**discount, "amount": inr(discount.get("amount"))}
    if order.get("source") == "app":
        total = paise(items + (freight or 0.0) - ((discount or {}).get("amount") or 0.0))
    else:   # Olist: what the customer really paid (vouchers and card interest included)
        total = inr(order.get("total", (order.get("payment") or {}).get("total_value")))
    return {"items_total": items if lines else None, "freight_total": freight, "discount": discount,
            "total": total, "unit_prices": units}


def luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def process_payment(payment, amount: float) -> dict:
    """Simulated gateway, charging `amount` rupees. Returns an approval or a decline;
    raises 422 on malformed card data."""
    result = {"type": payment.method, "installments": payment.installments if payment.method == "credit_card" else 1,
              "amount_charged": amount, "currency": "INR", "methods": [payment.method], "simulated": True,
              "transaction_id": new_id("txn_"), "card": None}
    if payment.method in ("credit_card", "debit_card"):
        number = "".join(ch for ch in (payment.card_number or "") if ch.isdigit())
        if not (13 <= len(number) <= 19) or not luhn_ok(number):
            raise HTTPException(422, "That card number doesn't look right.")
        try:
            month, year = (payment.expiry or "").split("/")
            month, year = int(month), 2000 + int(year)
            current = now()
            if not 1 <= month <= 12 or (year, month) < (current.year, current.month):
                raise ValueError
        except ValueError:
            raise HTTPException(422, "Check the card's expiry date (MM/YY).")
        if not (payment.cvv or "").isdigit() or len(payment.cvv) not in (3, 4):
            raise HTTPException(422, "Check the card's security code.")
        brand = {"4": "visa", "5": "mastercard", "3": "amex", "6": "elo"}.get(number[0], "card")
        result["card"] = {"brand": brand, "last4": number[-4:]}
        if number in DECLINED_TEST_CARDS:
            return {**result, "status": "declined", "decline_reason": "card_declined"}
    return {**result, "status": "approved"}


def place_order(db, client, user: dict, customer: dict, body) -> dict:
    cid = customer["_id"]
    cart = db[COLL_CARTS].find_one({"_id": cid}) or {"items": []}
    if not cart.get("items"):
        raise HTTPException(400, "Your cart is empty.")
    ids = [i["product_id"] for i in cart["items"]]
    products = {p["product_id"]: p for p in db[COLL_PRODUCTS].find({"product_id": {"$in": ids}})}
    priced = price_order(cart["items"], products, customer, body.coupon_code)

    payment = process_payment(body.payment, priced["total"])
    if payment["status"] != "approved":
        record_event(db, cid, "payment_failed", extra={"reason": payment.get("decline_reason")})
        raise HTTPException(402, "Your payment was declined. Try another card or payment method.")

    risk = (customer.get("anomaly") or {}).get("risk_label")
    held = risk == "HIGH"
    ts = now()
    discount = priced["discount"]
    status = "under_review" if held else "processing"
    order_id = new_id("app_")
    order = {
        "_id": f"o_{order_id}",
        "order_id": order_id,
        "customer_id": cid,
        "user_id": str(user["_id"]),
        "order_status": status,
        "status_changed_at": ts,
        "status_history": [{"status": status, "at": ts,
                            "note": "Held for a quick review" if held else "Payment approved"}],
        "order_purchase_timestamp": ts,
        "timeline": {"approved_at": None if held else ts, "shipped_at": None, "delivered_at": None,
                     "estimated_delivery_at": ts + timedelta(days=7)},
        # Olist-shaped fields in reais (what Pipelines A and B read) ...
        "payment": {**{k: v for k, v in payment.items() if k != "decline_reason"},
                    "total_value": to_brl(priced["total"])},
        "line_items": [{**li, "unit_price": to_brl(li["unit_price"]), "freight_value": to_brl(li["freight_value"]),
                        "unit_price_inr": li["unit_price"]} for li in priced["lines"]],
        "items_total": to_brl(priced["subtotal"]),
        "freight_total": to_brl(priced["freight"]),
        "discount": ({**discount, "amount": to_brl(discount["amount"]), "amount_inr": discount["amount"]}
                     if discount else None),
        "total": to_brl(priced["total"]),
        # ... and what the shopper was charged, in rupees, at this order's rate.
        "charged": {"currency": "INR", "inr_per_brl": INR_PER_BRL, "items": priced["subtotal"],
                    "delivery": priced["freight"], "discount": discount["amount"] if discount else 0.0,
                    "total": priced["total"]},
        "shipping_address": body.shipping.model_dump(),
        "risk_at_checkout": {"risk_label": risk, "score": (customer.get("anomaly") or {}).get("score")},
        "source": "app",
    }
    signature = sorted((i["product_id"], int(i["quantity"])) for i in cart["items"])

    def txn(session):
        current = db[COLL_CARTS].find_one({"_id": cid}, session=session) or {"items": []}
        if sorted((i["product_id"], int(i["quantity"])) for i in current.get("items", [])) != signature:
            raise HTTPException(409, "Your cart changed while you were checking out. Please review it.")
        db[COLL_ORDERS].insert_one(order, session=session)
        db[COLL_CARTS].update_one({"_id": cid}, {"$set": {"items": [], "updated_at": ts}}, session=session)
        db[COLL_PRODUCTS].bulk_write([UpdateOne({"product_id": li["product_id"]},
                                                {"$inc": {"sales_count": li["quantity"]}})
                                      for li in priced["lines"]], session=session)
        db[COLL_EVENTS].insert_many([{
            "_id": new_id("e_app_"), "customer_id": cid, "session_id": None, "event_type": "purchase",
            "timestamp": ts, "product_id": li["product_id"], "category": li["category"],
            "metadata": {"channel": "web", "is_synthetic": False, "source": "app", "order_id": order_id},
        } for li in priced["lines"]], session=session)
        db[COLL_CUSTOMERS].update_one({"_id": cid}, {"$set": {"last_order_at": ts}, "$inc": {"order_count": 1}},
                                      session=session)
        notify(db, user["_id"], "order", "Order placed" if not held else "Order received — under review",
               f"Order {order_id[-6:].upper()} for {rupees(priced['total'])}"
               + ("" if not held else ". We're doing a quick check and will update you shortly."),
               link=f"/orders/{order['_id']}", session=session)

    with client.start_session() as session:
        try:
            session.with_transaction(txn)
        except PyMongoError as exc:
            raise HTTPException(503, f"Could not place the order, nothing was charged ({type(exc).__name__}).")
    return order


def cancel_order(db, client, order: dict, by_user_id: str, reason: str, new_status: str = "canceled"):
    """Cancel (customer) or reject (admin) an order: status change + stock/sales
    counters restored + notification, again in one transaction."""
    if order["order_status"] not in CANCELLABLE:
        raise HTTPException(409, f"This order is already {order['order_status']} and can't be cancelled.")
    ts = now()

    def txn(session):
        res = db[COLL_ORDERS].update_one(
            {"_id": order["_id"], "order_status": {"$in": list(CANCELLABLE)}},
            {"$set": {"order_status": new_status, "status_changed_at": ts},
             "$push": {"status_history": {"status": new_status, "at": ts, "note": reason}}},
            session=session)
        if res.modified_count != 1:
            raise HTTPException(409, "This order changed status; please refresh.")
        db[COLL_PRODUCTS].bulk_write([UpdateOne({"product_id": li["product_id"]},
                                                {"$inc": {"sales_count": -li["quantity"]}})
                                      for li in order.get("line_items", [])], session=session)

    with client.start_session() as session:
        session.with_transaction(txn)
    return db[COLL_ORDERS].find_one({"_id": order["_id"]})
