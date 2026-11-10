"""
module2_collaborative_filtering.py
------------------------------------
MODULE 2 — Recommendation Intelligence (item-based Collaborative Filtering)

Input: Pipeline B's `category_affinity` collection (customer x category
spend), pulled via pymongo into pandas / a sparse matrix.

Approach: item-based collaborative filtering with categories as the "items".
Each customer is a row, each category a column, values are log1p(spend) so a
single expensive purchase doesn't dominate. Cosine similarity between
category columns says "people who spend in X also spend in Y". For a
customer, candidate categories are scored by their similarity to the
categories that customer already buys from, weighted by that spend; bought
categories are excluded. If a customer has no signal (new sign-up, or only
categories nobody co-buys with), we fall back to the most popular categories
— and say so in the API response.

Output: the `category_similarity` collection (one document per category with
its top neighbours and popularity). The API reads it at request time, so a
recommendation is a cheap lookup, not a model run.

Evaluation (run() returns it; the notebook shows it): customers who bought
from 2+ categories are split into test / validation / train by customer.
Similarities come from train only. For each held-out customer, one bought
category is hidden and we check whether it appears in the top-3 / top-5
recommendations made from the rest (HitRate@k). Three rankers are compared:
pure CF, a CF + popularity blend (blend weight alpha chosen on validation),
and a popularity-only baseline. Most Olist customers buy once, so the
co-purchase signal is thin; the blend lets popularity fill that gap.

Why item-based cosine similarity over matrix factorization (e.g. `surprise`):
the matrix here is category-level (74 categories), small and stable, so a
precomputed 74x74 similarity table is fast and every recommendation is
explainable ("because you buy in Bed Bath Table"). Matrix factorization pays
off on large, sparse product-level matrices, which is listed as future work.
"""

import json
import os
import random
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_AFFINITY, COLL_CATEGORY_SIMILARITY, COLL_PRODUCTS, MODEL_DIR  # noqa: E402

TOP_NEIGHBOURS = 15


def load_affinity_frame(db) -> pd.DataFrame:
    docs = list(db[COLL_AFFINITY].find({}, {"_id": 1, "spend": 1}))
    if not docs:
        raise RuntimeError("category_affinity is empty — run pipelines/pipeline_b_affinity.py first.")
    return pd.DataFrame([{
        "customer_id": d["_id"]["customer_id"],
        "category": d["_id"]["category"],
        "spend": float(d.get("spend") or 0.0),
    } for d in docs])


def build_similarity(df: pd.DataFrame) -> pd.DataFrame:
    """Cosine similarity between category columns of the customer x category matrix."""
    customers = df["customer_id"].astype("category")
    categories = df["category"].astype("category")
    matrix = sparse.csr_matrix(
        (np.log1p(df["spend"].to_numpy()), (customers.cat.codes.to_numpy(), categories.cat.codes.to_numpy())),
        shape=(len(customers.cat.categories), len(categories.cat.categories)),
    )
    sim = cosine_similarity(matrix.T, dense_output=True)
    np.fill_diagonal(sim, 0.0)
    labels = list(categories.cat.categories)
    return pd.DataFrame(sim, index=labels, columns=labels)


def popularity(df: pd.DataFrame) -> pd.Series:
    """Number of distinct buyers per category (the baseline / cold-start ranking)."""
    return df.groupby("category")["customer_id"].nunique().sort_values(ascending=False)


def recommend_categories(spend_by_category: dict, sim: pd.DataFrame, popular: pd.Series,
                         top_n: int = 3, alpha: float = 0.0) -> list:
    """Return [{category, score, because, reason}].

    score = CF score (normalised to 0..1) + alpha x popularity (normalised to
    0..1). alpha = 0 is pure collaborative filtering; Module 2 picks alpha on
    a validation split. Bought categories are excluded; popular categories
    fill any remaining slots (reason "popular")."""
    owned = {c for c, s in spend_by_category.items() if s > 0}
    cf = pd.Series(0.0, index=sim.columns)
    contributions = {}
    for cat, spend in spend_by_category.items():
        if cat in sim.index and spend > 0:
            contrib = sim.loc[cat] * np.log1p(spend)
            cf = cf.add(contrib, fill_value=0.0)
            contributions[cat] = contrib
    cf = cf.drop(labels=list(owned), errors="ignore")
    pop = popular.reindex(cf.index).fillna(0.0).astype(float)
    cf_norm = cf / cf.max() if cf.max() > 0 else cf
    pop_norm = pop / pop.max() if pop.max() > 0 else pop
    final = (cf_norm + alpha * pop_norm) if alpha else cf_norm
    final = final[final > 0].sort_values(ascending=False)

    recs = []
    for cat, score in final.head(top_n).items():
        from_cf = cf.get(cat, 0.0) > 0
        because = (max(contributions, key=lambda c: contributions[c].get(cat, 0.0))
                   if from_cf and contributions else None)
        recs.append({"category": cat, "score": round(float(score), 4), "because": because,
                     "reason": "collaborative_filtering" if from_cf else "popular"})
    for cat in popular.index:
        if len(recs) >= top_n:
            break
        if cat not in owned and cat not in {r["category"] for r in recs}:
            recs.append({"category": cat, "score": 0.0, "because": None, "reason": "popular"})
    return recs


ALPHAS = [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]


def evaluate(df: pd.DataFrame, share=0.2, seed=42) -> dict:
    """Leave-one-category-out HitRate@3/@5 on held-out customers.

    Customers with 2+ categories are split into test (20%), validation (20%)
    and train (the rest, plus every single-category customer). Similarities and
    popularity come from train only. alpha (the popularity blend) is chosen on
    validation and reported on test, next to pure CF and the popularity baseline."""
    rng = random.Random(seed)
    multi = df.groupby("customer_id")["category"].nunique()
    multi_ids = sorted(multi[multi >= 2].index)
    rng.shuffle(multi_ids)
    n_hold = max(1, int(len(multi_ids) * share))
    test_ids, val_ids = set(multi_ids[:n_hold]), set(multi_ids[n_hold:2 * n_hold])

    train = df[~df["customer_id"].isin(test_ids | val_ids)]
    sim, popular = build_similarity(train), popularity(train)

    def cases(ids):
        out = []
        for _, grp in df[df["customer_id"].isin(ids)].groupby("customer_id"):
            spend = dict(zip(grp["category"], grp["spend"]))
            hidden = rng.choice(sorted(spend))
            out.append(({c: s for c, s in spend.items() if c != hidden}, hidden))
        return out

    def hit_rates(case_list, alpha=None):
        h3 = h5 = 0
        for visible, hidden in case_list:
            if alpha is None:  # popularity baseline
                ranked = [c for c in popular.index if c not in visible][:5]
            else:
                ranked = [r["category"] for r in recommend_categories(visible, sim, popular, 5, alpha)]
            h3 += hidden in ranked[:3]
            h5 += hidden in ranked[:5]
        n = len(case_list) or 1
        return {"hit_rate@3": round(h3 / n, 4), "hit_rate@5": round(h5 / n, 4)}

    val_cases, test_cases = cases(val_ids), cases(test_ids)
    val = {a: hit_rates(val_cases, a) for a in ALPHAS}
    best_alpha = max(ALPHAS, key=lambda a: (val[a]["hit_rate@3"] + val[a]["hit_rate@5"], -a))
    return {
        "train_customers": int(train["customer_id"].nunique()),
        "validation_customers": len(val_cases),
        "test_customers": len(test_cases),
        "alpha": best_alpha,
        "validation_by_alpha": {str(a): v for a, v in val.items()},
        "test": {
            "collaborative_filtering": hit_rates(test_cases, 0.0),
            "hybrid": hit_rates(test_cases, best_alpha),
            "popularity_baseline": hit_rates(test_cases, None),
        },
    }


def category_labels(db) -> dict:
    return {d["_id"]: d["label"] for d in db[COLL_PRODUCTS].aggregate([
        {"$group": {"_id": "$category", "label": {"$first": "$category_label"}}}])}


def save_similarity(db, sim: pd.DataFrame, popular: pd.Series):
    labels = category_labels(db)
    now = datetime.now(timezone.utc)
    docs = []
    for cat in sim.index:
        row = sim.loc[cat].sort_values(ascending=False)
        row = row[row > 0].head(TOP_NEIGHBOURS)
        docs.append({
            "_id": cat,
            "label": labels.get(cat, cat),
            "buyers": int(popular.get(cat, 0)),
            "popularity_rank": int(list(popular.index).index(cat)) + 1 if cat in popular.index else None,
            "similar": [{"category": c, "score": round(float(s), 4)} for c, s in row.items()],
            "computed_at": now,
        })
    db[COLL_CATEGORY_SIMILARITY].delete_many({})
    if docs:
        db[COLL_CATEGORY_SIMILARITY].insert_many(docs)


META_PATH = os.path.join(MODEL_DIR, "cf_meta.json")


def save_meta(meta: dict):
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(META_PATH, "w") as fh:
        json.dump(meta, fh, indent=2, default=str)


def load_alpha() -> float:
    try:
        with open(META_PATH) as fh:
            return float(json.load(fh).get("alpha", 0.0))
    except (OSError, ValueError):
        return 0.0


def load_saved_model(db):
    """(similarity DataFrame, popularity Series, alpha) rebuilt from category_similarity."""
    docs = list(db[COLL_CATEGORY_SIMILARITY].find({}))
    if not docs:
        return None, None, 0.0
    cats = [d["_id"] for d in docs]
    sim = pd.DataFrame(0.0, index=cats, columns=cats)
    for d in docs:
        for n in d.get("similar", []):
            if n["category"] in sim.columns:
                sim.loc[d["_id"], n["category"]] = n["score"]
    popular = pd.Series({d["_id"]: d.get("buyers", 0) for d in docs}).sort_values(ascending=False)
    return sim, popular, load_alpha()


def run(db, verbose: bool = True) -> dict:
    df = load_affinity_frame(db)
    sim = build_similarity(df)
    popular = popularity(df)
    save_similarity(db, sim, popular)
    metrics = evaluate(df) if df["customer_id"].nunique() >= 50 else {"alpha": 0.0}
    metrics.update({"categories": int(len(sim)), "customers": int(df["customer_id"].nunique())})
    save_meta({"alpha": metrics.get("alpha", 0.0), "evaluation": metrics.get("test"),
               "trained_at": datetime.now(timezone.utc)})
    if verbose:
        print(f"Module 2: similarity for {len(sim)} categories saved to '{COLL_CATEGORY_SIMILARITY}'.")
        if "test" in metrics:
            t = metrics["test"]
            print(f"  Test HitRate@3/@5 ({metrics['test_customers']} customers): "
                  f"CF {t['collaborative_filtering']}, hybrid(alpha={metrics['alpha']}) {t['hybrid']}, "
                  f"popularity {t['popularity_baseline']}")
    return metrics


def get_recommendations(db, customer_id: str, top_n: int = 3) -> list:
    """Convenience entry point: categories recommended for one customer."""
    sim, popular, alpha = load_saved_model(db)
    if sim is None:
        df = load_affinity_frame(db)
        sim, popular, alpha = build_similarity(df), popularity(df), 0.0
    rows = db[COLL_AFFINITY].find({"_id.customer_id": customer_id}, {"_id": 1, "spend": 1})
    spend = {r["_id"]["category"]: float(r.get("spend") or 0) for r in rows}
    return [r["category"] for r in recommend_categories(spend, sim, popular, top_n, alpha)]


if __name__ == "__main__":
    from config import get_db
    run(get_db())
