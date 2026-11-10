"""
module3_isolation_forest.py
-----------------------------
MODULE 3 — Behavioral Anomaly Intelligence (Isolation Forest)

Input: Pipeline C's `rolling_behavioral_metrics` collection ($setWindowFields
output). An aggregation picks the latest row per customer ($sort + $group
with $last), which is that customer's current feature vector:
  rolling_event_count_7d   events in the trailing 7 days (RANGE window)
  avg_session_gap_seconds  mean gap over the last 10 events (DOCUMENTS window)
  cart_to_purchase_trend   share of purchases in the last 10 events
  cart_abandon_trend       share of abandoned carts in the last 10 events
A missing gap (a customer's very first event) is filled with the median gap
rather than 0, because a 0-second gap would itself look like bot behaviour.
The count and the gap are log1p-transformed before training: gaps range from
~2 seconds to days, and on a raw scale Isolation Forest's random splits would
almost all land in the long tail and never separate the very fast clickers.

Output: an anomaly score and a LOW / MEDIUM / HIGH risk label per customer,
written back onto customers.anomaly. Labels come from percentiles of the
training score distribution (bottom 10% = HIGH, next 20% = MEDIUM), so they
stay meaningful if the score scale drifts. The model, fill values and cut
points are saved to ml/models/isolation_forest.joblib so the API can score a
single customer live when a Change Stream trigger fires.

Evaluation: the event simulator gives ~3% of simulated customers an
"intense" persona. That persona is known by construction (it is synthetic),
so we can measure how many of them the model rates HIGH (recall) and how many
HIGH customers are intense (precision). The persona is NEVER a model feature.

Why Isolation Forest over a deep autoencoder: 3 numeric features per
customer, no labels, a 4-week timeline. Isolation Forest is built for
low-dimensional tabular anomaly detection, trains in well under a second,
and its score buckets naturally into LOW/MEDIUM/HIGH; an autoencoder would
need more data and tuning and give a less interpretable reconstruction error.
"""

import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from pymongo import UpdateOne
from sklearn.ensemble import IsolationForest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_ROLLING_METRICS, COLL_CUSTOMERS, COLL_EVENTS, MODEL_DIR  # noqa: E402

FEATURES = ["rolling_event_count_7d", "avg_session_gap_seconds", "cart_to_purchase_trend", "cart_abandon_trend"]
LOG_FEATURES = ["rolling_event_count_7d", "avg_session_gap_seconds"]
MODEL_PATH = os.path.join(MODEL_DIR, "isolation_forest.joblib")
HIGH_PCT, MEDIUM_PCT = 0.10, 0.30


def model_matrix(df: pd.DataFrame, fills: dict) -> pd.DataFrame:
    """Feature matrix the model sees: fill gaps, then log1p the skewed columns."""
    X = df[FEATURES].astype(float).fillna(fills)
    for f in LOG_FEATURES:
        X[f] = np.log1p(X[f].clip(lower=0))
    return X


def latest_metrics_pipeline(customer_id: str = None):
    stages = [{"$match": {"customer_id": customer_id}}] if customer_id else []
    return stages + [
        {"$sort": {"customer_id": 1, "timestamp": 1}},
        {"$group": {"_id": "$customer_id", "doc": {"$last": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
    ]


def load_latest_metrics_per_customer(db) -> pd.DataFrame:
    docs = list(db[COLL_ROLLING_METRICS].aggregate(latest_metrics_pipeline(), allowDiskUse=True))
    if not docs:
        raise RuntimeError(
            f"'{COLL_ROLLING_METRICS}' is empty — run pipelines/pipeline_c_rolling_metrics.py first."
        )
    df = pd.DataFrame(docs)
    for f in FEATURES:
        if f not in df.columns:
            df[f] = np.nan
    return df


def fill_values(df: pd.DataFrame) -> dict:
    gap = df["avg_session_gap_seconds"].median()
    return {"rolling_event_count_7d": 0.0,
            "avg_session_gap_seconds": float(gap) if pd.notna(gap) else 60.0,
            "cart_to_purchase_trend": 0.0,
            "cart_abandon_trend": 0.0}


def risk_label_from_score(score: float, high_cut: float, medium_cut: float) -> str:
    # sklearn's decision_function: lower (more negative) = more anomalous.
    if score < high_cut:
        return "HIGH"
    if score < medium_cut:
        return "MEDIUM"
    return "LOW"


def persona_evaluation(db, df: pd.DataFrame) -> dict:
    """Compare HIGH labels with the simulator's known 'intense' persona (evaluation only)."""
    personas = {d["_id"]: d["persona"] for d in db[COLL_EVENTS].aggregate([
        {"$match": {"metadata.source": "simulator"}},
        {"$group": {"_id": "$customer_id", "persona": {"$first": "$metadata.persona"}}},
    ], allowDiskUse=True)}
    if not personas:
        return {}
    sim = df[df["customer_id"].isin(personas)].copy()
    sim["intense"] = sim["customer_id"].map(personas).eq("intense")
    intense = int(sim["intense"].sum())
    high = sim["risk_label"].eq("HIGH")
    high_or_med = sim["risk_label"].isin(["HIGH", "MEDIUM"])
    tp = int((high & sim["intense"]).sum())
    return {
        "simulated_customers": int(len(sim)),
        "intense_customers": intense,
        "recall_high": round(tp / intense, 4) if intense else None,
        "precision_high": round(tp / int(high.sum()), 4) if int(high.sum()) else None,
        "recall_high_or_medium": round(int((high_or_med & sim["intense"]).sum()) / intense, 4) if intense else None,
    }


def run(db, contamination: float = 0.1, verbose: bool = True) -> dict:
    df = load_latest_metrics_per_customer(db)
    fills = fill_values(df)
    X = model_matrix(df, fills)

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,   # expected anomaly fraction — course-project assumption
        random_state=42,
    )
    model.fit(X)
    df["anomaly_score"] = model.decision_function(X)

    # Bucket into LOW/MEDIUM/HIGH via percentiles of the score distribution
    # rather than a fixed threshold, so labeling is robust to scale drift.
    high_cut = float(df["anomaly_score"].quantile(HIGH_PCT))
    medium_cut = float(df["anomaly_score"].quantile(MEDIUM_PCT))
    df["risk_label"] = df["anomaly_score"].apply(lambda s: risk_label_from_score(s, high_cut, medium_cut))

    now = datetime.now(timezone.utc)
    ops = [UpdateOne({"_id": row.customer_id}, {"$set": {
        "anomaly.risk_label": row.risk_label,
        "anomaly.score": round(float(row.anomaly_score), 5),
        "anomaly.method": "isolation-forest",
        "anomaly.computed_at": now,
    }}) for row in df.itertuples(index=False)]
    for i in range(0, len(ops), 5_000):
        db[COLL_CUSTOMERS].bulk_write(ops[i:i + 5_000], ordered=False)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump({"model": model, "fills": fills, "high_cut": high_cut, "medium_cut": medium_cut,
                 "features": FEATURES, "trained_at": now}, MODEL_PATH)

    counts = df["risk_label"].value_counts().to_dict()
    metrics = {"customers_scored": int(len(df)), "risk_counts": {k: int(v) for k, v in counts.items()},
               "high_cut": round(high_cut, 5), "medium_cut": round(medium_cut, 5),
               "contamination": contamination, "persona_evaluation": persona_evaluation(db, df)}
    if verbose:
        print(f"Wrote anomaly scores for {len(df):,} customers back to '{COLL_CUSTOMERS}': {counts}")
        if metrics["persona_evaluation"]:
            print(f"  Persona check: {metrics['persona_evaluation']}")
    return metrics


def load_model():
    return joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else None


def score_customer(db, customer_id: str):
    """Live path used by the API's Change Stream worker: score one customer's
    latest $setWindowFields row with the saved model and write it back."""
    bundle = load_model()
    rows = list(db[COLL_ROLLING_METRICS].aggregate(latest_metrics_pipeline(customer_id)))
    if bundle is None or not rows:
        return None
    row = rows[0]
    features = {f: (row.get(f) if row.get(f) is not None else bundle["fills"][f]) for f in FEATURES}
    X = model_matrix(pd.DataFrame([features]), bundle["fills"])
    score = float(bundle["model"].decision_function(X)[0])
    label = risk_label_from_score(score, bundle["high_cut"], bundle["medium_cut"])
    db[COLL_CUSTOMERS].update_one({"_id": customer_id}, {"$set": {
        "anomaly.risk_label": label, "anomaly.score": round(score, 5),
        "anomaly.method": "isolation-forest-live", "anomaly.computed_at": datetime.now(timezone.utc),
    }})
    return {"risk_label": label, "score": round(score, 5), "features": features}


if __name__ == "__main__":
    from config import get_db
    run(get_db())
