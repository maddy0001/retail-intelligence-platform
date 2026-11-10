"""Catalog: categories, search, product pages and reviews."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from config import COLL_ORDERS, COLL_PRODUCTS, COLL_REVIEWS
from ..db import get_client, get_db
from ..schemas import ReviewIn
from ..security import current_user, optional_user
from ..services.activity import record_event
from ..services.catalog import (also_bought, deals, get_product, list_categories, product_reviews,
                                search_products)
from ..services.checkout import FREE_DELIVERY_MIN
from ..services.common import clean, now, product_card
from ..services.money import CURRENCY, store_price
from ..services.personalization import BUDGET_MAX

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/store")
def store_info():
    """The store's currency and delivery rule, for the footer and the price notes."""
    return {**CURRENCY, "free_delivery_min": FREE_DELIVERY_MIN, "budget_max": BUDGET_MAX}


@router.get("/categories")
def categories(db=Depends(get_db)):
    return list_categories(db)


@router.get("/deals")
def deals_list(limit: int = Query(48, ge=1, le=96), db=Depends(get_db)):
    """Well-rated products whose price is 15-60% below the highest price they really sold for."""
    return {"items": deals(db, limit)}


@router.get("/products")
def products(q: Optional[str] = Query(None, max_length=80), category: Optional[str] = None,  # prices in rupees
             min_price: Optional[float] = Query(None, ge=0), max_price: Optional[float] = Query(None, ge=0),
             min_rating: Optional[float] = Query(None, ge=0, le=5), sort: str = "relevance",
             page: int = Query(1, ge=1, le=500), page_size: int = Query(24, ge=1, le=60),
             user=Depends(optional_user), db=Depends(get_db)):
    q = (q or "").strip() or None
    result = search_products(db, q, category, min_price, max_price, min_rating, sort, page, page_size)
    if user and user.get("customer_id") and q and page == 1:
        record_event(db, user["customer_id"], "search", category=category, extra={"query": q})
    return result


@router.get("/products/{product_id}")
def product_detail(product_id: str, user=Depends(optional_user), db=Depends(get_db)):
    product = get_product(db, product_id)
    if not product:
        raise HTTPException(404, "Product not found.")
    can_review = False
    if user and user.get("customer_id"):
        cid = user["customer_id"]
        record_event(db, cid, "view_product", product_id=product_id, category=product.get("category"))
        bought = db[COLL_ORDERS].find_one({"customer_id": cid, "line_items.product_id": product_id,
                                           "order_status": {"$in": ["shipped", "delivered"]}}, {"_id": 1})
        reviewed = db[COLL_REVIEWS].find_one({"customer_id": cid, "product_id": product_id}, {"_id": 1})
        can_review = bool(bought) and not reviewed
    return {
        "product": {**product_card(product), "category_pt": product.get("category_pt"),
                    "price_range": {k: store_price(v) for k, v in (product.get("price_range") or {}).items()},
                    "photos_qty": product.get("photos_qty"),
                    "weight_g": product.get("weight_g"), "dimensions_cm": product.get("dimensions_cm"),
                    "seller": product.get("seller")},
        "reviews": product_reviews(db, product_id),
        "also_bought": also_bought(db, product_id, product.get("category")),
        "can_review": can_review,
    }


@router.get("/products/{product_id}/reviews")
def reviews(product_id: str, page: int = Query(1, ge=1, le=200), db=Depends(get_db)):
    return product_reviews(db, product_id, page=page)


@router.post("/products/{product_id}/reviews", status_code=201)
def write_review(product_id: str, body: ReviewIn, user=Depends(current_user), db=Depends(get_db)):
    cid = user.get("customer_id")
    if not db[COLL_ORDERS].find_one({"customer_id": cid, "line_items.product_id": product_id,
                                     "order_status": {"$in": ["shipped", "delivered"]}}, {"_id": 1}):
        raise HTTPException(403, "You can review products you've bought once they've shipped.")
    if db[COLL_REVIEWS].find_one({"customer_id": cid, "product_id": product_id}, {"_id": 1}):
        raise HTTPException(409, "You've already reviewed this product.")
    review = {"_id": f"r_app_{now().strftime('%Y%m%d%H%M%S%f')}", "product_id": product_id, "customer_id": cid,
              "rating": body.rating, "title": (body.title or "").strip() or None,
              "message": (body.message or "").strip() or None, "language": "en", "created_at": now(),
              "verified_purchase": True, "author": user.get("name"), "source": "app"}

    # Review insert and the product's running average change together (transaction).
    with get_client().start_session() as session:
        def txn(s):
            db[COLL_REVIEWS].insert_one(review, session=s)
            db[COLL_PRODUCTS].update_one({"product_id": product_id}, [{"$set": {
                "rating_avg": {"$round": [{"$divide": [
                    {"$add": [{"$multiply": [{"$ifNull": ["$rating_avg", 0]}, "$review_count"]}, body.rating]},
                    {"$add": ["$review_count", 1]}]}, 2]},
                "review_count": {"$add": ["$review_count", 1]},
            }}], session=s)
        session.with_transaction(txn)
    return clean(review)
