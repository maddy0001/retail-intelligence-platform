"""
catalog.py — product search, product pages and "customers also bought".

Search is ONE aggregation: a $match (with $text when there is a query) feeds a
$facet that returns, in a single round trip, the page of results, the total
count, and the facet counts the filter sidebar shows (categories, price
ranges via $bucket, star ratings via $bucket).
"""

import re
import time

from config import COLL_PRODUCTS, COLL_REVIEWS, COLL_ORDERS, COMPLETED_STATUSES
from .common import PRODUCT_CARD_FIELDS, clean, product_card
from .money import INR_PER_BRL, brl_ceiling, brl_floor

# Price filters are in store rupees. The catalogue is stored in reais, so a rupee
# range becomes a reais range for the query (which keeps using the `price` index)
# and the facet buckets group on the rupee price itself.
NO_UPPER = 10_000_000
PRICE_BOUNDARIES = [0, 500, 1000, 2000, 5000, 10000, 20000, NO_UPPER]
RATING_BOUNDARIES = [1, 2, 3, 4, 5.01]
SORTS = {
    "popular": {"sales_count": -1, "_id": 1},
    "rating": {"rating_avg": -1, "review_count": -1, "_id": 1},
    "price_asc": {"price": 1, "_id": 1},
    "price_desc": {"price": -1, "_id": 1},
}

_category_cache = {"at": 0.0, "data": None}


def list_categories(db, ttl_seconds: int = 300) -> list:
    """All categories with product counts, most-sold first (cached for 5 minutes)."""
    if _category_cache["data"] is not None and time.time() - _category_cache["at"] < ttl_seconds:
        return _category_cache["data"]
    rows = db[COLL_PRODUCTS].aggregate([
        {"$group": {"_id": "$category", "label": {"$first": "$category_label"},
                    "products": {"$sum": 1}, "sales": {"$sum": "$sales_count"}}},
        {"$sort": {"sales": -1}},
    ])
    data = [{"category": r["_id"], "label": r["label"], "products": r["products"], "sales": r["sales"]}
            for r in rows]
    _category_cache.update(at=time.time(), data=data)
    return data


def category_label(db, category: str) -> str:
    for c in list_categories(db):
        if c["category"] == category:
            return c["label"]
    return category.replace("_", " ").title() if category else category


def search_products(db, q=None, category=None, min_price=None, max_price=None, min_rating=None,
                    sort="relevance", page=1, page_size=24, mode="auto") -> dict:
    """$text search first (stemmed, ranked). If it finds nothing — e.g. "perfume"
    vs the stem of "Perfumery" — retry once with a case-insensitive substring
    match on the name and category label (mode="substring")."""
    if q and mode == "auto":
        result = search_products(db, q, category, min_price, max_price, min_rating, sort, page, page_size,
                                 mode="text")
        if result["total"] > 0:
            return result
        return search_products(db, q, category, min_price, max_price, min_rating,
                               "popular" if sort == "relevance" else sort, page, page_size, mode="substring")
    match = {}
    if q and mode == "substring":
        pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
        match["$or"] = [{"name": pattern}, {"category_label": pattern}, {"category_pt": pattern}]
        q = None   # no text score in this mode
    elif q:
        match["$text"] = {"$search": q}
    price = {}
    if min_price is not None:
        price["$gte"] = brl_floor(min_price)
    if max_price is not None:
        price["$lt"] = brl_ceiling(max_price)
    if price:
        match["price"] = price
    if min_rating:
        match["rating_avg"] = {"$gte": float(min_rating)}
    match_all = dict(match)          # used for the category facet (ignores the category filter)
    if category:
        match["category"] = category

    if q and (sort == "relevance" or sort not in SORTS):
        sort_spec = {"score": -1, "sales_count": -1, "_id": 1}   # best text match first
    else:
        sort_spec = SORTS.get(sort, SORTS["popular"])

    page = max(1, int(page))
    page_size = min(60, max(1, int(page_size)))
    results_stage = [
        {"$sort": sort_spec},
        {"$skip": (page - 1) * page_size},
        {"$limit": page_size},
        {"$project": PRODUCT_CARD_FIELDS},
    ]
    # The text score is attached BEFORE $facet so the sub-pipelines can sort on it.
    pre_facet = [{"$match": match}] + ([{"$addFields": {"score": {"$meta": "textScore"}}}] if q else [])

    facet = {
        "results": results_stage,
        "total": [{"$count": "n"}],
        "price_ranges": [{"$bucket": {"groupBy": {"$round": [{"$multiply": ["$price", INR_PER_BRL]}, 0]},
                                      "boundaries": PRICE_BOUNDARIES,
                                      "default": "unknown", "output": {"count": {"$sum": 1}}}}],
        "ratings": [{"$bucket": {"groupBy": {"$ifNull": ["$rating_avg", 0]}, "boundaries": RATING_BOUNDARIES,
                                 "default": "unrated", "output": {"count": {"$sum": 1}}}}],
    }
    if not category:
        facet["categories"] = [
            {"$group": {"_id": "$category", "label": {"$first": "$category_label"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}, {"$limit": 40},
        ]
    out = list(db[COLL_PRODUCTS].aggregate(pre_facet + [{"$facet": facet}], allowDiskUse=True))[0]

    if category:  # category counts should not be narrowed by the category itself
        out["categories"] = list(db[COLL_PRODUCTS].aggregate([
            {"$match": match_all},
            {"$group": {"_id": "$category", "label": {"$first": "$category_label"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}, {"$limit": 40},
        ]))

    total = out["total"][0]["n"] if out["total"] else 0
    price_ranges = []
    for b in out["price_ranges"]:
        if b["_id"] == "unknown":
            continue
        idx = PRICE_BOUNDARIES.index(b["_id"])
        upper = PRICE_BOUNDARIES[idx + 1] if idx + 1 < len(PRICE_BOUNDARIES) else None
        price_ranges.append({"min": b["_id"], "max": None if upper == NO_UPPER else upper, "count": b["count"]})
    ratings = [{"stars": int(b["_id"]), "count": b["count"]} for b in out["ratings"] if b["_id"] != "unrated"]
    return {
        "items": [product_card(p) for p in out["results"]],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "facets": {
            "categories": [{"category": c["_id"], "label": c["label"], "count": c["count"]} for c in out["categories"]],
            "price_ranges": price_ranges,
            "ratings": sorted(ratings, key=lambda r: -r["stars"]),
        },
    }


def get_product(db, product_id: str):
    return db[COLL_PRODUCTS].find_one({"product_id": product_id})


def product_reviews(db, product_id: str, page: int = 1, page_size: int = 6) -> dict:
    """Star breakdown over ALL reviews; the listing pages through reviews that have text
    (most Olist reviews are a star rating only)."""
    query = {"product_id": product_id}
    total = db[COLL_REVIEWS].count_documents(query)
    text_query = {**query, "message": {"$ne": None}}
    with_text = db[COLL_REVIEWS].count_documents(text_query)
    cursor = db[COLL_REVIEWS].find(text_query).sort([("created_at", -1), ("_id", 1)]) \
        .skip((page - 1) * page_size).limit(page_size)
    items = [clean({k: r.get(k) for k in ("rating", "title", "message", "created_at", "language",
                                          "verified_purchase", "source", "author")}) for r in cursor]
    breakdown = {int(r["_id"]): r["n"] for r in db[COLL_REVIEWS].aggregate([
        {"$match": query}, {"$group": {"_id": "$rating", "n": {"$sum": 1}}}])}
    return {"total": total, "with_text": with_text, "page": page, "items": items,
            "breakdown": {str(s): breakdown.get(s, 0) for s in range(5, 0, -1)}}


def also_bought(db, product_id: str, category: str = None, limit: int = 8) -> dict:
    """People who bought this also bought: products in OTHER orders of the same
    customers (and in the same order). Falls back to best-sellers in the
    category when the co-purchase signal is thin (most Olist buyers order once)."""
    buyers = db[COLL_ORDERS].distinct("customer_id", {"line_items.product_id": product_id,
                                                      "order_status": {"$in": COMPLETED_STATUSES}})
    co = []
    if buyers:
        co = list(db[COLL_ORDERS].aggregate([
            {"$match": {"customer_id": {"$in": buyers[:2000]}, "order_status": {"$in": COMPLETED_STATUSES}}},
            {"$unwind": "$line_items"},
            {"$match": {"line_items.product_id": {"$ne": product_id}}},
            {"$group": {"_id": "$line_items.product_id", "buyers": {"$addToSet": "$customer_id"}}},
            {"$project": {"n": {"$size": "$buyers"}}},
            {"$sort": {"n": -1, "_id": 1}},
            {"$limit": limit},
            {"$lookup": {"from": COLL_PRODUCTS, "localField": "_id", "foreignField": "product_id", "as": "p"}},
            {"$unwind": "$p"},
        ]))
    items = [{**product_card(r["p"]), "co_buyers": r["n"]} for r in co]
    reason = "co_purchase" if items else None
    if len(items) < 4 and category:
        seen = {product_id} | {i["product_id"] for i in items}
        for p in db[COLL_PRODUCTS].find({"category": category, "product_id": {"$nin": list(seen)},
                                         "rating_avg": {"$gte": 4}}, PRODUCT_CARD_FIELDS) \
                .sort("sales_count", -1).limit(limit - len(items)):
            items.append({**product_card(p), "co_buyers": 0})
        reason = reason or "same_category"
    return {"reason": reason, "items": items}


def deals(db, limit: int = 12, exclude=None) -> list:
    """Today's deals: well-rated products whose current price is furthest below
    the highest price they really sold for (the store's M.R.P.)."""
    gap = {"$divide": [{"$subtract": ["$price_range.max", "$price"]}, "$price_range.max"]}
    match = {"rating_avg": {"$gte": 4.0}, "review_count": {"$gte": 5}, "price": {"$gt": 0}}
    if exclude:
        match["product_id"] = {"$nin": list(exclude)}
    rows = db[COLL_PRODUCTS].aggregate([
        {"$match": match},
        {"$addFields": {"_gap": gap}},
        {"$match": {"_gap": {"$gte": 0.15, "$lte": 0.6}}},
        {"$sort": {"_gap": -1, "sales_count": -1, "_id": 1}},
        {"$limit": limit},
        {"$project": PRODUCT_CARD_FIELDS},
    ])
    return [product_card(p) for p in rows]


def under_price(db, max_inr: float = 999, limit: int = 12, exclude=None) -> list:
    """Well-rated best-sellers whose store price is at most max_inr rupees."""
    query = {"price": {"$lt": brl_ceiling(max_inr)}, "rating_avg": {"$gte": 4.3}, "review_count": {"$gte": 8}}
    if exclude:
        query["product_id"] = {"$nin": list(exclude)}
    return [product_card(p) for p in db[COLL_PRODUCTS].find(query, PRODUCT_CARD_FIELDS)
            .sort("sales_count", -1).limit(limit)]


def popular_products(db, limit: int = 12, category: str = None, exclude=None, min_rating: float = 4.0) -> list:
    query = {"rating_avg": {"$gte": min_rating}, "review_count": {"$gte": 3}}
    if category:
        query["category"] = category
    if exclude:
        query["product_id"] = {"$nin": list(exclude)}
    return [product_card(p) for p in db[COLL_PRODUCTS].find(query, PRODUCT_CARD_FIELDS)
            .sort("sales_count", -1).limit(limit)]
