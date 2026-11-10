"""
event_simulator.py
-------------------
*** SYNTHETIC DATA GENERATOR ***

Generates clickstream events (browse -> add_to_cart -> purchase / abandon)
for customers already loaded from the REAL Olist dataset. Every document this
script writes carries `metadata.is_synthetic: true` and
`metadata.source: "simulator"`, and is inserted only into the `events`
collection — never merged into `customers`, `orders`, `products` or
`reviews`, which hold real transactional data.

Who gets events: only customers who have at least one completed real order,
so every simulated customer also has a segment (RFM) and recommendations
(category affinity). A fixed pool of "active" customers is drawn first and
sessions are spread over that pool, so each one builds up a real history for
the 7-day $setWindowFields metrics.

Documented assumptions (also stated in the report's Data Provenance and
Limitations sections):
  - Cart-abandonment rate: ~70%, based on the commonly cited Baymard
    Institute e-commerce cart-abandonment benchmark range (~65-75%).
  - Session length: log-normal distribution (many short sessions, a long
    tail of long ones) — a standard shape in clickstream simulation.
  - Time between events in a session: exponential distribution, i.e. a
    Poisson click process, mean ~25 s.
  - What people browse: 60% of product views come from categories the
    customer really bought from (their Olist order history); the rest are
    drawn from the whole catalog weighted by real sales counts.
  - Personas: ~3% of simulated customers follow an "intense" profile (long
    sessions, ~2 s between clicks, frequent cart abandonment). They give the
    anomaly detector realistic outliers to find, and because the persona is
    known by construction it can be used to EVALUATE Module 3 — it is never
    used as a model feature.

Usage:
    # One-shot batch generation over the past 14 days
    python simulator/event_simulator.py --mode batch --n-customers 1500 --n-sessions 6000

    # Live streaming mode (for demonstrating Change Streams)
    python simulator/event_simulator.py --mode live --sessions-per-min 20
"""

import argparse
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_db, COLL_ORDERS, COLL_PRODUCTS, COLL_EVENTS, COMPLETED_STATUSES  # noqa: E402

CART_ABANDON_RATE = 0.70          # documented assumption, see module docstring
OWN_CATEGORY_SHARE = 0.60         # share of views from the customer's own past categories
INTENSE_PERSONA_SHARE = 0.03      # share of simulated customers with an "intense" profile
CHANNELS = ["mobile_app", "web"]


def sample_session_length(persona: str) -> int:
    """Log-normal: most sessions are short, a long tail of longer ones."""
    if persona == "intense":
        return max(8, int(round(random.lognormvariate(2.8, 0.3))))
    return max(1, int(round(random.lognormvariate(1.3, 0.6))))


def sample_gap_seconds(persona: str) -> float:
    """Exponential inter-event gap -> Poisson click process."""
    return random.expovariate(1 / (2.0 if persona == "intense" else 25.0))


class Catalog:
    """Products grouped by category, with real sales counts as sampling weights."""

    def __init__(self, db):
        docs = list(db[COLL_PRODUCTS].find({}, {"product_id": 1, "category": 1, "sales_count": 1}))
        if not docs:
            raise RuntimeError("products is empty. Load real data first (data/load_olist_data.py).")
        self.all = docs
        self.weights = [d.get("sales_count", 0) + 1 for d in docs]
        self.by_category = {}
        for d in docs:
            self.by_category.setdefault(d["category"], []).append(d)

    def pick(self, own_categories=None):
        if own_categories and random.random() < OWN_CATEGORY_SHARE:
            pool = self.by_category.get(random.choice(own_categories))
            if pool:
                return random.choice(pool)
        return random.choices(self.all, weights=self.weights, k=1)[0]


def load_active_customers(db, n_customers: int, seed: int = None):
    """Draw customers who have >=1 completed real order, with the categories they bought."""
    rng = random.Random(seed)
    pipeline = [
        {"$match": {"order_status": {"$in": COMPLETED_STATUSES}, "source": "olist"}},
        {"$unwind": "$line_items"},
        {"$group": {"_id": "$customer_id", "categories": {"$addToSet": "$line_items.category"}}},
    ]
    customers = list(db[COLL_ORDERS].aggregate(pipeline, allowDiskUse=True))
    if not customers:
        raise RuntimeError("No completed orders found. Load real data first (data/load_olist_data.py).")
    chosen = rng.sample(customers, min(n_customers, len(customers)))
    for c in chosen:
        c["persona"] = "intense" if rng.random() < INTENSE_PERSONA_SHARE else "normal"
    return chosen


def _event(customer, session_id, event_type, ts, product, channel):
    return {
        "_id": f"e_{uuid.uuid4().hex[:16]}",
        "customer_id": customer["_id"],
        "session_id": session_id,
        "event_type": event_type,
        "timestamp": ts,
        "product_id": product["product_id"] if product else None,
        "category": product["category"] if product else None,
        "metadata": {"channel": channel, "is_synthetic": True, "source": "simulator",
                     "persona": customer.get("persona", "normal")},
    }


def build_session_events(customer, catalog: Catalog, start_time: datetime):
    persona = customer.get("persona", "normal")
    session_id = f"s_{uuid.uuid4().hex[:10]}"
    channel = random.choice(CHANNELS)
    n_events = sample_session_length(persona)
    events, t, browsed = [], start_time, []

    # Browse phase
    for _ in range(max(1, n_events - 2)):
        product = catalog.pick(customer.get("categories"))
        browsed.append(product)
        events.append(_event(customer, session_id, "view_product", t, product, channel))
        t += timedelta(seconds=sample_gap_seconds(persona))

    # Cart phase: ~55% of sessions add something to the cart
    added = []
    if browsed and random.random() < 0.55:
        added = random.sample(browsed, random.randint(1, min(3, len(browsed))))
        for product in added:
            events.append(_event(customer, session_id, "add_to_cart", t, product, channel))
            t += timedelta(seconds=sample_gap_seconds(persona))

    # Purchase or abandon, governed by CART_ABANDON_RATE (intense persona abandons more)
    abandon_rate = 0.9 if persona == "intense" else CART_ABANDON_RATE
    if added and random.random() > abandon_rate:
        for product in added:
            events.append(_event(customer, session_id, "purchase", t, product, channel))
    elif added:
        events.append(_event(customer, session_id, "cart_abandon", t, None, channel))
    return events


def run_batch(db, n_customers=1500, n_sessions=6000, days=14, seed=None):
    if seed is not None:
        random.seed(seed)
    catalog = Catalog(db)
    customers = load_active_customers(db, n_customers, seed)
    now = datetime.now(timezone.utc)
    all_events = []
    for _ in range(n_sessions):
        customer = random.choice(customers)
        if customer["persona"] == "intense" and random.random() < 0.5:
            customer = random.choice(customers)  # keep intense customers a minority of sessions too
        start = now - timedelta(minutes=random.randint(5, 60 * 24 * days))
        all_events.extend(build_session_events(customer, catalog, start))
    for i in range(0, len(all_events), 10_000):
        db[COLL_EVENTS].insert_many(all_events[i:i + 10_000], ordered=False)
    intense = sum(1 for c in customers if c["persona"] == "intense")
    print(f"[SYNTHETIC] inserted {len(all_events):,} events across {n_sessions:,} sessions for "
          f"{len(customers):,} customers ({intense} with the 'intense' persona); "
          f"cart_abandon_rate assumption = {CART_ABANDON_RATE}.")
    return len(all_events)


def run_live(db, sessions_per_min=20, n_customers=1500, stop_event=None, log=print):
    """Stream sessions in real time. `stop_event` (threading.Event) lets the
    API start/stop this from the admin page; from the CLI, Ctrl+C stops it."""
    catalog = Catalog(db)
    customers = load_active_customers(db, n_customers)
    interval = 60.0 / max(1, sessions_per_min)
    log(f"[SYNTHETIC][LIVE] streaming ~{sessions_per_min} sessions/min.")
    try:
        while stop_event is None or not stop_event.is_set():
            customer = random.choice(customers)
            events = build_session_events(customer, catalog, datetime.now(timezone.utc))
            # Spread the session's events over real time so Change Streams see them arrive.
            for ev in events:
                ev["timestamp"] = datetime.now(timezone.utc)
                db[COLL_EVENTS].insert_one(ev)
                if stop_event is not None and stop_event.wait(min(2.0, interval / max(1, len(events)))):
                    return
                if stop_event is None:
                    time.sleep(min(2.0, interval / max(1, len(events))))
    except KeyboardInterrupt:
        log("\nStopped live stream.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["batch", "live"], default="batch")
    parser.add_argument("--n-customers", type=int, default=1500)
    parser.add_argument("--n-sessions", type=int, default=6000)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--sessions-per-min", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    db = get_db()
    if args.mode == "batch":
        run_batch(db, args.n_customers, args.n_sessions, args.days, args.seed)
    else:
        run_live(db, args.sessions_per_min, args.n_customers)


if __name__ == "__main__":
    main()
