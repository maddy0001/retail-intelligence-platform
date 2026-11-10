"""
pipeline_a_rfm.py
------------------
PIPELINE A — RFM Feature Computation

Course concept demonstrated: multi-stage aggregation pipeline design
(T13), including $group accumulators and a $lookup join back to a reference
collection (T10 aggregation). Groups completed orders by customer to compute
Recency / Frequency / Monetary value, then attaches customer profile fields.

Customers are real people (one document per Olist customer_unique_id, or one
per app sign-up), so Frequency counts a person's repeat orders.

Recency reference date: the Olist data ends in October 2018, so recency for
historical customers is measured from the end of that dataset (the day after
its last order). If a customer's latest order was placed in the app (after
that date), recency is measured from "now" instead. Measuring 2018 orders from
today's date would make every historical customer look ~8 years inactive.

Expected output document shape (one per customer with >=1 completed order):
{
  "_id": "c_861eff4711a542e4b93843c6dd7febb0",
  "recency_days": 12.4,
  "frequency": 2,
  "monetary": 412.80,
  "first_order_date": ISODate(...),
  "last_order_date": ISODate(...),
  "customer_profile": { "customer_city": "franca", "customer_state": "SP", "source": "olist" }
}
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_ORDERS, COLL_CUSTOMERS, COLL_RFM, COMPLETED_STATUSES  # noqa: E402

DAY_MS = 1000 * 60 * 60 * 24


def historical_as_of(db) -> datetime:
    """The day after the last real Olist order (the end of the historical data)."""
    doc = db[COLL_ORDERS].find_one({"source": "olist"}, {"order_purchase_timestamp": 1},
                                   sort=[("order_purchase_timestamp", -1)])
    if not doc or not doc.get("order_purchase_timestamp"):
        return datetime.now(timezone.utc)
    ts = doc["order_purchase_timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts + timedelta(days=1)


def build_pipeline(as_of_historical: datetime, now: datetime, customer_id: str = None):
    match = {"order_status": {"$in": COMPLETED_STATUSES}}
    if customer_id:
        match["customer_id"] = customer_id  # scoped re-run for one customer (used live by the API)
    return [
        # Stage 1: only completed orders count toward loyalty or spend.
        {"$match": match},

        # Stage 2: group by customer, computing R/F/M in one pass.
        {"$group": {
            "_id": "$customer_id",
            "first_order_date": {"$min": "$order_purchase_timestamp"},
            "last_order_date": {"$max": "$order_purchase_timestamp"},
            "frequency": {"$sum": 1},
            "monetary": {"$sum": {"$ifNull": ["$payment.total_value", 0]}},
        }},

        # Stage 3: recency in days, from the right reference date (see docstring).
        {"$addFields": {
            "as_of": {"$cond": [{"$gt": ["$last_order_date", as_of_historical]}, now, as_of_historical]},
        }},
        {"$addFields": {
            "recency_days": {"$divide": [{"$subtract": ["$as_of", "$last_order_date"]}, DAY_MS]},
            "monetary": {"$round": ["$monetary", 2]},
        }},

        # Stage 4: $lookup join to attach profile fields from customers.
        {"$lookup": {
            "from": COLL_CUSTOMERS,
            "localField": "_id",
            "foreignField": "_id",
            "as": "customer_doc",
        }},
        {"$unwind": "$customer_doc"},
        {"$addFields": {
            "customer_profile": {
                "customer_city": "$customer_doc.customer_city",
                "customer_state": "$customer_doc.customer_state",
                "source": "$customer_doc.source",
            }
        }},
        {"$project": {"customer_doc": 0, "as_of": 0}},

        # Stage 5: write the result set into rfm_features for the ML module
        # to read via pymongo -> pandas. Keeps every model traceable to a
        # named aggregation output rather than raw collections.
        {"$merge": {"into": COLL_RFM, "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def run(db, now: datetime = None, customer_id: str = None, verbose: bool = True):
    now = now or datetime.now(timezone.utc)
    pipeline = build_pipeline(historical_as_of(db), now, customer_id)
    list(db[COLL_ORDERS].aggregate(pipeline, allowDiskUse=True))
    count = db[COLL_RFM].count_documents({"_id": customer_id} if customer_id else {})
    if verbose:
        print(f"Pipeline A complete: {count:,} customer RFM documents written to '{COLL_RFM}'.")
    return count


if __name__ == "__main__":
    from config import get_db
    run(get_db())
