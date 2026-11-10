"""
seed.py — creates the admin account and three demo shopper accounts.

ALL VALUES HERE ARE TEST CREDENTIALS FOR A LOCAL DEMO. Override them with the
ADMIN_EMAIL / ADMIN_PASSWORD / DEMO_PASSWORD environment variables, and never
reuse a real password.

The demo shoppers are linked to REAL Olist customers (anonymised ids, real
order history) chosen by segment, so an evaluator can log in and immediately
see segment-based offers, history-based recommendations and past orders.
The link itself (a login for an anonymised Olist customer) is a demo
convenience and is labelled source="demo" on the user document.
"""

import os

from config import COLL_CUSTOMERS, COLL_RFM, COLL_USERS
from .security import hash_password
from .services.common import now

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@retail-intel.test")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin#2026demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Shopper#2026demo")

DEMO_SHOPPERS = [
    ("loyal@retail-intel.test", "Lara (demo: loyal customer)", "High-Value Loyal", [("frequency", -1), ("monetary", -1)]),
    ("bigspender@retail-intel.test", "Bruno (demo: big spender)", "Big Spender", [("monetary", -1)]),
    ("atrisk@retail-intel.test", "Alice (demo: at-risk customer)", "At-Risk", [("monetary", -1)]),
]


def _pick_customer(db, segment: str, sort):
    """A real customer in `segment` with a sensible history (not an extreme outlier), and
    not currently rated MEDIUM/HIGH risk, so the demo shows the normal checkout path."""
    taken = set(db[COLL_USERS].distinct("customer_id"))
    ids = [c["_id"] for c in db[COLL_CUSTOMERS].find(
        {"segment.label": segment, "source": "olist", "anomaly.risk_label": {"$nin": ["HIGH", "MEDIUM"]}},
        {"_id": 1}).limit(5000)]
    if not ids:
        return None
    query = {"_id": {"$in": ids, "$nin": list(taken)}, "monetary": {"$lte": 2500}}
    row = db[COLL_RFM].find_one(query, sort=sort)
    return row["_id"] if row else None


def seed_users(db) -> dict:
    created = {}
    if not db[COLL_USERS].find_one({"email": ADMIN_EMAIL}):
        db[COLL_USERS].insert_one({"email": ADMIN_EMAIL, "name": "Store admin", "role": "admin",
                                   "password_hash": hash_password(ADMIN_PASSWORD), "customer_id": None,
                                   "created_at": now(), "source": "seed"})
        created["admin"] = ADMIN_EMAIL
    for email, name, segment, sort in DEMO_SHOPPERS:
        if db[COLL_USERS].find_one({"email": email}):
            continue
        cid = _pick_customer(db, segment, sort)
        if not cid:
            continue   # analytics hasn't run yet; seed again after `python ml/run_all.py`
        db[COLL_USERS].insert_one({"email": email, "name": name, "role": "customer", "customer_id": cid,
                                   "password_hash": hash_password(DEMO_PASSWORD), "created_at": now(),
                                   "source": "demo"})
        created[email] = cid
    return created


if __name__ == "__main__":
    from .db import get_db
    print(seed_users(get_db()) or "Accounts already exist.")
