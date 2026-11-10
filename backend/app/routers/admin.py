"""
Admin (operations) area: orders held for review, risk alerts, customer
lookup, and the analytics / synthetic-traffic controls. Admins only.
"""

from datetime import timedelta
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from config import (COLL_AFFINITY, COLL_ALERTS, COLL_CUSTOMERS, COLL_EVENTS, COLL_ML_RUNS, COLL_ORDERS,
                    COLL_RFM, COLL_ROLLING_METRICS, COLL_USERS)
from ..db import get_client, get_db
from ..schemas import SimulatorIn
from ..security import require_admin
from ..services.catalog import category_label
from ..services.checkout import cancel_order
from ..services.common import clean, now
from ..services.money import INR_PER_BRL, inr
from ..services.intelligence import analytics_runner, traffic_simulator
from ..services.personalization import recommendations
from ..services.realtime import manager
from .shopping import order_out

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/overview")
def overview(db=Depends(get_db)):
    day_ago, hour_ago = now() - timedelta(days=1), now() - timedelta(hours=1)
    segments = list(db[COLL_CUSTOMERS].aggregate([
        {"$group": {"_id": {"$ifNull": ["$segment.label", "Unsegmented"]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}]))
    risk = list(db[COLL_CUSTOMERS].aggregate([
        {"$match": {"anomaly.risk_label": {"$ne": None}}},
        {"$group": {"_id": "$anomaly.risk_label", "count": {"$sum": 1}}}]))
    app_orders = list(db[COLL_ORDERS].aggregate([
        {"$match": {"source": "app", "order_purchase_timestamp": {"$gte": day_ago},
                    "order_status": {"$nin": ["canceled", "unavailable"]}}},
        # rupees actually charged; orders placed before the rupee switch are converted
        {"$group": {"_id": None, "orders": {"$sum": 1}, "revenue": {"$sum": {
            "$ifNull": ["$charged.total", {"$multiply": ["$total", INR_PER_BRL]}]}}}}]))
    last_run = db[COLL_ML_RUNS].find_one(sort=[("started_at", -1)])
    return clean({
        "customers": db[COLL_CUSTOMERS].estimated_document_count(),
        "app_customers": db[COLL_CUSTOMERS].count_documents({"source": "app"}),
        "orders_24h": app_orders[0]["orders"] if app_orders else 0,
        "revenue_24h": round(app_orders[0]["revenue"], 2) if app_orders else 0.0,
        "held_orders": db[COLL_ORDERS].count_documents({"order_status": "under_review"}),
        "open_alerts": db[COLL_ALERTS].count_documents({"status": "open"}),
        "events_last_hour": db[COLL_EVENTS].count_documents({"timestamp": {"$gte": hour_ago}}),
        "segments": [{"label": s["_id"], "count": s["count"]} for s in segments],
        "risk": {r["_id"]: r["count"] for r in risk},
        "last_run": last_run,
        "analytics_running": analytics_runner.running,
        "simulator": {"running": traffic_simulator.running, "sessions_per_min": traffic_simulator.sessions_per_min},
    })


@router.get("/orders")
def orders(status: str = "under_review", db=Depends(get_db)):
    query = {"source": "app"} if status == "all" else {"order_status": status}
    rows = list(db[COLL_ORDERS].find(query).sort("order_purchase_timestamp", -1).limit(50))
    cids = list({o["customer_id"] for o in rows})
    risk = {c["_id"]: c.get("anomaly") for c in db[COLL_CUSTOMERS].find({"_id": {"$in": cids}}, {"anomaly": 1})}
    users = {u["customer_id"]: u for u in db[COLL_USERS].find({"customer_id": {"$in": cids}}, {"email": 1, "name": 1, "customer_id": 1})}
    return [order_out(o, detail=False) | clean({
        "customer_id": o["customer_id"], "customer_email": users.get(o["customer_id"], {}).get("email"),
        "customer_name": users.get(o["customer_id"], {}).get("name"),
        "risk": risk.get(o["customer_id"]), "risk_at_checkout": o.get("risk_at_checkout")}) for o in rows]


@router.post("/orders/{order_id}/approve")
def approve(order_id: str, db=Depends(get_db)):
    ts = now()
    res = db[COLL_ORDERS].update_one(
        {"_id": order_id, "order_status": "under_review"},
        {"$set": {"order_status": "processing", "status_changed_at": ts, "timeline.approved_at": ts},
         "$push": {"status_history": {"status": "processing", "at": ts, "note": "Approved after review"}}})
    if res.modified_count != 1:
        raise HTTPException(409, "Only orders under review can be approved.")
    return order_out(db[COLL_ORDERS].find_one({"_id": order_id}))


@router.post("/orders/{order_id}/reject")
def reject(order_id: str, user=Depends(require_admin), db=Depends(get_db)):
    order = db[COLL_ORDERS].find_one({"_id": order_id})
    if not order:
        raise HTTPException(404, "Order not found.")
    return order_out(cancel_order(db, get_client(), order, str(user["_id"]), "Rejected after review"))


@router.get("/alerts")
def alerts(status: str = "open", db=Depends(get_db)):
    query = {} if status == "all" else {"status": status}
    return clean(list(db[COLL_ALERTS].find(query).sort("created_at", -1).limit(50)))


@router.post("/alerts/{alert_id}/resolve")
def resolve(alert_id: str, user=Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(alert_id)
    except InvalidId:
        raise HTTPException(404, "Alert not found.")
    res = db[COLL_ALERTS].update_one({"_id": oid, "status": "open"},
                                     {"$set": {"status": "resolved", "resolved_at": now(),
                                               "resolved_by": user.get("email")}})
    if res.matched_count != 1:
        raise HTTPException(404, "Alert not found or already resolved.")
    return {"resolved": True}


@router.get("/customers")
def find_customers(q: Optional[str] = Query(None, max_length=80), db=Depends(get_db)):
    q = (q or "").strip()
    if not q:
        rows = db[COLL_CUSTOMERS].find({"anomaly.risk_label": "HIGH"}).limit(20)
    else:
        user = db[COLL_USERS].find_one({"email": q.lower()}, {"customer_id": 1})
        ids = [user["customer_id"]] if user else []
        rows = db[COLL_CUSTOMERS].find({"$or": [{"_id": {"$in": ids + [q, f"c_{q}"]}},
                                                {"customer_unique_id": q},
                                                {"customer_city": q.lower()}]}).limit(20)
    return clean([{"customer_id": c["_id"], "city": c.get("customer_city"), "state": c.get("customer_state"),
                   "segment": (c.get("segment") or {}).get("label"),
                   "risk": (c.get("anomaly") or {}).get("risk_label"), "orders": c.get("order_count", 0),
                   "source": c.get("source")} for c in rows])


@router.get("/customers/{customer_id}")
def customer_360(customer_id: str, db=Depends(get_db)):
    c = db[COLL_CUSTOMERS].find_one({"_id": customer_id})
    if not c:
        raise HTTPException(404, "Customer not found.")
    user = db[COLL_USERS].find_one({"customer_id": customer_id}, {"email": 1, "name": 1, "created_at": 1})
    affinity = list(db[COLL_AFFINITY].find({"_id.customer_id": customer_id}).sort("spend", -1).limit(6))
    trend = list(db[COLL_ROLLING_METRICS].find({"customer_id": customer_id}, {"_id": 0}).sort("timestamp", -1).limit(60))
    events = list(db[COLL_EVENTS].find({"customer_id": customer_id}, {"_id": 0}).sort("timestamp", -1).limit(15))
    orders = list(db[COLL_ORDERS].find({"customer_id": customer_id}).sort("order_purchase_timestamp", -1).limit(8))
    rfm = db[COLL_RFM].find_one({"_id": customer_id})
    if rfm:   # Pipeline A works in reais; the screen shows rupees (monetary_brl keeps the model's value)
        rfm = {**rfm, "monetary_brl": rfm.get("monetary"), "monetary": inr(rfm.get("monetary"))}
    return clean({
        "customer": {k: v for k, v in c.items() if k != "olist_customer_ids"},
        "user": {"email": user.get("email"), "name": user.get("name")} if user else None,
        "rfm": rfm,
        "affinity": [{"category": a["_id"]["category"], "label": category_label(db, a["_id"]["category"]),
                      "spend": inr(a.get("spend")), "orders": a.get("orders_touched")} for a in affinity],
        "recommendations": recommendations(db, customer_id, n_categories=3, per_category=2)["categories"],
        "rolling_metrics": list(reversed(trend)),
        "recent_events": events,
        "orders": [order_out(o, detail=False) for o in orders],
        "alerts": list(db[COLL_ALERTS].find({"customer_id": customer_id}).sort("created_at", -1).limit(5)),
    })


@router.post("/analytics/run", status_code=202)
def run_analytics(user=Depends(require_admin), db=Depends(get_db)):
    started = analytics_runner.start(db, triggered_by=user.get("email", "admin"), on_event=manager.push_admins)
    if not started:
        raise HTTPException(409, "An analytics run is already in progress.")
    return {"started": True}


@router.get("/analytics/runs")
def analytics_runs(db=Depends(get_db)):
    return clean(list(db[COLL_ML_RUNS].find().sort("started_at", -1).limit(10)))


@router.get("/simulator")
def simulator_status():
    return {"running": traffic_simulator.running, "sessions_per_min": traffic_simulator.sessions_per_min}


@router.post("/simulator")
def simulator(body: SimulatorIn, db=Depends(get_db)):
    if body.action == "start":
        traffic_simulator.start(db, body.sessions_per_min)
    else:
        traffic_simulator.stop()
    return {"running": traffic_simulator.running, "sessions_per_min": traffic_simulator.sessions_per_min}
