"""
intelligence.py — runs the analytics from inside the app.

  * refresh_after_purchase: after an app order, re-run Pipeline A and B scoped
    to that one customer and place them in a K-Means segment with the saved
    model, so their offer and recommendations update immediately.
  * recompute_risk: re-run Pipeline C ($setWindowFields) scoped to one
    customer and score them with the saved Isolation Forest. Called by the
    Change Stream worker when a behaviour threshold is crossed.
  * AnalyticsRunner / TrafficSimulator: admin-triggered background jobs (the
    full analytics chain, and a live synthetic-traffic stream for demos).
"""

import logging
import threading

from config import COLL_ALERTS, COLL_CUSTOMERS, COLL_USERS
from ml import module1_kmeans, module3_isolation_forest
from ml.run_all import run_all
from pipelines import pipeline_a_rfm, pipeline_b_affinity, pipeline_c_rolling_metrics
from simulator.event_simulator import run_live
from .activity import notify
from .common import now
from .personalization import invalidate_model

log = logging.getLogger("retail.intelligence")


def refresh_after_purchase(db, customer_id: str, user_id=None):
    before = ((db[COLL_CUSTOMERS].find_one({"_id": customer_id}, {"segment": 1}) or {})
              .get("segment") or {}).get("label")
    pipeline_a_rfm.run(db, customer_id=customer_id, verbose=False)
    pipeline_b_affinity.run(db, customer_id=customer_id, verbose=False)
    label = module1_kmeans.assign_segment(db, customer_id)
    if label and label != before and user_id:
        from .checkout import OFFERS
        offer = OFFERS.get(label)
        notify(db, user_id, "offer", f"New perk unlocked: {offer['title']}" if offer else "Your perks were updated",
               f"Use code {offer['code']} at checkout." if offer else "", link="/")
    return label


def recompute_risk(db, customer_id: str, reason: str) -> dict:
    """Scoped $setWindowFields re-run + live Isolation Forest score; raise an alert on HIGH."""
    before = ((db[COLL_CUSTOMERS].find_one({"_id": customer_id}, {"anomaly": 1}) or {})
              .get("anomaly") or {}).get("risk_label")
    pipeline_c_rolling_metrics.run(db, customer_id=customer_id, verbose=False)
    scored = module3_isolation_forest.score_customer(db, customer_id)
    if not scored:
        return {"risk_label": before, "changed": False}
    db[COLL_CUSTOMERS].update_one({"_id": customer_id}, {"$addToSet": {"anomaly.flags": reason}})
    if scored["risk_label"] == "HIGH" and not db[COLL_ALERTS].find_one({"customer_id": customer_id, "status": "open"}):
        user = db[COLL_USERS].find_one({"customer_id": customer_id}, {"email": 1, "name": 1})
        db[COLL_ALERTS].insert_one({
            "customer_id": customer_id, "user_email": (user or {}).get("email"),
            "risk_label": scored["risk_label"], "score": scored["score"], "previous_label": before,
            "reason": reason, "features": scored["features"], "status": "open", "created_at": now(),
        })
    return {**scored, "previous_label": before, "changed": scored["risk_label"] != before}


class AnalyticsRunner:
    """Runs ml/run_all.py's chain in a background thread, one run at a time."""

    def __init__(self):
        self._thread = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, db, triggered_by: str, on_event=None) -> bool:
        with self._lock:
            if self.running:
                return False

            def work():
                try:
                    run_all(db, triggered_by=triggered_by, log=log.info,
                            on_step=(lambda step: on_event and on_event({"type": "analytics_step", "step": step})))
                    invalidate_model()
                    on_event and on_event({"type": "analytics_done", "status": "succeeded"})
                except Exception as exc:  # recorded in ml_runs by run_all
                    log.exception("analytics run failed")
                    on_event and on_event({"type": "analytics_done", "status": "failed", "error": str(exc)})

            self._thread = threading.Thread(target=work, name="analytics-run", daemon=True)
            self._thread.start()
            return True


class TrafficSimulator:
    """Streams SYNTHETIC sessions (simulator/event_simulator.py live mode) so the
    Change Stream features can be shown without a second terminal."""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self.sessions_per_min = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, db, sessions_per_min: int):
        self.stop()
        self._stop = threading.Event()
        self.sessions_per_min = sessions_per_min
        self._thread = threading.Thread(target=run_live, name="traffic-simulator", daemon=True,
                                        kwargs={"db": db, "sessions_per_min": sessions_per_min,
                                                "stop_event": self._stop, "log": log.info})
        self._thread.start()

    def stop(self):
        if self.running:
            self._stop.set()
            self._thread.join(timeout=5)
        self.sessions_per_min = 0


analytics_runner = AnalyticsRunner()
traffic_simulator = TrafficSimulator()
