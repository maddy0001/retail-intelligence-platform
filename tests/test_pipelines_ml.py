"""
Pipelines A/B/C and ML modules 1-3, run against a REAL MongoDB (the throw-away
`retail_intel_test` database), so $setWindowFields, $merge and $lookup are
actually executed — not mocked. Data comes from the placeholder fixture
(data/generate_sample_seed.py), never from the real database.

Run from retail-intelligence-platform/:   venv/bin/python -m pytest
"""

import os
import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from config import (COLL_AFFINITY, COLL_CATEGORY_SIMILARITY, COLL_CUSTOMERS, COLL_EVENTS, COLL_ORDERS,
                    COLL_RFM, COLL_ROLLING_METRICS, COMPLETED_STATUSES, get_db)
from data.generate_sample_seed import seed
from ml import module1_kmeans, module2_collaborative_filtering, module3_isolation_forest
from pipelines import pipeline_a_rfm, pipeline_b_affinity, pipeline_c_rolling_metrics

INTENSE = 4


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "retail_intel_test", "tests must never run against the real database"
    database.client.drop_database(database.name)
    customers, products, _ = seed(database, n_customers=60, n_orders=320, n_products=24)

    # Fixture events shaped like the simulator's output (labelled as such only
    # inside this throw-away database). The first INTENSE customers click every
    # ~2 s and abandon carts; the rest behave normally.
    rng = random.Random(11)
    now = datetime.now(timezone.utc)
    events = []
    for idx, c in enumerate(customers[:50]):
        intense = idx < INTENSE
        t = now - timedelta(days=rng.uniform(0.5, 6))
        for k in range(30 if intense else rng.randint(4, 12)):
            etype = (rng.choice(["view_product", "add_to_cart", "cart_abandon"]) if intense else
                     rng.choices(["view_product", "add_to_cart", "cart_abandon", "purchase"], [70, 15, 8, 7])[0])
            p = rng.choice(products)
            events.append({"_id": f"e_fx_{idx}_{k}", "customer_id": c["_id"], "session_id": None,
                           "event_type": etype, "timestamp": t, "product_id": p["product_id"],
                           "category": p["category"],
                           "metadata": {"source": "simulator", "is_synthetic": True,
                                        "persona": "intense" if intense else "normal"}})
            t += timedelta(seconds=rng.expovariate(1 / 2.0) if intense else rng.expovariate(1 / 900.0))
    database[COLL_EVENTS].insert_many(events)
    yield database
    database.client.drop_database(database.name)


def test_pipeline_a_frequency_counts_completed_orders(db):
    assert pipeline_a_rfm.run(db, verbose=False) > 0
    row = db[COLL_RFM].find_one(sort=[("frequency", -1)])
    expected = db[COLL_ORDERS].count_documents({"customer_id": row["_id"], "order_status": {"$in": COMPLETED_STATUSES}})
    assert row["frequency"] == expected >= 2
    assert row["recency_days"] >= 0
    assert row["customer_profile"]["source"] == "fixture"


def test_pipeline_a_scoped_rerun_rebuilds_one_customer(db):
    cid = db[COLL_RFM].find_one()["_id"]
    db[COLL_RFM].delete_one({"_id": cid})
    assert pipeline_a_rfm.run(db, customer_id=cid, verbose=False) == 1


def test_pipeline_b_spend_matches_line_items(db):
    pipeline_b_affinity.run(db, verbose=False)
    doc = db[COLL_AFFINITY].find_one(sort=[("spend", -1)])
    cid, cat = doc["_id"]["customer_id"], doc["_id"]["category"]
    spend = sum(li["unit_price"] * li["quantity"]
                for o in db[COLL_ORDERS].find({"customer_id": cid, "order_status": {"$in": COMPLETED_STATUSES}})
                for li in o["line_items"] if li["category"] == cat)
    assert doc["spend"] == pytest.approx(round(spend, 2), abs=0.02)


def test_pipeline_c_set_window_fields_matches_hand_computation(db):
    pipeline_c_rolling_metrics.run(db, verbose=False)
    cid = db[COLL_EVENTS].find_one({"metadata.persona": "normal"})["customer_id"]
    events = list(db[COLL_EVENTS].find({"customer_id": cid}).sort("timestamp", 1))
    rows = list(db[COLL_ROLLING_METRICS].find({"customer_id": cid}).sort("timestamp", 1))
    assert len(rows) == len(events)
    for i, r in enumerate(rows):   # RANGE window: events in [t - 7 days, t]
        ts = events[i]["timestamp"]
        assert r["rolling_event_count_7d"] == sum(1 for e in events if ts - timedelta(days=7) <= e["timestamp"] <= ts)
    assert rows[0]["session_gap_seconds"] is None            # $shift has no previous row
    gap = (events[1]["timestamp"] - events[0]["timestamp"]).total_seconds()
    assert rows[1]["session_gap_seconds"] == pytest.approx(gap, abs=0.01)
    last10 = events[-10:]                                     # DOCUMENTS window [-9, 0]
    assert rows[-1]["cart_abandon_trend"] == pytest.approx(sum(e["event_type"] == "cart_abandon" for e in last10) / len(last10))
    gaps = [g for g in (r["session_gap_seconds"] for r in rows[-10:]) if g is not None]
    assert rows[-1]["avg_session_gap_seconds"] == pytest.approx(sum(gaps) / len(gaps), rel=1e-6)


def test_module1_kmeans_labels_customers_and_saves_model(db):
    metrics = module1_kmeans.run(db, verbose=False)
    assert metrics["k"] >= 4
    assert "High-Value Loyal" in metrics["segment_counts"]
    assert db[COLL_CUSTOMERS].count_documents({"segment.method": "kmeans"}) == metrics["customers_labeled"]
    assert os.path.exists(module1_kmeans.MODEL_PATH)
    cid = db[COLL_RFM].find_one()["_id"]
    assert module1_kmeans.assign_segment(db, cid) in metrics["segment_counts"]


def test_module2_recommends_only_unbought_categories(db):
    metrics = module2_collaborative_filtering.run(db, verbose=False)
    assert metrics["categories"] == db[COLL_CATEGORY_SIMILARITY].count_documents({})
    # the customer with the fewest categories, so there is something left to recommend
    cid = next(db[COLL_AFFINITY].aggregate([
        {"$group": {"_id": "$_id.customer_id", "n": {"$sum": 1}}}, {"$sort": {"n": 1, "_id": 1}}, {"$limit": 1}]))["_id"]
    bought = set(db[COLL_AFFINITY].distinct("_id.category", {"_id.customer_id": cid}))
    recs = module2_collaborative_filtering.get_recommendations(db, cid, top_n=3)
    assert len(recs) == min(3, metrics["categories"] - len(bought))
    assert not (set(recs) & bought)


def test_module2_evaluation_compares_three_rankers():
    rng = random.Random(5)
    cats = [f"c{i}" for i in range(8)]
    rows = []
    for n in range(400):   # customers who buy "c0" tend to also buy "c1"
        picks = ["c0", "c1"] if n % 3 == 0 else sorted(rng.sample(cats, rng.randint(1, 3)))
        rows += [{"customer_id": f"u{n}", "category": c, "spend": rng.uniform(10, 200)} for c in picks]
    result = module2_collaborative_filtering.evaluate(pd.DataFrame(rows))
    assert set(result["test"]) == {"collaborative_filtering", "hybrid", "popularity_baseline"}
    for ranker in result["test"].values():
        assert 0 <= ranker["hit_rate@3"] <= ranker["hit_rate@5"] <= 1
    # alpha is the validation winner (ties go to the smaller alpha)
    val = result["validation_by_alpha"]
    best = max(v["hit_rate@3"] + v["hit_rate@5"] for v in val.values())
    winners = [float(a) for a, v in val.items() if v["hit_rate@3"] + v["hit_rate@5"] == best]
    assert result["alpha"] == min(winners)


def test_module3_flags_the_intense_customers(db):
    metrics = module3_isolation_forest.run(db, verbose=False)
    assert set(metrics["risk_counts"]) <= {"LOW", "MEDIUM", "HIGH"}
    persona = metrics["persona_evaluation"]
    assert persona["intense_customers"] == INTENSE
    assert persona["recall_high_or_medium"] >= 0.75
    cid = db[COLL_CUSTOMERS].find_one({"anomaly.method": "isolation-forest"})["_id"]
    batch_label = db[COLL_CUSTOMERS].find_one({"_id": cid})["anomaly"]["risk_label"]
    assert module3_isolation_forest.score_customer(db, cid)["risk_label"] == batch_label


def test_run_all_records_every_step(db):
    from ml.run_all import run_all
    doc = run_all(db, triggered_by="pytest", log=lambda *_: None)
    assert doc["status"] == "succeeded"
    assert len(doc["steps"]) == 6
