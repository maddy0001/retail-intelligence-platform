"""
pipeline_c_rolling_metrics.py
------------------------------
PIPELINE C — Rolling Behavioral Metrics via $setWindowFields

Course concept demonstrated: MongoDB's $setWindowFields stage (Unit 3,
single-row / window-style functions; T13 pipeline design). This is NOT
generic "window functions" — it is specifically $setWindowFields with:

  - partitionBy: "$customer_id"
        Splits the sorted event stream into one independent window per
        customer, the same way SQL's `PARTITION BY customer_id` would.
  - sortBy: { "timestamp": 1 }
        Orders each partition chronologically so range-based windows
        ("last 7 days") and position-based windows ("previous event") are
        well-defined.
  - output: per-metric window specs, each with its own `window` clause
        (a time RANGE window, a $shift, and DOCUMENTS windows), computed
        independently per customer, per event, without a self-join or a
        client-side loop.
  - a second $setWindowFields stage averages the per-event gap over the
        last 10 events (it depends on a field the first stage produces).

Input: the `events` collection — SYNTHETIC simulator events plus events
produced by people using the app (both labeled in metadata).

Expected output document shape (one per event, enriched with rolling
metrics — Module 3 then reads the latest row per customer):
{
  "_id": "e_00931ab2...",
  "customer_id": "c_861eff47...",
  "timestamp": ISODate(...),
  "event_type": "add_to_cart",
  "rolling_event_count_7d": 14,
  "session_gap_seconds": 41.2,
  "avg_session_gap_seconds": 1830.5,
  "cart_to_purchase_trend": 0.3,
  "cart_abandon_trend": 0.1
}
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_EVENTS, COLL_ROLLING_METRICS  # noqa: E402


def build_pipeline(customer_id: str = None):
    stages = []
    if customer_id:
        # Scoped re-run: the same $setWindowFields logic for one customer, cheap
        # enough to run on every Change Stream trigger in real time.
        stages.append({"$match": {"customer_id": customer_id}})
    stages += [
        {"$sort": {"customer_id": 1, "timestamp": 1}},

        {"$setWindowFields": {
            "partitionBy": "$customer_id",
            "sortBy": {"timestamp": 1},
            "output": {
                # 7-day rolling event count: a RANGE window in *time* units,
                # not document count — every event whose timestamp falls
                # within the trailing 7 days of the current row's timestamp.
                "rolling_event_count_7d": {
                    "$count": {},
                    "window": {"range": [-7, 0], "unit": "day"},
                },

                # The previous event's timestamp in the same partition, via
                # $shift (a document-bound look at exactly the prior row).
                "prev_timestamp": {
                    "$shift": {"output": "$timestamp", "by": -1},
                },

                # Cart-to-purchase conversion trend: fraction of the last 10
                # events (DOCUMENTS window) that were a "purchase", used as a
                # lightweight leading indicator of buying intent.
                "cart_to_purchase_trend": {
                    "$avg": {"$cond": [{"$eq": ["$event_type", "purchase"]}, 1, 0]},
                    "window": {"documents": [-9, 0]},
                },

                # Abandonment trend: fraction of the last 10 events that were
                # an abandoned cart/checkout (same DOCUMENTS window).
                "cart_abandon_trend": {
                    "$avg": {"$cond": [{"$eq": ["$event_type", "cart_abandon"]}, 1, 0]},
                    "window": {"documents": [-9, 0]},
                },
            },
        }},

        # Derive the gap since the previous event in seconds from the shifted timestamp.
        {"$addFields": {
            "session_gap_seconds": {
                "$cond": [
                    {"$eq": ["$prev_timestamp", None]},
                    None,
                    {"$divide": [{"$subtract": ["$timestamp", "$prev_timestamp"]}, 1000]},
                ]
            }
        }},

        # A second $setWindowFields stage: the AVERAGE gap over the last 10
        # events. It needs session_gap_seconds, which only exists after the
        # first stage, so it cannot live in the same stage. ($avg skips the
        # null gap of a customer's very first event.)
        {"$setWindowFields": {
            "partitionBy": "$customer_id",
            "sortBy": {"timestamp": 1},
            "output": {
                "avg_session_gap_seconds": {
                    "$avg": "$session_gap_seconds",
                    "window": {"documents": [-9, 0]},
                },
            },
        }},

        {"$project": {
            "customer_id": 1,
            "timestamp": 1,
            "event_type": 1,
            "rolling_event_count_7d": 1,
            "session_gap_seconds": 1,
            "avg_session_gap_seconds": 1,
            "cart_to_purchase_trend": 1,
            "cart_abandon_trend": 1,
        }},

        {"$merge": {"into": COLL_ROLLING_METRICS, "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]
    return stages


def run(db, customer_id: str = None, verbose: bool = True):
    list(db[COLL_EVENTS].aggregate(build_pipeline(customer_id), allowDiskUse=True))
    count = db[COLL_ROLLING_METRICS].count_documents({"customer_id": customer_id} if customer_id else {})
    if verbose:
        print(f"Pipeline C complete: {count:,} rolling-metric rows written to '{COLL_ROLLING_METRICS}'.")
    return count


if __name__ == "__main__":
    from config import get_db
    run(get_db())
