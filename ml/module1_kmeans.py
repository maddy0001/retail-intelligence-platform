"""
module1_kmeans.py
------------------
MODULE 1 — Customer Intelligence (K-Means)

Input: Pipeline A's `rfm_features` collection, pulled via pymongo into a
pandas DataFrame. No raw order documents are read here — every feature is
traceable to the RFM aggregation output.

Preprocessing: Frequency and Monetary are heavily right-skewed (most people
order once; a few spend thousands), so both are log1p-transformed before
standard scaling. Without this, K-Means spends its clusters on a handful of
big spenders.

Choosing k: silhouette score over k = 4..6, computed on a 10,000-row random
sample (silhouette is O(n^2), and ~93k customers would take minutes for no
gain in the estimate). The lower bound of 4 is a business requirement: the
store's offers need at least four actionable segments.

Naming clusters: deterministic rules on the cluster centroids (in real
units), not a black box:
  1. High-Value Loyal  -> highest mean frequency (the repeat buyers)
  2. At-Risk           -> of the rest, the longest time since last order
  3. Bargain Browser   -> of the rest, the lowest mean spend
  4. Big Spender       -> of the rest, the highest mean spend (one-time, high basket)
  5+ Occasional Shopper / Dormant for any extra clusters
"New Customer" is not a K-Means cluster: it is the rule-based label the app
gives a sign-up who has no completed order yet (segment.method = "rule").
On real Olist data no cluster is "new" in absolute terms, because the
newest historical order is from October 2018.

Why K-Means over a heavier alternative: RFM segmentation is a low-dimensional
(3-feature) clustering problem where clusters are roughly convex. K-Means
trains in well under a second on ~93k customers and gives directly
interpretable centroids. A Gaussian Mixture or a deep embedding clustering
would add tuning and interpretability cost the timeline doesn't justify.

The fitted scaler + model + names are saved to ml/models/kmeans_rfm.joblib so
the API can place a single customer into a segment right after a purchase.
"""

import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from pymongo import UpdateOne
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_RFM, COLL_CUSTOMERS, MODEL_DIR  # noqa: E402

FEATURES = ["recency_days", "frequency", "monetary"]
MODEL_PATH = os.path.join(MODEL_DIR, "kmeans_rfm.joblib")
EXTRA_LABELS = ["Occasional Shopper", "Dormant", "Segment 7", "Segment 8"]


def load_rfm(db) -> pd.DataFrame:
    docs = list(db[COLL_RFM].find({}, {"_id": 1, **{f: 1 for f in FEATURES}}))
    if not docs:
        raise RuntimeError(f"'{COLL_RFM}' is empty — run pipelines/pipeline_a_rfm.py first.")
    df = pd.DataFrame(docs).rename(columns={"_id": "customer_id"})
    return df[["customer_id"] + FEATURES].dropna().reset_index(drop=True)


def transform(df: pd.DataFrame) -> np.ndarray:
    """recency as-is; frequency and monetary log1p (right-skewed)."""
    return np.column_stack([
        df["recency_days"].to_numpy(dtype=float),
        np.log1p(df["frequency"].to_numpy(dtype=float)),
        np.log1p(df["monetary"].to_numpy(dtype=float)),
    ])


def choose_k(X_scaled, k_range=range(4, 7), sample_size=10_000, seed=42):
    """Best silhouette (on a sample) in a small, sane range; inertia kept for the elbow plot."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X_scaled), size=min(sample_size, len(X_scaled)), replace=False)
    silhouettes, inertias = {}, {}
    for k in k_range:
        if k >= len(X_scaled):
            break
        model = KMeans(n_clusters=k, random_state=seed, n_init=10)
        labels = model.fit_predict(X_scaled)
        inertias[k] = float(model.inertia_)
        silhouettes[k] = float(silhouette_score(X_scaled[idx], labels[idx]))
    best_k = max(silhouettes, key=silhouettes.get)
    return best_k, silhouettes, inertias


def name_clusters(df: pd.DataFrame) -> dict:
    """Deterministic, explainable names from cluster centroids (see module docstring)."""
    stats = df.groupby("cluster")[FEATURES].mean()
    remaining = list(stats.index)
    names = {}

    def take(cluster_id, label):
        names[int(cluster_id)] = label
        remaining.remove(cluster_id)

    take(stats["frequency"].idxmax(), "High-Value Loyal")
    if remaining:
        take(stats.loc[remaining, "recency_days"].idxmax(), "At-Risk")
    if remaining:
        take(stats.loc[remaining, "monetary"].idxmin(), "Bargain Browser")
    if remaining:
        take(stats.loc[remaining, "monetary"].idxmax(), "Big Spender")
    for label, cluster_id in zip(EXTRA_LABELS, sorted(remaining, key=lambda c: stats.loc[c, "recency_days"])):
        names[int(cluster_id)] = label
    return names


def save_model(scaler, model, names, k, silhouettes):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump({"scaler": scaler, "model": model, "names": names, "k": k,
                 "silhouettes": silhouettes, "features": FEATURES,
                 "trained_at": datetime.now(timezone.utc)}, MODEL_PATH)


def load_model():
    return joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else None


def run(db, k: int = None, verbose: bool = True) -> dict:
    df = load_rfm(db)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(transform(df))

    if k is None and len(df) >= 50:
        k, silhouettes, inertias = choose_k(X_scaled)
    else:  # tiny datasets (offline tests): fixed k, no search
        k = k or min(4, max(2, len(df) // 5))
        silhouettes, inertias = {}, {}

    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    df["cluster"] = model.fit_predict(X_scaled)
    names = name_clusters(df)
    df["segment_label"] = df["cluster"].map(names)

    now = datetime.now(timezone.utc)
    ops = [UpdateOne({"_id": row.customer_id}, {"$set": {
        "segment.label": row.segment_label,
        "segment.cluster_id": int(row.cluster),
        "segment.method": "kmeans",
        "segment.computed_at": now,
    }}) for row in df.itertuples(index=False)]
    for i in range(0, len(ops), 5_000):
        db[COLL_CUSTOMERS].bulk_write(ops[i:i + 5_000], ordered=False)
    save_model(scaler, model, names, k, silhouettes)

    centroids = df.groupby("segment_label")[FEATURES].mean().round(2)
    counts = df["segment_label"].value_counts().to_dict()
    if verbose:
        print(f"Chosen k={k} (silhouette by k: { {kk: round(v, 3) for kk, v in silhouettes.items()} })")
        print(f"Wrote segment labels for {len(df):,} customers back to '{COLL_CUSTOMERS}'.")
        print(centroids.assign(customers=pd.Series(counts)).to_string())
    return {
        "k": int(k),
        "silhouette_by_k": {str(kk): round(v, 4) for kk, v in silhouettes.items()},
        "inertia_by_k": {str(kk): round(v, 1) for kk, v in inertias.items()},
        "segment_counts": {str(kk): int(v) for kk, v in counts.items()},
        "centroids": {seg: {f: float(v) for f, v in row.items()} for seg, row in centroids.iterrows()},
        "customers_labeled": int(len(df)),
    }


def assign_segment(db, customer_id: str):
    """Live path used by the API after a purchase: read this customer's RFM
    row (Pipeline A, scoped) and place it with the saved model."""
    bundle = load_model()
    row = db[COLL_RFM].find_one({"_id": customer_id})
    if bundle is None or row is None:
        return None
    X = bundle["scaler"].transform(transform(pd.DataFrame([row])))
    cluster = int(bundle["model"].predict(X)[0])
    label = bundle["names"].get(cluster, f"Segment {cluster}")
    db[COLL_CUSTOMERS].update_one({"_id": customer_id}, {"$set": {
        "segment.label": label, "segment.cluster_id": cluster,
        "segment.method": "kmeans-live", "segment.computed_at": datetime.now(timezone.utc),
    }})
    return label


if __name__ == "__main__":
    from config import get_db
    run(get_db())
