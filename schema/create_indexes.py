"""
create_indexes.py
------------------
Creates every index called for in schema_design.md. Idempotent — safe to
run repeatedly (create_index is a no-op if an identical index exists).

Read-heavy collections (products, customers, orders, reviews) get the indexes
their query patterns need; the write-heavy `events` collection gets only the
one compound index $setWindowFields needs, because every extra index slows
every insert.

Usage:
    python schema/create_indexes.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import ASCENDING, DESCENDING, TEXT  # noqa: E402

from config import (  # noqa: E402
    get_db, COLL_CUSTOMERS, COLL_ORDERS, COLL_PRODUCTS, COLL_REVIEWS, COLL_EVENTS,
    COLL_USERS, COLL_CARTS, COLL_NOTIFICATIONS, COLL_ALERTS, COLL_ROLLING_METRICS,
    COLL_AFFINITY,
)

NOTIFICATION_TTL_SECONDS = 30 * 24 * 3600  # notifications expire after 30 days

# Indexes from the first (Aug 2026) version of the schema that the current
# design replaces; dropped so each collection carries only indexes it uses.
LEGACY_INDEXES = {
    COLL_CUSTOMERS: ["idx_customer_unique_id", "idx_segment_cluster"],
    COLL_ORDERS: ["idx_line_item_category"],
    COLL_PRODUCTS: ["idx_product_category"],
}


def drop_legacy_indexes(db):
    for coll_name, names in LEGACY_INDEXES.items():
        existing = {idx["name"] for idx in db[coll_name].list_indexes()}
        for name in names:
            if name in existing:
                db[coll_name].drop_index(name)


def create_indexes(db, verbose: bool = True):
    drop_legacy_indexes(db)
    customers = db[COLL_CUSTOMERS]
    # Unique now: there is exactly one customer document per real person
    # (customer_unique_id). App sign-ups get their own generated id.
    customers.create_index("customer_unique_id", unique=True, name="uniq_customer_unique_id")
    customers.create_index("segment.label", name="idx_segment_label")
    customers.create_index("anomaly.risk_label", name="idx_anomaly_risk")

    orders = db[COLL_ORDERS]
    orders.create_index([("customer_id", ASCENDING), ("order_purchase_timestamp", DESCENDING)],
                        name="idx_customer_recency")
    orders.create_index("order_status", name="idx_order_status")
    orders.create_index("line_items.product_id", name="idx_line_item_product")
    orders.create_index([("source", ASCENDING), ("order_status", ASCENDING)], name="idx_source_status")

    products = db[COLL_PRODUCTS]
    products.create_index("product_id", unique=True, name="uniq_product_id")
    products.create_index([("category", ASCENDING), ("sales_count", DESCENDING)], name="idx_category_popularity")
    products.create_index([("sales_count", DESCENDING)], name="idx_popularity")
    products.create_index([("price", ASCENDING)], name="idx_price")
    # Full-text search for the store's search box ($text). Weights make a name
    # or category match count more than the Portuguese category name.
    products.create_index(
        [("name", TEXT), ("category_label", TEXT), ("category", TEXT), ("category_pt", TEXT)],
        weights={"name": 10, "category_label": 8, "category": 5, "category_pt": 2},
        default_language="english", name="txt_product_search",
    )

    reviews = db[COLL_REVIEWS]
    reviews.create_index([("product_id", ASCENDING), ("created_at", DESCENDING)], name="idx_product_reviews")
    reviews.create_index([("customer_id", ASCENDING)], name="idx_review_customer")

    events = db[COLL_EVENTS]
    events.create_index([("customer_id", ASCENDING), ("timestamp", ASCENDING)],
                        name="idx_customer_timestamp")  # required for $setWindowFields perf
    events.create_index("timestamp", name="idx_timestamp")

    users = db[COLL_USERS]
    users.create_index("email", unique=True, name="uniq_email")
    users.create_index("customer_id", name="idx_user_customer")

    # carts: _id IS the customer id (one cart per customer) -> no extra index needed.
    db[COLL_CARTS].create_index("updated_at", name="idx_cart_updated")

    notifications = db[COLL_NOTIFICATIONS]
    notifications.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_notifications")
    notifications.create_index("created_at", expireAfterSeconds=NOTIFICATION_TTL_SECONDS,
                               name="ttl_notifications_30d")

    alerts = db[COLL_ALERTS]
    alerts.create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="idx_alert_status")

    db[COLL_ROLLING_METRICS].create_index([("customer_id", ASCENDING), ("timestamp", ASCENDING)],
                                          name="idx_customer_timestamp")
    db[COLL_AFFINITY].create_index("_id.customer_id", name="idx_affinity_customer")

    if verbose:
        print("All indexes created.")
        for coll_name in [COLL_CUSTOMERS, COLL_ORDERS, COLL_PRODUCTS, COLL_REVIEWS, COLL_EVENTS,
                          COLL_USERS, COLL_CARTS, COLL_NOTIFICATIONS, COLL_ALERTS]:
            print(f"\n{coll_name}:")
            for idx in db[coll_name].list_indexes():
                extra = f" (TTL {idx['expireAfterSeconds']}s)" if "expireAfterSeconds" in idx else ""
                extra += " (unique)" if idx.get("unique") else ""
                print(f"  - {idx['name']}: {dict(idx['key'])}{extra}")


if __name__ == "__main__":
    create_indexes(get_db())
