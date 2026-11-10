"""
enrich_products.py
-------------------
Adds `delivery_days` to every product: the MEDIAN number of days from
purchase to delivery across that product's real, delivered Olist orders.
The store uses it for the "FREE delivery Wed, 11 Nov" promise.

It is one aggregation, using MongoDB 7's `$median` accumulator:
  $match delivered orders -> $project days -> $unwind line_items
  -> $group by product with $median -> $merge back into products.
Products with no delivered order get the median over all orders instead.
Called at the end of data/load_olist_data.py; safe to re-run.

Usage:
    python data/enrich_products.py
"""

import math
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_ORDERS, COLL_PRODUCTS  # noqa: E402

DAY_MS = 86_400_000


def enrich_delivery_days(db, verbose: bool = True) -> dict:
    delivered = {"source": "olist", "order_status": "delivered", "order_delivered_timestamp": {"$ne": None}}
    days = {"$divide": [{"$subtract": ["$order_delivered_timestamp", "$order_purchase_timestamp"]}, DAY_MS]}

    overall = list(db[COLL_ORDERS].aggregate([
        {"$match": delivered}, {"$project": {"days": days}},
        {"$group": {"_id": None, "median": {"$median": {"input": "$days", "method": "approximate"}}}},
    ]))
    fallback = math.ceil(overall[0]["median"]) if overall else 10

    db[COLL_ORDERS].aggregate([
        {"$match": delivered},
        {"$project": {"days": days, "line_items.product_id": 1}},
        {"$unwind": "$line_items"},
        {"$group": {"_id": "$line_items.product_id",
                    "median": {"$median": {"input": "$days", "method": "approximate"}}}},
        {"$project": {"_id": 0, "product_id": "$_id", "delivery_days": {"$max": [2, {"$ceil": "$median"}]}}},
        {"$merge": {"into": COLL_PRODUCTS, "on": "product_id", "whenMatched": "merge", "whenNotMatched": "discard"}},
    ], allowDiskUse=True)
    missing = db[COLL_PRODUCTS].update_many({"delivery_days": {"$exists": False}},
                                            {"$set": {"delivery_days": fallback}}).modified_count
    if verbose:
        print(f"delivery_days set from real deliveries (median of all orders: {fallback} days; "
              f"{missing:,} products without a delivered order use it).")
    return {"fallback_days": fallback, "products_using_fallback": missing}


if __name__ == "__main__":
    from config import get_db
    enrich_delivery_days(get_db())
