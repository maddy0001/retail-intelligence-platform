"""
run_all.py
----------
Runs the whole analytics chain in order and records the run in `ml_runs`:

    Pipeline A (RFM) -> Pipeline B (affinity) -> Pipeline C ($setWindowFields)
    -> Module 1 (K-Means) -> Module 2 (collaborative filtering) -> Module 3 (Isolation Forest)

Every model reads only the aggregation output that feeds it. The admin page
of the app calls run_all() in a background thread; from the CLI:

    python ml/run_all.py
"""

import os
import sys
import time
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COLL_ML_RUNS  # noqa: E402
from pipelines import pipeline_a_rfm, pipeline_b_affinity, pipeline_c_rolling_metrics  # noqa: E402
from ml import module1_kmeans, module2_collaborative_filtering, module3_isolation_forest  # noqa: E402

STEPS = [
    ("Pipeline A — RFM ($group + $lookup)", lambda db: {"rfm_rows": pipeline_a_rfm.run(db, verbose=False)}),
    ("Pipeline B — category affinity ($unwind + $group)", lambda db: {"affinity_rows": pipeline_b_affinity.run(db, verbose=False)}),
    ("Pipeline C — rolling metrics ($setWindowFields)", lambda db: {"rolling_rows": pipeline_c_rolling_metrics.run(db, verbose=False)}),
    ("Module 1 — K-Means segments", lambda db: module1_kmeans.run(db, verbose=False)),
    ("Module 2 — collaborative filtering", lambda db: module2_collaborative_filtering.run(db, verbose=False)),
    ("Module 3 — Isolation Forest risk", lambda db: module3_isolation_forest.run(db, verbose=False)),
]


def run_all(db, triggered_by: str = "cli", log=print, on_step=None) -> dict:
    run_doc = {"started_at": datetime.now(timezone.utc), "triggered_by": triggered_by,
               "status": "running", "steps": []}
    run_id = db[COLL_ML_RUNS].insert_one(run_doc).inserted_id
    t_all = time.time()
    try:
        for name, fn in STEPS:
            t0 = time.time()
            result = fn(db)
            step = {"name": name, "seconds": round(time.time() - t0, 2), "result": result}
            db[COLL_ML_RUNS].update_one({"_id": run_id}, {"$push": {"steps": step}})
            log(f"[{step['seconds']:>6.2f}s] {name}: {result}")
            if on_step:
                on_step(step)
        status = "succeeded"
        error = None
    except Exception as exc:  # recorded on the run document, then re-raised
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        log(f"Analytics run failed: {error}")
    finished = {"status": status, "error": error, "finished_at": datetime.now(timezone.utc),
                "duration_s": round(time.time() - t_all, 2)}
    db[COLL_ML_RUNS].update_one({"_id": run_id}, {"$set": finished})
    if error:
        raise RuntimeError(error)
    return db[COLL_ML_RUNS].find_one({"_id": run_id})


if __name__ == "__main__":
    from config import get_db
    doc = run_all(get_db())
    print(f"\nRun {doc['_id']} {doc['status']} in {doc['duration_s']}s")
