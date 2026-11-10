"""
API tests: FastAPI's TestClient against a real MongoDB replica set (the
throw-away `retail_intel_test` database), so transactions really commit and
roll back. Background threads are off; the Change Stream handler and the
fulfilment step are called directly.
"""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from config import (COLL_CARTS, COLL_CATEGORY_SIMILARITY, COLL_CUSTOMERS, COLL_EVENTS, COLL_NOTIFICATIONS, COLL_ORDERS,
                    COLL_PRODUCTS)
from data.generate_sample_seed import gen_products
from backend.app.db import get_db
from backend.app.main import app
from backend.app.seed import ADMIN_EMAIL, ADMIN_PASSWORD
from backend.app.services import realtime
from backend.app.services.common import now
from backend.app.services.fulfillment import advance_orders
from backend.app.services.money import INR_PER_BRL, brl_ceiling, rupees, store_price

GOOD_CARD = {"method": "credit_card", "installments": 2, "card_number": "4242 4242 4242 4242",
             "card_name": "TEST", "expiry": "12/39", "cvv": "123"}
DECLINE_CARD = {**GOOD_CARD, "card_number": "4000 0000 0000 0002"}
SHIP = {"name": "Test Buyer", "street": "Rua Teste, 1", "city": "Sao Paulo", "state": "SP", "zip": "01310-100"}


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "retail_intel_test", "tests must never run against the real database"
    database.client.drop_database(database.name)
    import random
    database[COLL_PRODUCTS].insert_many(gen_products(24, random.Random(3)))
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(scope="module")
def client(db):
    with TestClient(app) as c:     # runs the lifespan: indexes + admin seed
        yield c


def signup(client, **extra):
    body = {"name": "Test Buyer", "email": f"t_{uuid.uuid4().hex[:8]}@retail-intel.test",
            "password": "test-password-1", **extra}
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['token']}"}, data


def admin_headers(client):
    r = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def some_product(db, offset=0):
    return db[COLL_PRODUCTS].find_one(sort=[("product_id", 1)], skip=offset)


# ---- accounts -----------------------------------------------------------------
def test_health_reports_replica_set(client):
    body = client.get("/api/health").json()
    assert body["database"] == "retail_intel_test" and body["replica_set"]


def test_signup_creates_customer_and_user_and_login_works(client, db):
    headers, data = signup(client, city="Campinas", state="sp")
    assert data["customer"]["segment"] == "New Customer"
    assert db[COLL_CUSTOMERS].find_one({"_id": data["customer"]["customer_id"], "source": "app"})
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["offer"]["code"] == "WELCOME10"
    dup = client.post("/api/auth/signup", json={"name": "X Y", "email": data["user"]["email"], "password": "another-pass-1"})
    assert dup.status_code == 409
    bad = client.post("/api/auth/login", json={"email": data["user"]["email"], "password": "wrong-password"})
    assert bad.status_code == 401


def test_protected_routes_need_login_and_admin_role(client):
    assert client.get("/api/cart").status_code == 401
    headers, _ = signup(client)
    assert client.get("/api/admin/overview", headers=headers).status_code == 403
    assert client.get("/api/admin/overview", headers=admin_headers(client)).status_code == 200


# ---- catalogue ----------------------------------------------------------------
def test_search_uses_text_index_and_facets(client):
    body = client.get("/api/products", params={"q": "perfumery", "page_size": 5}).json()
    assert body["total"] > 0
    assert all(i["category"] == "perfumery" for i in body["items"])
    assert {"categories", "price_ranges", "ratings"} <= set(body["facets"])
    fallback = client.get("/api/products", params={"q": "perfum"}).json()   # substring fallback
    assert fallback["total"] > 0
    filtered = client.get("/api/products", params={"category": "toys", "sort": "price_asc"}).json()
    prices = [i["price"] for i in filtered["items"]]
    assert prices == sorted(prices) and all(i["category"] == "toys" for i in filtered["items"])


def test_product_detail_and_unknown_product(client, db):
    pid = some_product(db)["product_id"]
    body = client.get(f"/api/products/{pid}").json()
    assert body["product"]["product_id"] == pid and "breakdown" in body["reviews"]
    assert client.get("/api/products/does-not-exist").status_code == 404


# ---- cart & checkout transaction ----------------------------------------------
def test_checkout_commits_everything_together(client, db):
    headers, data = signup(client)
    cid = data["customer"]["customer_id"]
    product = some_product(db, 1)
    before = product["sales_count"]
    client.post("/api/cart/items", json={"product_id": product["product_id"], "quantity": 2}, headers=headers)
    cart = client.patch(f"/api/cart/items/{product['product_id']}", json={"quantity": 3}, headers=headers).json()
    assert cart["count"] == 3
    preview = client.get("/api/checkout/preview", params={"coupon_code": "WELCOME10"}, headers=headers).json()
    assert preview["discount"]["amount"] == pytest.approx(round(preview["subtotal"] * 0.10, 2))

    r = client.post("/api/checkout", json={"shipping": SHIP, "payment": GOOD_CARD, "coupon_code": "WELCOME10"}, headers=headers)
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "processing" and order["payment"]["card"] == {"brand": "visa", "last4": "4242"}
    assert db[COLL_CARTS].find_one({"_id": cid})["items"] == []
    assert db[COLL_PRODUCTS].find_one({"product_id": product["product_id"]})["sales_count"] == before + 3
    assert db[COLL_EVENTS].count_documents({"customer_id": cid, "event_type": "purchase", "metadata.source": "app"}) == 1
    assert db[COLL_NOTIFICATIONS].count_documents({"user_id": data["user"]["id"], "kind": "order"}) == 1
    stored = db[COLL_ORDERS].find_one({"_id": order["id"]})
    assert "card_number" not in str(stored) and "4242 4242" not in str(stored)   # only brand + last 4 kept
    # charged in rupees; the Olist-shaped fields keep the same amounts in reais for the pipelines
    assert stored["charged"]["currency"] == "INR" and stored["charged"]["total"] == order["total"] == preview["total"]
    assert stored["line_items"][0]["unit_price_inr"] == store_price(product["price"])
    assert stored["total"] == stored["payment"]["total_value"] == pytest.approx(order["total"] / INR_PER_BRL, abs=0.01)
    assert stored["items_total"] == pytest.approx(preview["subtotal"] / INR_PER_BRL, abs=0.01)

    cancelled = client.post(f"/api/orders/{order['id']}/cancel", headers=headers).json()
    assert cancelled["status"] == "canceled"
    assert db[COLL_PRODUCTS].find_one({"product_id": product["product_id"]})["sales_count"] == before


def test_declined_payment_creates_nothing_and_keeps_cart(client, db):
    headers, data = signup(client)
    cid = data["customer"]["customer_id"]
    pid = some_product(db, 2)["product_id"]
    client.post("/api/cart/items", json={"product_id": pid, "quantity": 1}, headers=headers)
    r = client.post("/api/checkout", json={"shipping": SHIP, "payment": DECLINE_CARD}, headers=headers)
    assert r.status_code == 402
    assert db[COLL_ORDERS].count_documents({"customer_id": cid}) == 0
    assert len(db[COLL_CARTS].find_one({"_id": cid})["items"]) == 1
    assert db[COLL_EVENTS].count_documents({"customer_id": cid, "event_type": "payment_failed"}) == 1


def test_bad_card_and_unavailable_coupon_are_rejected(client, db):
    headers, _ = signup(client)
    client.post("/api/cart/items", json={"product_id": some_product(db, 3)["product_id"], "quantity": 1}, headers=headers)
    bad = {**GOOD_CARD, "card_number": "4242 4242 4242 4241"}   # fails the Luhn check
    assert client.post("/api/checkout", json={"shipping": SHIP, "payment": bad}, headers=headers).status_code == 422
    r = client.post("/api/checkout", json={"shipping": SHIP, "payment": GOOD_CARD, "coupon_code": "LOYALSHIP"}, headers=headers)
    assert r.status_code == 422


def test_high_risk_customer_order_is_held_until_admin_approves(client, db):
    headers, data = signup(client)
    cid = data["customer"]["customer_id"]
    db[COLL_CUSTOMERS].update_one({"_id": cid}, {"$set": {"anomaly.risk_label": "HIGH", "anomaly.score": -0.1}})
    client.post("/api/cart/items", json={"product_id": some_product(db, 4)["product_id"], "quantity": 1}, headers=headers)
    order = client.post("/api/checkout", json={"shipping": SHIP, "payment": {"method": "boleto"}}, headers=headers).json()
    assert order["status"] == "under_review"
    admin = admin_headers(client)
    held = client.get("/api/admin/orders", headers=admin).json()
    assert order["id"] in [o["id"] for o in held]
    assert client.post(f"/api/admin/orders/{order['id']}/approve", headers=headers).status_code == 403
    approved = client.post(f"/api/admin/orders/{order['id']}/approve", headers=admin).json()
    assert approved["status"] == "processing"


# ---- pricing rules: M.R.P. from real prices, free delivery ---------------------
def test_rupee_prices_and_formatting():
    assert store_price(89.9) == round(89.9 * INR_PER_BRL)          # whole rupees, like an Indian store
    assert rupees(1600) == "₹1,600" and rupees(1326.6) == "₹1,326.60" and rupees(12.95) == "₹12.95"
    assert rupees(123456.78) == "₹1,23,456.78"                       # Indian digit grouping
    for brl in (0.99, 12.5, 56.17, 89.9, 1234.56):                  # a rupee ceiling maps to the right reais bound
        rs = store_price(brl)
        assert brl < brl_ceiling(rs) and not brl < brl_ceiling(rs - 1)


def test_search_price_filters_and_buckets_are_in_rupees(client, db):
    prices = sorted(store_price(p["price"]) for p in db[COLL_PRODUCTS].find({}, {"price": 1}))
    cap = prices[len(prices) // 2]
    body = client.get("/api/products", params={"max_price": cap, "page_size": 60}).json()
    assert body["total"] == sum(1 for x in prices if x <= cap)
    assert all(i["price"] <= cap for i in body["items"])
    ranges = client.get("/api/products", params={"page_size": 1}).json()["facets"]["price_ranges"]
    assert sum(r["count"] for r in ranges) == len(prices) and all(r["min"] % 500 == 0 for r in ranges)


def test_mrp_comes_from_the_highest_real_price_and_ignores_outliers():
    from backend.app.services.common import mrp_and_discount
    assert mrp_and_discount({"price": 60.0, "price_range": {"max": 100.0}}) == (store_price(100.0), 40)
    assert mrp_and_discount({"price": 60.0, "price_range": {"max": 61.0}}) == (None, None)    # < 5% gap: noise
    assert mrp_and_discount({"price": 60.0, "price_range": {"max": 300.0}}) == (None, None)   # > 60% gap: outlier sale
    assert mrp_and_discount({"price": 60.0, "price_range": {"max": 60.0}}) == (None, None)


def test_free_delivery_over_threshold_or_for_plus_members(client, db):
    from backend.app.services.checkout import FREE_DELIVERY_MIN
    headers, data = signup(client)
    cid = data["customer"]["customer_id"]
    # a product that is under the threshold alone but over it within 20 units (prices are in rupees)
    cheap = db[COLL_PRODUCTS].find_one({"price": {"$gte": FREE_DELIVERY_MIN / 20 / INR_PER_BRL,
                                                  "$lt": FREE_DELIVERY_MIN / 2 / INR_PER_BRL}}, sort=[("price", 1)])
    cart = client.post("/api/cart/items", json={"product_id": cheap["product_id"], "quantity": 1}, headers=headers).json()
    assert cart["delivery"]["free"] is False and cart["freight"] > 0
    assert cart["subtotal"] == store_price(cheap["price"])
    assert cart["delivery"]["add_for_free"] == pytest.approx(round(FREE_DELIVERY_MIN - cart["subtotal"], 2))
    qty = int(FREE_DELIVERY_MIN // cart["subtotal"]) + 1
    cart = client.patch(f"/api/cart/items/{cheap['product_id']}", json={"quantity": qty}, headers=headers).json()
    assert cart["subtotal"] >= FREE_DELIVERY_MIN
    assert cart["delivery"] == {**cart["delivery"], "free": True, "reason": "threshold"} and cart["freight"] == 0
    client.patch(f"/api/cart/items/{cheap['product_id']}", json={"quantity": 1}, headers=headers)
    db[COLL_CUSTOMERS].update_one({"_id": cid}, {"$set": {"segment.label": "High-Value Loyal"}})   # Kartiq Plus
    cart = client.get("/api/cart", headers=headers).json()
    assert cart["delivery"]["free"] is True and cart["delivery"]["reason"] == "plus" and cart["freight"] == 0
    assert client.get("/api/auth/me", headers=headers).json()["is_plus"] is True


def test_taste_graph_links_categories_by_model_similarity(client, db):
    cats = db[COLL_PRODUCTS].distinct("category")[:3]
    db[COLL_CATEGORY_SIMILARITY].delete_many({})
    db[COLL_CATEGORY_SIMILARITY].insert_many([
        {"_id": c, "label": c, "buyers": 10 * (i + 1),
         "similar": [{"category": o, "score": 0.2 / (j + 1)} for j, o in enumerate(x for x in cats if x != c)]}
        for i, c in enumerate(cats)])
    graph = client.get("/api/taste-graph").json()
    ids = {n["id"] for n in graph["nodes"]}
    assert ids == set(cats) and graph["signal"] == "popular" and set(graph["focus"]) <= ids
    assert graph["edges"] and all(e["a"] in ids and e["b"] in ids and 0 < e["w"] <= 1 for e in graph["edges"])
    assert max(e["w"] for e in graph["edges"]) == 1
    assert graph["stats"]["aisles"] == 3 and graph["stats"]["products"] == db[COLL_PRODUCTS].count_documents({})


def test_deals_only_show_real_discounts(client, db):
    db[COLL_PRODUCTS].update_one({}, {"$set": {"price_range.max": 999999.0}})      # an outlier must not become a deal
    items = client.get("/api/deals", params={"limit": 20}).json()["items"]
    assert all(15 <= p["discount_pct"] <= 60 and p["mrp"] > p["price"] for p in items)


# ---- real-time pieces -----------------------------------------------------------
class Recorder:
    def __init__(self):
        self.users, self.admins = [], []

    def push_user(self, user_id, message):
        self.users.append((user_id, message))

    def push_admins(self, message):
        self.admins.append(message)


def test_order_status_change_is_pushed_and_notified(client, db):
    headers, data = signup(client)
    client.post("/api/cart/items", json={"product_id": some_product(db, 5)["product_id"], "quantity": 1}, headers=headers)
    order = client.post("/api/checkout", json={"shipping": SHIP, "payment": {"method": "voucher"}}, headers=headers).json()

    db[COLL_ORDERS].update_one({"_id": order["id"]}, {"$set": {"status_changed_at": now() - timedelta(hours=1)}})
    assert advance_orders(db, step_seconds=20) == 1            # simulated fulfilment step
    doc = db[COLL_ORDERS].find_one({"_id": order["id"]})
    assert doc["order_status"] == "shipped"

    rec = Recorder()
    worker = realtime.ChangeStreamWorker(db, push=rec)
    worker.handle_change({"ns": {"coll": COLL_ORDERS}, "operationType": "update", "fullDocument": doc,
                          "updateDescription": {"updatedFields": {"order_status": "shipped"}}})
    assert any(m["type"] == "order_status" and m["status"] == "shipped" for _, m in rec.users)
    assert db[COLL_NOTIFICATIONS].find_one({"user_id": data["user"]["id"], "title": "Your order is on its way"})


def test_three_abandoned_carts_trigger_one_risk_recompute(db, monkeypatch):
    calls = []
    monkeypatch.setattr(realtime, "recompute_risk", lambda _db, cid, reason: calls.append((cid, reason)) or {"risk_label": "HIGH"})
    rec = Recorder()
    worker = realtime.ChangeStreamWorker(db, push=rec)
    for _ in range(3):
        worker.handle_change({"ns": {"coll": COLL_EVENTS}, "operationType": "insert", "fullDocument": {
            "customer_id": "c_test", "event_type": "cart_abandon", "timestamp": now(), "metadata": {"source": "app"}}})
    assert len(calls) == 1 and calls[0][0] == "c_test"
    assert any(m["type"] == "risk_update" for m in rec.admins)


def test_websocket_requires_a_valid_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=not-a-token") as ws:
            ws.receive_json()
    headers, _ = signup(client)
    token = headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "hello"
