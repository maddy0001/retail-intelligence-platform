"""
realtime.py — MongoDB Change Streams -> WebSocket push.

One background thread opens a single Change Stream on the database, filtered
to the four collections the app reacts to, and turns each change into a push
to the right browser tabs:

  events (insert)          -> admin live-activity feed; behaviour thresholds:
                              3+ abandoned carts in 30 min, or 2+ declined
                              payments in 10 min, trigger a scoped
                              $setWindowFields re-run + live Isolation Forest
                              score for that customer (and an alert if HIGH)
  orders (insert/update)   -> new-order feed for admins; a status change is
                              pushed to the customer's open tabs and stored as
                              a notification; "shipped" also refreshes the
                              customer's RFM segment
  notifications (insert)   -> the user's notification bell, instantly
  alerts (insert)          -> the admin's alert list, instantly

Nothing polls: the stream tails MongoDB's oplog, so quiet periods cost zero
queries — the RDBMS alternative would be polling or a trigger plus a queue.
Change Streams need a replica set (a single-node one is enough).
"""

import asyncio
import logging
import threading
from collections import defaultdict, deque
from datetime import timedelta

from pymongo.errors import PyMongoError

from config import COLL_ALERTS, COLL_EVENTS, COLL_NOTIFICATIONS, COLL_ORDERS
from ..settings import settings
from .activity import notify
from .checkout import charged_amounts
from .common import clean, now
from .intelligence import recompute_risk, refresh_after_purchase

log = logging.getLogger("retail.realtime")

STATUS_MESSAGES = {
    "processing": ("Order approved", "Your order passed review and is being prepared."),
    "shipped": ("Your order is on its way", "It has been handed to the carrier."),
    "delivered": ("Delivered!", "Enjoy your purchase. You can now leave a review."),
    "canceled": ("Order canceled", "Any payment will be returned to your original method."),
}


class ConnectionManager:
    """Open WebSockets per user, plus the set of admin sockets. Thread-safe
    push helpers let the Change Stream thread hand messages to the event loop."""

    def __init__(self):
        self.loop = None
        self.users = defaultdict(set)
        self.admins = set()

    async def connect(self, ws, user: dict):
        await ws.accept()
        self.users[str(user["_id"])].add(ws)
        if user.get("role") == "admin":
            self.admins.add(ws)

    def disconnect(self, ws, user: dict):
        self.users[str(user["_id"])].discard(ws)
        self.admins.discard(ws)

    async def _send(self, sockets, message: dict):
        for ws in list(sockets):
            try:
                await ws.send_json(message)
            except Exception:  # closed tab: forget the socket
                for group in [self.admins, *self.users.values()]:
                    group.discard(ws)

    def push_user(self, user_id, message: dict):
        sockets = set(self.users.get(str(user_id), ()))
        if self.loop and sockets:
            asyncio.run_coroutine_threadsafe(self._send(sockets, clean(message)), self.loop)

    def push_admins(self, message: dict):
        if self.loop and self.admins:
            asyncio.run_coroutine_threadsafe(self._send(set(self.admins), clean(message)), self.loop)


manager = ConnectionManager()


class ThresholdCounter:
    """Sliding-window counts per (customer, event type), kept in memory."""

    def __init__(self):
        self._hits = defaultdict(deque)

    def hit(self, key, ts, window: timedelta) -> int:
        dq = self._hits[key]
        dq.append(ts)
        while dq and dq[0] < ts - window:
            dq.popleft()
        return len(dq)

    def reset(self, key):
        self._hits.pop(key, None)


class ChangeStreamWorker(threading.Thread):
    WATCHED = [COLL_EVENTS, COLL_ORDERS, COLL_NOTIFICATIONS, COLL_ALERTS]

    def __init__(self, db, push=manager):
        super().__init__(name="change-stream-worker", daemon=True)
        self.db = db
        self.push = push
        self.counter = ThresholdCounter()
        self._stop = threading.Event()
        self.ready = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        pipeline = [{"$match": {"ns.coll": {"$in": self.WATCHED},
                                "operationType": {"$in": ["insert", "update", "replace"]}}}]
        resume_token = None
        while not self._stop.is_set():
            try:
                with self.db.watch(pipeline, full_document="updateLookup", resume_after=resume_token,
                                   max_await_time_ms=1000) as stream:
                    self.ready.set()
                    log.info("Change Stream open on %s", ", ".join(self.WATCHED))
                    while not self._stop.is_set():
                        change = stream.try_next()
                        if change is None:
                            continue
                        resume_token = stream.resume_token
                        try:
                            self.handle_change(change)
                        except Exception:
                            log.exception("failed to handle change on %s", change.get("ns"))
            except PyMongoError as exc:
                log.warning("Change Stream interrupted (%s); reconnecting", exc)
                self._stop.wait(2)

    # ---- dispatch ---------------------------------------------------------
    def handle_change(self, change: dict):
        coll = change["ns"]["coll"]
        op = change["operationType"]
        doc = change.get("fullDocument") or {}
        if coll == COLL_EVENTS and op == "insert":
            self.on_event(doc)
        elif coll == COLL_ORDERS:
            self.on_order(op, doc, (change.get("updateDescription") or {}).get("updatedFields") or {})
        elif coll == COLL_NOTIFICATIONS and op == "insert":
            self.push.push_user(doc.get("user_id"), {"type": "notification", "notification": doc})
        elif coll == COLL_ALERTS and op == "insert":
            self.push.push_admins({"type": "alert", "alert": doc})

    def on_event(self, ev: dict):
        meta = ev.get("metadata") or {}
        self.push.push_admins({"type": "activity", "event": {
            "event_type": ev.get("event_type"), "customer_id": ev.get("customer_id"),
            "category": ev.get("category"), "source": meta.get("source"), "timestamp": ev.get("timestamp")}})

        rules = {
            "cart_abandon": (settings.abandon_threshold, settings.abandon_window_minutes,
                             f"{settings.abandon_threshold}+ abandoned carts in {settings.abandon_window_minutes} min"),
            "payment_failed": (settings.payment_fail_threshold, settings.payment_fail_window_minutes,
                               f"{settings.payment_fail_threshold}+ declined payments in "
                               f"{settings.payment_fail_window_minutes} min"),
        }
        rule = rules.get(ev.get("event_type"))
        if not rule:
            return
        threshold, minutes, reason = rule
        key = (ev["customer_id"], ev["event_type"])
        ts = ev.get("timestamp") or now()
        if self.counter.hit(key, ts, timedelta(minutes=minutes)) >= threshold:
            self.counter.reset(key)
            result = recompute_risk(self.db, ev["customer_id"], reason)
            self.push.push_admins({"type": "risk_update", "customer_id": ev["customer_id"],
                                   "reason": reason, "result": result})

    def on_order(self, op: str, order: dict, updated: dict):
        summary = {"order_id": order.get("_id"), "customer_id": order.get("customer_id"),
                   "status": order.get("order_status"), "total": charged_amounts(order)["total"],
                   "source": order.get("source")}
        if op == "insert" and order.get("source") == "app":
            self.push.push_admins({"type": "order_created", "order": summary})
            return
        if op != "update" or "order_status" not in updated:
            return
        status = updated["order_status"]
        self.push.push_admins({"type": "order_status", "order": summary})
        user_id = order.get("user_id")
        if not user_id:
            return
        self.push.push_user(user_id, {"type": "order_status", "order_id": order["_id"], "status": status,
                                      "status_history": order.get("status_history", [])})
        title, body = STATUS_MESSAGES.get(status, (f"Order {status}", ""))
        notify(self.db, user_id, "order", title, f"Order {order['_id'][-6:].upper()}: {body}",
               link=f"/orders/{order['_id']}")
        if status == "shipped":   # the order now counts as a completed purchase for RFM
            refresh_after_purchase(self.db, order["customer_id"], user_id)
