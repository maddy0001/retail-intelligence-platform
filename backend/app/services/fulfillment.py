"""
fulfillment.py — SIMULATED order fulfilment for the demo.

There is no warehouse or carrier behind this store, so a background thread
moves app orders along: processing -> shipped -> delivered, one step every
FULFILLMENT_STEP_SECONDS (20 s by default). Each step is an ordinary update on
the order; the Change Stream worker sees it and pushes the new status to the
customer's browser, which is what makes order tracking update live.
"""

import logging
import threading
from datetime import timedelta

from pymongo.errors import PyMongoError

from config import COLL_ORDERS
from .common import now

log = logging.getLogger("retail.fulfillment")

STEPS = [
    ("processing", "shipped", "timeline.shipped_at", "Handed to the carrier"),
    ("shipped", "delivered", "timeline.delivered_at", "Delivered to the shipping address"),
]


def advance_orders(db, step_seconds: int) -> int:
    moved = 0
    cutoff = now() - timedelta(seconds=step_seconds)
    for current, nxt, field, note in STEPS:
        for order in db[COLL_ORDERS].find({"source": "app", "order_status": current,
                                           "status_changed_at": {"$lte": cutoff}}, {"_id": 1}):
            ts = now()
            update = {"$set": {"order_status": nxt, "status_changed_at": ts, field: ts},
                      "$push": {"status_history": {"status": nxt, "at": ts, "note": note}}}
            if nxt == "delivered":
                update["$set"]["order_delivered_timestamp"] = ts
            res = db[COLL_ORDERS].update_one({"_id": order["_id"], "order_status": current}, update)
            moved += res.modified_count
    return moved


class FulfillmentWorker(threading.Thread):
    def __init__(self, db, step_seconds: int):
        super().__init__(name="fulfillment-simulator", daemon=True)
        self.db = db
        self.step_seconds = step_seconds
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.wait(3):
            try:
                advance_orders(self.db, self.step_seconds)
            except PyMongoError as exc:
                log.warning("fulfilment step skipped: %s", exc)
