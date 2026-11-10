"""
personalization.py — "Recommended for you" and the home feed.

Recommendations use Module 2's saved category similarities
(`category_similarity`, built from Pipeline B's affinity matrix) with the
popularity blend weight Module 2 chose on validation data:
  * customers with purchases: their category spend from `category_affinity`;
  * new sign-ups with no purchases yet: categories they have viewed in this
    store (app events) act as a light implicit signal (cold start);
  * nobody with any signal: best-sellers.
Products shown for a recommended category are its best-sellers with a 4+ star
real Olist rating, excluding things the customer already bought.
"""

import threading
import time

from config import COLL_AFFINITY, COLL_CATEGORY_SIMILARITY, COLL_CUSTOMERS, COLL_EVENTS, COLL_ORDERS
from ml.module2_collaborative_filtering import load_saved_model, recommend_categories
from .catalog import category_label, list_categories, popular_products
from .checkout import offer_for

# One product view counts like R$20 of spend (the analytics stay in the catalogue's reais).
VIEW_WEIGHT = 20.0
BUDGET_MAX = 999     # the "Great finds under ₹999" rail, in store rupees

_model = {"at": 0.0, "sim": None, "popular": None, "alpha": 0.0}
_lock = threading.Lock()


def invalidate_model():
    with _lock:
        _model["at"] = 0.0


def _load_model(db, ttl_seconds=600):
    with _lock:
        if _model["sim"] is None or time.time() - _model["at"] > ttl_seconds:
            sim, popular, alpha = load_saved_model(db)
            _model.update(at=time.time(), sim=sim, popular=popular, alpha=alpha)
        return _model["sim"], _model["popular"], _model["alpha"]


def interest_profile(db, customer_id: str) -> tuple:
    """(category -> weight, signal name) from purchases, else from recent views."""
    spend = {r["_id"]["category"]: float(r.get("spend") or 0.0)
             for r in db[COLL_AFFINITY].find({"_id.customer_id": customer_id}, {"_id": 1, "spend": 1})}
    if spend:
        return spend, "purchases"
    views = db[COLL_EVENTS].aggregate([
        {"$match": {"customer_id": customer_id, "event_type": {"$in": ["view_product", "add_to_cart"]},
                    "category": {"$ne": None}}},
        {"$sort": {"timestamp": -1}}, {"$limit": 50},
        {"$group": {"_id": "$category", "n": {"$sum": 1}}},
    ])
    viewed = {v["_id"]: v["n"] * VIEW_WEIGHT for v in views}
    return viewed, ("browsing" if viewed else None)


def recommendations(db, customer_id: str = None, n_categories: int = 3, per_category: int = 4) -> dict:
    sim, popular, alpha = _load_model(db)
    profile, signal = (interest_profile(db, customer_id) if customer_id else ({}, None))
    bought = set()
    if customer_id:
        bought = set(db[COLL_ORDERS].distinct("line_items.product_id", {"customer_id": customer_id}))

    if sim is None or not signal:
        cats = [c["category"] for c in list_categories(db)[:n_categories]]
        recs = [{"category": c, "reason": "popular", "because": None} for c in cats]
    else:
        recs = recommend_categories(profile, sim, popular, n_categories, alpha)
        # A category the customer only browsed (not bought) is still fair to show.
        if signal == "browsing":
            seen = {r["category"] for r in recs}
            for cat in sorted(profile, key=profile.get, reverse=True):
                if len(recs) >= n_categories:
                    break
                if cat not in seen:
                    recs.append({"category": cat, "reason": "browsing", "because": None})

    categories, products, seen_products = [], [], set(bought)
    for r in recs[:n_categories]:
        items = popular_products(db, per_category, category=r["category"], exclude=seen_products)
        if not items:
            items = popular_products(db, per_category, category=r["category"], exclude=seen_products, min_rating=0)
        seen_products |= {i["product_id"] for i in items}
        because = r.get("because") if r.get("because") not in (None, "other") else None  # "other" = no category
        categories.append({
            "category": r["category"], "label": category_label(db, r["category"]), "reason": r["reason"],
            "because": because,
            "because_label": category_label(db, because) if because else None,
        })
        products += [{**i, "rec_category": r["category"]} for i in items]
    return {"signal": signal or "none", "alpha": alpha, "categories": categories, "products": products}


def home_feed(db, customer: dict = None) -> dict:
    from .catalog import deals, under_price
    from .checkout import FREE_DELIVERY_MIN, is_plus
    cid = customer["_id"] if customer else None
    recs = recommendations(db, cid, n_categories=3, per_category=4) if cid else None
    seen = {p["product_id"] for p in (recs or {}).get("products", [])}
    deal_items = deals(db, 12, exclude=seen)
    seen |= {p["product_id"] for p in deal_items}
    popular = popular_products(db, 12, exclude=seen)
    seen |= {p["product_id"] for p in popular}
    return {
        "offer": offer_for(customer) if customer else None,
        "segment": ((customer or {}).get("segment") or {}).get("label"),
        "is_plus": is_plus(customer) if customer else False,
        "free_delivery_min": FREE_DELIVERY_MIN,
        "recommended": recs,
        "deals": deal_items,
        "popular": popular,
        "budget": {"max": BUDGET_MAX, "items": under_price(db, BUDGET_MAX, 12, exclude=seen)},
        "categories": list_categories(db)[:18],
    }


def taste_graph(db, customer: dict = None, neighbours: int = 3) -> dict:
    """The data behind the home page's 3-D "taste map".

    Nodes are the store's categories (sized by how many real customers bought
    in them). Edges are Module 2's category similarities: each category is
    joined to its `neighbours` most similar ones, the same table "Recommended
    for you" reads. `focus` is where the shopper's own taste starts (their
    purchases, else what they browsed, else the best-sellers) and
    `recommended` is where the model sends them next."""
    sims = list(db[COLL_CATEGORY_SIMILARITY].find({}, {"label": 1, "buyers": 1, "similar": 1}))
    cats = {c["category"]: c for c in list_categories(db)}
    nodes = [{"id": d["_id"], "label": cats[d["_id"]]["label"], "buyers": int(d.get("buyers") or 0),
              "products": cats[d["_id"]]["products"]}
             for d in sims if d["_id"] in cats and d["_id"] != "other"]
    ids = {n["id"] for n in nodes}
    weights = {}
    for d in sims:
        if d["_id"] not in ids:
            continue
        for s in [s for s in d.get("similar", []) if s["category"] in ids and s["score"] > 0][:neighbours]:
            key = tuple(sorted((d["_id"], s["category"])))
            weights[key] = max(weights.get(key, 0.0), float(s["score"]))
    top = max(weights.values(), default=1.0) or 1.0
    edges = [{"a": a, "b": b, "w": round(w / top, 4)} for (a, b), w in sorted(weights.items())]

    focus, recommended, signal = [], [], None
    if customer:
        profile, signal = interest_profile(db, customer["_id"])
        focus = [c for c in sorted(profile, key=profile.get, reverse=True) if c in ids][:3]
        sim, popular, alpha = _load_model(db)
        if focus and sim is not None:
            recommended = [r["category"] for r in recommend_categories(profile, sim, popular, 3, alpha)
                           if r["category"] in ids]
    if not focus:
        focus = [c for c in cats if c in ids][:3]       # best-sellers first
    stats = {"aisles": len(nodes), "products": sum(c["products"] for c in cats.values()),
             "customers": db[COLL_CUSTOMERS].estimated_document_count()}
    return {"nodes": nodes, "edges": edges, "focus": focus, "recommended": recommended,
            "signal": signal or "popular", "stats": stats}
