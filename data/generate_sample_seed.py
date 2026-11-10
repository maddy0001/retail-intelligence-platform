"""
generate_sample_seed.py
------------------------
*** PLACEHOLDER TEST FIXTURE — NOT REAL DATA, NOT SYNTHETIC BEHAVIOURAL DATA ***

Fabricates a small number of customer / order / product documents in the
exact shape defined in schema/schema_design.md, so the automated tests can
exercise the pipelines and ML modules quickly against a throw-away database
(retail_intel_test).

Every document carries `source: "fixture"`. NEVER load this into the real
`retail_intel` database and never cite anything generated here as data in the
report. The report's Data Provenance Statement covers only:
  - REAL: Olist transactional data (source "olist"), via data/load_olist_data.py
  - SYNTHETIC (labelled): clickstream events from simulator/event_simulator.py
  - APP: records created by people using the store (source "app")

Usage (tests call the functions directly):
    MONGO_DB=retail_intel_test python data/generate_sample_seed.py
"""

import random
from datetime import datetime, timedelta, timezone

CATEGORIES = ["electronics", "computers_accessories", "housewares", "sports_leisure",
              "health_beauty", "toys", "furniture_decor", "perfumery"]
STATES = ["SP", "RJ", "MG", "RS", "PR", "BA"]
SOURCE = "fixture"


def _label(cat):
    return cat.replace("_", " ").title()


def gen_products(n=24, rng=random):
    docs = []
    for i in range(n):
        cat = CATEGORIES[i % len(CATEGORIES)]
        price = round(rng.uniform(15, 400), 2)
        docs.append({
            "_id": f"p_fx{i:04d}", "product_id": f"fx{i:04d}",
            "name": f"{_label(cat)} #FX{i:04d}", "category": cat, "category_label": _label(cat),
            "category_pt": cat, "price": price, "price_range": {"min": price, "max": price},
            "freight": round(rng.uniform(5, 30), 2), "sales_count": rng.randint(1, 300),
            "rating_avg": round(rng.uniform(3, 5), 2), "review_count": rng.randint(3, 50),
            "seller": {"seller_id": f"s_fx{i % 5}", "city": "sao paulo", "state": rng.choice(STATES)},
            "photos_qty": 1, "weight_g": 500.0, "dimensions_cm": {"length": 20.0, "height": 10.0, "width": 15.0},
            "source": SOURCE,
        })
    return docs


def gen_customers(n=40, rng=random):
    return [{
        "_id": f"c_fx{i:04d}", "customer_unique_id": f"fx{i:04d}", "customer_city": "sao paulo",
        "customer_state": rng.choice(STATES), "order_count": 0, "source": SOURCE,
        "profile": {"preferred_channel": rng.choice(["mobile_app", "web"])},
        "segment": {"label": None, "cluster_id": None, "method": None, "computed_at": None},
        "anomaly": {"risk_label": None, "score": None, "flags": [], "computed_at": None},
    } for i in range(n)]


def gen_orders(customers, products, n=150, rng=random):
    docs = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        cust = rng.choice(customers)
        lines = []
        for prod in rng.sample(products, rng.randint(1, 3)):
            lines.append({"product_id": prod["product_id"], "category": prod["category"],
                          "category_pt": prod["category_pt"], "seller_id": prod["seller"]["seller_id"],
                          "unit_price": prod["price"], "freight_value": prod["freight"],
                          "quantity": rng.randint(1, 3)})
        items_total = round(sum(li["unit_price"] * li["quantity"] for li in lines), 2)
        purchase_ts = now - timedelta(days=rng.randint(1, 360))
        docs.append({
            "_id": f"o_fx{i:05d}", "order_id": f"fx{i:05d}", "customer_id": cust["_id"],
            "order_status": rng.choices(["delivered", "shipped", "canceled"], weights=[0.85, 0.1, 0.05])[0],
            "order_purchase_timestamp": purchase_ts,
            "order_delivered_timestamp": purchase_ts + timedelta(days=rng.randint(2, 12)),
            "payment": {"type": rng.choice(["credit_card", "boleto", "voucher"]),
                        "installments": rng.randint(1, 6), "total_value": items_total, "methods": []},
            "line_items": lines, "items_total": items_total, "freight_total": 0.0, "source": SOURCE,
        })
    return docs


def seed(db, n_customers=40, n_orders=150, n_products=24, seed_value=7):
    from config import COLL_CUSTOMERS, COLL_ORDERS, COLL_PRODUCTS
    rng = random.Random(seed_value)
    products = gen_products(n_products, rng)
    customers = gen_customers(n_customers, rng)
    orders = gen_orders(customers, products, n_orders, rng)
    for coll_name, docs in [(COLL_PRODUCTS, products), (COLL_CUSTOMERS, customers), (COLL_ORDERS, orders)]:
        db[coll_name].delete_many({"source": SOURCE})
        db[coll_name].insert_many(docs)
    print(f"[PLACEHOLDER FIXTURE] seeded {len(products)} products, {len(customers)} customers, {len(orders)} orders.")
    return customers, products, orders


if __name__ == "__main__":
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import get_db, MONGO_DB
    if MONGO_DB == "retail_intel":
        sys.exit("Refusing to write fixture data into the real database. Set MONGO_DB=retail_intel_test.")
    seed(get_db())
