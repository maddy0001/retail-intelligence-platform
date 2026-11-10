"""
activity.py — writing app events and user notifications.

Events produced by people using the store are labelled
metadata.source = "app" and metadata.is_synthetic = false, so they are never
confused with the simulator's synthetic events or with real Olist orders.
"""

from config import COLL_EVENTS, COLL_NOTIFICATIONS
from .common import new_id, now


def record_event(db, customer_id: str, event_type: str, product_id: str = None, category: str = None,
                 extra: dict = None, session=None) -> dict:
    doc = {
        "_id": new_id("e_app_"),
        "customer_id": customer_id,
        "session_id": None,
        "event_type": event_type,
        "timestamp": now(),
        "product_id": product_id,
        "category": category,
        "metadata": {"channel": "web", "is_synthetic": False, "source": "app", **(extra or {})},
    }
    db[COLL_EVENTS].insert_one(doc, session=session)
    return doc


def notify(db, user_id, kind: str, title: str, body: str = "", link: str = None, session=None) -> dict:
    """Store a notification. The Change Stream worker pushes it to the user's
    open browser tabs; the TTL index removes it after 30 days."""
    doc = {"user_id": str(user_id), "kind": kind, "title": title, "body": body, "link": link,
           "read": False, "created_at": now()}
    db[COLL_NOTIFICATIONS].insert_one(doc, session=session)
    return doc
