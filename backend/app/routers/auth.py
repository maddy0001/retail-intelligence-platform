"""Sign-up, login and the current user."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from config import COLL_CUSTOMERS, COLL_USERS
from ..db import get_client, get_db
from ..schemas import LoginIn, SignupIn
from ..security import create_token, current_user, hash_password, public_user, verify_password
from ..services.activity import notify
from ..services.checkout import FREE_DELIVERY_MIN, is_plus, offer_for
from ..services.common import now

router = APIRouter(prefix="/api/auth", tags=["auth"])


def customer_summary(customer: dict) -> dict:
    if not customer:
        return {}
    return {"customer_id": customer["_id"], "city": customer.get("customer_city"),
            "state": customer.get("customer_state"), "segment": (customer.get("segment") or {}).get("label"),
            "order_count": customer.get("order_count", 0), "source": customer.get("source")}


@router.post("/signup", status_code=201)
def signup(body: SignupIn, db=Depends(get_db)):
    if db[COLL_USERS].find_one({"email": body.email}):
        raise HTTPException(409, "An account with this email already exists. Try logging in.")
    ts, key = now(), uuid.uuid4().hex[:16]
    customer = {
        "_id": f"c_app_{key}", "customer_unique_id": f"app_{key}",
        "customer_city": (body.city or "").strip().lower() or None, "customer_state": body.state,
        "customer_zip_prefix": None, "first_order_at": None, "last_order_at": None, "order_count": 0,
        "source": "app", "created_at": ts, "profile": {"preferred_channel": "web"},
        # Rule-based until the first completed order gives K-Means something to work with.
        "segment": {"label": "New Customer", "cluster_id": None, "method": "rule", "computed_at": ts},
        "anomaly": {"risk_label": None, "score": None, "flags": [], "computed_at": None},
    }
    user = {"email": body.email, "name": body.name.strip(), "password_hash": hash_password(body.password),
            "role": "customer", "customer_id": customer["_id"], "created_at": ts, "source": "app"}

    # The customer profile and the login account are created together or not at all.
    with get_client().start_session() as session:
        try:
            def txn(s):
                db[COLL_CUSTOMERS].insert_one(customer, session=s)
                user["_id"] = db[COLL_USERS].insert_one(user, session=s).inserted_id
            session.with_transaction(txn)
        except DuplicateKeyError:
            raise HTTPException(409, "An account with this email already exists. Try logging in.")

    notify(db, user["_id"], "welcome", f"Welcome, {user['name'].split()[0]}!",
           "Your first order is 10% off with code WELCOME10.", link="/")
    return {"token": create_token(user), "user": public_user(user), "customer": customer_summary(customer)}


@router.post("/login")
def login(body: LoginIn, db=Depends(get_db)):
    user = db[COLL_USERS].find_one({"email": body.email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(401, "Email or password is incorrect.")
    customer = db[COLL_CUSTOMERS].find_one({"_id": user.get("customer_id")}) if user.get("customer_id") else None
    return {"token": create_token(user), "user": public_user(user), "customer": customer_summary(customer)}


@router.get("/me")
def me(user=Depends(current_user), db=Depends(get_db)):
    customer = db[COLL_CUSTOMERS].find_one({"_id": user.get("customer_id")}) if user.get("customer_id") else None
    return {"user": public_user(user), "customer": customer_summary(customer),
            "offer": offer_for(customer) if customer else None,
            "is_plus": is_plus(customer) if customer else False, "free_delivery_min": FREE_DELIVERY_MIN}
