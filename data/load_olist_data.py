"""
load_olist_data.py
-------------------
REAL DATA loader. Transforms the public Olist Brazilian E-Commerce dataset
(Kaggle: olistbr/brazilian-ecommerce) into the customers / orders / products /
reviews schema defined in schema/schema_design.md and loads it into MongoDB.

This script does NOT generate or fabricate any behavioral/clickstream data —
it only reshapes real transactional records. Every document it writes carries
`source: "olist"`. Synthetic events are produced separately and explicitly by
simulator/event_simulator.py, and records created by people using the app
carry `source: "app"`.

Key modelling decisions (see schema/schema_design.md for the full reasoning):
  * One customer document per REAL PERSON. Olist issues a new `customer_id`
    for every order; the actual repeat customer is `customer_unique_id`.
    Keying customers on customer_unique_id is what gives RFM a meaningful
    Frequency (2,861 people have 2+ completed orders, up to 16).
  * All orders are loaded by default (99,441). `--limit` exists only for
    quick local iteration.
  * Line items are grouped per (order, product, seller) with a real quantity,
    and carry the English category name used throughout the app.
  * Olist has no product names or photos. Display names are derived from real
    attributes ("Bed Bath Table #1E9E8E" = category + product-id prefix);
    nothing is invented. Price, rating, sales count and seller location are
    all computed from the real order, review and seller files.

Expected input files (download from Kaggle and place in data/raw/):
    olist_customers_dataset.csv        olist_order_payments_dataset.csv
    olist_orders_dataset.csv           olist_products_dataset.csv
    olist_order_items_dataset.csv      olist_order_reviews_dataset.csv
    olist_sellers_dataset.csv          product_category_name_translation.csv

Usage:
    python data/load_olist_data.py --raw-dir data/raw
    python data/load_olist_data.py --raw-dir data/raw --limit 5000   # quick dev load
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (  # noqa: E402
    get_db, COLL_CUSTOMERS, COLL_ORDERS, COLL_PRODUCTS, COLL_REVIEWS, COLL_EVENTS,
    COLL_RFM, COLL_AFFINITY, COLL_ROLLING_METRICS, COLL_CATEGORY_SIMILARITY,
)

SOURCE = "olist"

# Two Portuguese categories have no row in Olist's own translation file.
CATEGORY_FALLBACK_EN = {
    "pc_gamer": "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_food_preparers",
}
SMALL_WORDS = {"and", "of", "for", "the", "in", "on"}
# Typos that exist in Olist's English category names.
LABEL_FIXES = {"Fashio ": "Fashion ", "Confort": "Comfort", "Costruction": "Construction"}


def category_label(category_en: str) -> str:
    """'bed_bath_table' -> 'Bed Bath Table'; fixes Olist's known typos."""
    if not category_en or category_en == "other":
        return "Other"
    words = category_en.replace("_", " ").split()
    label = " ".join(w if (i and w in SMALL_WORDS) else w.capitalize() for i, w in enumerate(words))
    for bad, good in LABEL_FIXES.items():
        label = label.replace(bad, good)
    if label.endswith(" 2"):
        label = label[:-2] + " II"
    return label


def _none_if_nan(value):
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if value is pd.NaT:
        return None
    return value


def _ts(value):
    """pandas Timestamp/NaT -> timezone-aware datetime or None."""
    if value is None or pd.isna(value):
        return None
    return value.to_pydatetime().replace(tzinfo=timezone.utc)


def load_raw_frames(raw_dir: str) -> dict:
    files = {
        "customers": "olist_customers_dataset.csv",
        "orders": "olist_orders_dataset.csv",
        "items": "olist_order_items_dataset.csv",
        "payments": "olist_order_payments_dataset.csv",
        "products": "olist_products_dataset.csv",
        "reviews": "olist_order_reviews_dataset.csv",
        "sellers": "olist_sellers_dataset.csv",
        "translation": "product_category_name_translation.csv",
    }
    frames = {}
    for key, name in files.items():
        path = os.path.join(raw_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Missing {name} in {raw_dir}. Download the Olist dataset from "
                f"Kaggle (olistbr/brazilian-ecommerce) and place the CSVs there."
            )
        frames[key] = pd.read_csv(path, encoding="utf-8-sig")
    date_cols = {
        "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
                   "order_delivered_customer_date", "order_estimated_delivery_date"],
        "reviews": ["review_creation_date", "review_answer_timestamp"],
    }
    for key, cols in date_cols.items():
        for col in cols:
            frames[key][col] = pd.to_datetime(frames[key][col], errors="coerce")
    return frames


def apply_limit(frames: dict, limit: int) -> dict:
    """Keep only the `limit` most recent orders (and the rows that belong to them)."""
    orders = frames["orders"].sort_values("order_purchase_timestamp").tail(limit)
    keep_orders = set(orders["order_id"])
    keep_customers = set(orders["customer_id"])
    frames = dict(frames)
    frames["orders"] = orders
    frames["items"] = frames["items"][frames["items"]["order_id"].isin(keep_orders)]
    frames["payments"] = frames["payments"][frames["payments"]["order_id"].isin(keep_orders)]
    frames["reviews"] = frames["reviews"][frames["reviews"]["order_id"].isin(keep_orders)]
    frames["customers"] = frames["customers"][frames["customers"]["customer_id"].isin(keep_customers)]
    frames["products"] = frames["products"][frames["products"]["product_id"].isin(set(frames["items"]["product_id"]))]
    return frames


def category_frame(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    """product_id -> (category_pt, category, category_label)."""
    df = products[["product_id", "product_category_name"]].merge(translation, on="product_category_name", how="left")
    df["category_pt"] = df["product_category_name"].fillna("sem_categoria")
    df["category"] = df["product_category_name_english"]
    missing = df["category"].isna()
    df.loc[missing, "category"] = df.loc[missing, "product_category_name"].map(CATEGORY_FALLBACK_EN)
    df["category"] = df["category"].fillna("other")
    df["category_label"] = df["category"].map(category_label)
    return df[["product_id", "category_pt", "category", "category_label"]]


def build_customers(customers: pd.DataFrame, orders: pd.DataFrame) -> list:
    """One document per real person (customer_unique_id)."""
    merged = customers.merge(orders[["customer_id", "order_purchase_timestamp"]], on="customer_id", how="left")
    merged = merged.sort_values("order_purchase_timestamp")
    docs = []
    for unique_id, grp in merged.groupby("customer_unique_id", sort=False):
        latest = grp.iloc[-1]  # most recent order's address
        docs.append({
            "_id": f"c_{unique_id}",
            "customer_unique_id": unique_id,
            "olist_customer_ids": grp["customer_id"].tolist(),
            "customer_city": latest["customer_city"],
            "customer_state": latest["customer_state"],
            "customer_zip_prefix": str(latest["customer_zip_code_prefix"]).zfill(5),
            "first_order_at": _ts(grp["order_purchase_timestamp"].min()),
            "last_order_at": _ts(grp["order_purchase_timestamp"].max()),
            "order_count": int(len(grp)),
            "source": SOURCE,
            "profile": {"preferred_channel": None},
            "segment": {"label": None, "cluster_id": None, "method": None, "computed_at": None},
            "anomaly": {"risk_label": None, "score": None, "flags": [], "computed_at": None},
        })
    return docs


def build_orders(orders, items, payments, cats, customers) -> list:
    person_by_customer_id = dict(zip(customers["customer_id"], customers["customer_unique_id"]))

    lines = (items.groupby(["order_id", "product_id", "seller_id"], as_index=False)
             .agg(quantity=("order_item_id", "count"), unit_price=("price", "mean"),
                  freight_value=("freight_value", "mean")))
    lines = lines.merge(cats, on="product_id", how="left")
    lines["unit_price"] = lines["unit_price"].round(2)
    lines["freight_value"] = lines["freight_value"].round(2)
    items_by_order = {}
    for row in lines.to_dict("records"):
        items_by_order.setdefault(row["order_id"], []).append({
            "product_id": row["product_id"],
            "category": row["category"],
            "category_pt": row["category_pt"],
            "seller_id": row["seller_id"],
            "unit_price": float(row["unit_price"]),
            "freight_value": float(row["freight_value"]),
            "quantity": int(row["quantity"]),
        })

    payment_by_order = {}
    for order_id, grp in payments.groupby("order_id"):
        main = grp.sort_values("payment_value").iloc[-1]
        payment_by_order[order_id] = {
            "type": main["payment_type"],
            "installments": int(grp["payment_installments"].max()),
            "total_value": round(float(grp["payment_value"].sum()), 2),
            "methods": sorted(grp["payment_type"].unique().tolist()),
        }

    docs = []
    for row in orders.to_dict("records"):
        order_id = row["order_id"]
        line_items = items_by_order.get(order_id, [])
        items_total = round(sum(li["unit_price"] * li["quantity"] for li in line_items), 2)
        freight_total = round(sum(li["freight_value"] * li["quantity"] for li in line_items), 2)
        delivered = _ts(row["order_delivered_customer_date"])
        docs.append({
            "_id": f"o_{order_id}",
            "order_id": order_id,
            "customer_id": f"c_{person_by_customer_id[row['customer_id']]}",
            "olist_customer_id": row["customer_id"],
            "order_status": row["order_status"],
            "order_purchase_timestamp": _ts(row["order_purchase_timestamp"]),
            "order_delivered_timestamp": delivered,
            "timeline": {
                "approved_at": _ts(row["order_approved_at"]),
                "shipped_at": _ts(row["order_delivered_carrier_date"]),
                "delivered_at": delivered,
                "estimated_delivery_at": _ts(row["order_estimated_delivery_date"]),
            },
            "payment": payment_by_order.get(order_id, {}),
            "line_items": line_items,
            "items_total": items_total,
            "freight_total": freight_total,
            "source": SOURCE,
        })
    return docs


def build_products(products, items, reviews, sellers, cats) -> list:
    price_stats = items.groupby("product_id").agg(
        price=("price", "median"), price_min=("price", "min"), price_max=("price", "max"),
        freight=("freight_value", "median"), sales_count=("order_item_id", "count"))

    main_seller = (items.groupby(["product_id", "seller_id"]).size().reset_index(name="n")
                   .sort_values("n").groupby("product_id").tail(1)
                   .merge(sellers, on="seller_id", how="left").set_index("product_id"))

    # Olist reviews are per ORDER; a review applies to every product in that order.
    order_products = items[["order_id", "product_id"]].drop_duplicates()
    rated = order_products.merge(reviews[["order_id", "review_score"]], on="order_id", how="inner")
    rating_stats = rated.groupby("product_id").agg(rating_avg=("review_score", "mean"),
                                                   review_count=("review_score", "count"))

    df = (products.merge(cats, on="product_id", how="left")
          .merge(price_stats, left_on="product_id", right_index=True, how="left")
          .merge(rating_stats, left_on="product_id", right_index=True, how="left"))

    docs = []
    for row in df.to_dict("records"):
        pid = row["product_id"]
        seller = main_seller.loc[pid] if pid in main_seller.index else None
        docs.append({
            "_id": f"p_{pid}",
            "product_id": pid,
            "name": f"{row['category_label']} #{pid[:6].upper()}",
            "category": row["category"],
            "category_label": row["category_label"],
            "category_pt": row["category_pt"],
            "price": round(float(row["price"]), 2) if pd.notna(row["price"]) else None,
            "price_range": {
                "min": round(float(row["price_min"]), 2) if pd.notna(row["price_min"]) else None,
                "max": round(float(row["price_max"]), 2) if pd.notna(row["price_max"]) else None,
            },
            "freight": round(float(row["freight"]), 2) if pd.notna(row["freight"]) else None,
            "sales_count": int(row["sales_count"]) if pd.notna(row["sales_count"]) else 0,
            "rating_avg": round(float(row["rating_avg"]), 2) if pd.notna(row["rating_avg"]) else None,
            "review_count": int(row["review_count"]) if pd.notna(row["review_count"]) else 0,
            "seller": None if seller is None else {
                "seller_id": seller["seller_id"],
                "city": _none_if_nan(seller["seller_city"]),
                "state": _none_if_nan(seller["seller_state"]),
            },
            "photos_qty": int(row["product_photos_qty"]) if pd.notna(row["product_photos_qty"]) else 0,
            "weight_g": float(row["product_weight_g"]) if pd.notna(row["product_weight_g"]) else None,
            "dimensions_cm": {
                "length": float(row["product_length_cm"]) if pd.notna(row["product_length_cm"]) else None,
                "height": float(row["product_height_cm"]) if pd.notna(row["product_height_cm"]) else None,
                "width": float(row["product_width_cm"]) if pd.notna(row["product_width_cm"]) else None,
            },
            "source": SOURCE,
        })
    return docs


def build_reviews(reviews, items, customers, orders) -> list:
    person_by_customer_id = dict(zip(customers["customer_id"], customers["customer_unique_id"]))
    customer_by_order = dict(zip(orders["order_id"], orders["customer_id"]))
    order_products = items[["order_id", "product_id"]].drop_duplicates()
    df = reviews.merge(order_products, on="order_id", how="inner")
    df = df.drop_duplicates(subset=["review_id", "order_id", "product_id"])
    docs = []
    for row in df.to_dict("records"):
        olist_cid = customer_by_order.get(row["order_id"])
        docs.append({
            "_id": f"r_{row['review_id']}_{row['order_id'][:8]}_{row['product_id'][:8]}",
            "review_id": row["review_id"],
            "order_id": row["order_id"],
            "product_id": row["product_id"],
            "customer_id": f"c_{person_by_customer_id[olist_cid]}" if olist_cid in person_by_customer_id else None,
            "rating": int(row["review_score"]),
            "title": _none_if_nan(row["review_comment_title"]),
            "message": _none_if_nan(row["review_comment_message"]),
            "language": "pt",
            "created_at": _ts(row["review_creation_date"]),
            "verified_purchase": True,
            "source": SOURCE,
        })
    return docs


def insert_in_batches(coll, docs, batch_size=10_000):
    for start in range(0, len(docs), batch_size):
        coll.insert_many(docs[start:start + batch_size], ordered=False)


def clear_previous_load(db):
    """Remove earlier Olist loads and everything derived from them, but keep
    records people created in the app (source: "app")."""
    db[COLL_CUSTOMERS].delete_many({"source": {"$ne": "app"}})
    db[COLL_ORDERS].delete_many({"source": {"$ne": "app"}})
    db[COLL_REVIEWS].delete_many({"source": {"$ne": "app"}})
    db[COLL_PRODUCTS].delete_many({})
    db[COLL_EVENTS].delete_many({"metadata.source": {"$ne": "app"}})
    for name in [COLL_RFM, COLL_AFFINITY, COLL_ROLLING_METRICS, COLL_CATEGORY_SIMILARITY]:
        db[name].drop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--limit", type=int, default=None,
                        help="Optional: keep only the N most recent orders, for fast local iteration")
    args = parser.parse_args()

    t0 = time.time()
    frames = load_raw_frames(args.raw_dir)
    if args.limit:
        frames = apply_limit(frames, args.limit)
    cats = category_frame(frames["products"], frames["translation"])

    products = build_products(frames["products"], frames["items"], frames["reviews"], frames["sellers"], cats)
    customers = build_customers(frames["customers"], frames["orders"])
    orders = build_orders(frames["orders"], frames["items"], frames["payments"], cats, frames["customers"])
    reviews = build_reviews(frames["reviews"], frames["items"], frames["customers"], frames["orders"])
    print(f"Built documents in {time.time() - t0:.1f}s")

    db = get_db()
    clear_previous_load(db)
    db[COLL_PRODUCTS].create_index("product_id", unique=True, name="uniq_product_id")
    insert_in_batches(db[COLL_PRODUCTS], products)
    insert_in_batches(db[COLL_CUSTOMERS], customers)
    insert_in_batches(db[COLL_ORDERS], orders)
    insert_in_batches(db[COLL_REVIEWS], reviews)

    from data.enrich_products import enrich_delivery_days
    enrich_delivery_days(db, verbose=False)   # needs the unique index on products.product_id

    repeat = sum(1 for c in customers if c["order_count"] > 1)
    print(f"Loaded REAL Olist data in {time.time() - t0:.1f}s: {len(products):,} products, "
          f"{len(customers):,} customers (real people; {repeat:,} with 2+ orders), "
          f"{len(orders):,} orders, {len(reviews):,} product reviews. "
          f"No synthetic fields populated here (source='olist').")


if __name__ == "__main__":
    main()
