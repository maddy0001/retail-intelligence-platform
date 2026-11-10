"""
pipeline_b_affinity.py
-----------------------
PIPELINE B — Category / Product Affinity

Course concept demonstrated: $unwind to flatten embedded arrays before
grouping (T13 aggregation pipeline design; T10 aggregation). Produces the
customer x category spend matrix that feeds Module 2 (collaborative
filtering). Categories are the English names carried on every embedded line
item, so recommendations read naturally in the store.

Expected output document shape (one per customer x category pair):
{
  "_id": { "customer_id": "c_861eff47...", "category": "bed_bath_table" },
  "spend": 412.30,
  "units": 5,
  "orders_touched": 3
}
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_ORDERS, COLL_AFFINITY, COMPLETED_STATUSES  # noqa: E402


def build_pipeline(customer_id: str = None):
    match = {"order_status": {"$in": COMPLETED_STATUSES}}
    if customer_id:
        match["customer_id"] = customer_id  # scoped re-run after an app purchase
    return [
        {"$match": match},

        # Stage 1: unwind embedded line_items — this is exactly why
        # line_items were embedded (schema_design.md #2): a single $unwind
        # turns nested arrays into a flat stream MongoDB can group over.
        {"$unwind": "$line_items"},

        # Stage 2: group by (customer, category) to build the affinity matrix.
        {"$group": {
            "_id": {
                "customer_id": "$customer_id",
                "category": "$line_items.category",
            },
            "spend": {
                "$sum": {"$multiply": ["$line_items.unit_price", "$line_items.quantity"]}
            },
            "units": {"$sum": "$line_items.quantity"},
            "orders_touched": {"$addToSet": "$_id"},
        }},
        {"$addFields": {"orders_touched": {"$size": "$orders_touched"}, "spend": {"$round": ["$spend", 2]}}},

        {"$merge": {"into": COLL_AFFINITY, "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def run(db, customer_id: str = None, verbose: bool = True):
    list(db[COLL_ORDERS].aggregate(build_pipeline(customer_id), allowDiskUse=True))
    count = db[COLL_AFFINITY].count_documents({"_id.customer_id": customer_id} if customer_id else {})
    if verbose:
        print(f"Pipeline B complete: {count:,} customer-category affinity rows written to '{COLL_AFFINITY}'.")
    return count


if __name__ == "__main__":
    from config import get_db
    run(get_db())
