# Real-Time Retail Intelligence Platform: **Kartiq** store

**CLA-2 · MongoDB Application Development · 21CSE562T SQL and NoSQL for Data Science**

**Kartiq** ("cart" + "IQ"; tagline *Smart shopping, live.*) is a full-stack online store built around MongoDB. Shoppers sign up, search 32,951 real products, read real reviews, fill a cart, pay (simulated) and track their order live. Behind the store, three MongoDB aggregation pipelines feed three lightweight ML models:

- **segments** (K-Means), which decide the shopper's offer;
- **recommendations** (collaborative filtering);
- **behavioural risk** (Isolation Forest), which can hold an order for review.

MongoDB Change Streams push every change to the browser over WebSockets. The home page opens on a live **3-D taste map** of the store's aisles, drawn from the recommendation model, and prices are shown in **rupees**.

| Layer | Technology |
|---|---|
| Front end | React 18 + React Router (Vite), hand-written CSS design system, Lucide icons, Plus Jakarta Sans, a `<canvas>` 3-D taste map (no 3-D library) |
| Back end | FastAPI (Python), JWT auth, WebSockets |
| Database | MongoDB 7, single-node replica set (needed for transactions and Change Streams) |
| ML | pandas, scikit-learn (K-Means, Isolation Forest), cosine-similarity collaborative filtering |

```
           React store (search · cart · checkout · orders · operations)
                    │  REST /api/*                 ▲  WebSocket /ws
                    ▼                              │
        FastAPI ── transactions ──► MongoDB ── Change Stream ──► push worker
           │                         │  ▲
           │ scoped re-runs          │  │ write-back (segment, risk, similarity)
           ▼                         ▼  │
   Pipelines A/B/C (aggregation) ──► rfm_features · category_affinity · rolling_behavioral_metrics
                                     ──► Module 1 K-Means · Module 2 CF · Module 3 Isolation Forest
```

## What it does

**For shoppers** (`/`, `/search`, `/product/:id`, `/cart`, `/checkout`, `/orders`, `/account`, `/how-it-works`):
- **The taste map (home page):** a turning globe of the store's 73 aisles. Dots are categories sized by real buyers; lines are the collaborative-filtering model's category similarities (`GET /api/taste-graph`). Every few seconds a pulse ripples out from the shopper's own aisles to the most similar ones, which is how "Recommended for you" is chosen. Drag it, hover for counts, tap an aisle to explore it.
- **How Kartiq works:** a scroll story with a pinned, animated picture for each step (events → Change Streams → pipelines and models → live updates).
- **Accounts:** sign up and log in. The customer profile and the login account are created in one transaction.
- **Search:** `$text` search plus filter counts, all from one `$facet` aggregation. If the stemmed text search finds nothing, it falls back to a substring match.
- **Product pages:** real Olist ratings and reviews, plus "customers who bought this also bought" (co-purchases across the same customers' orders).
- **Prices in rupees:** the catalogue is in Brazilian reais (the real data); the store shows and charges rupees at one fixed rate, ₹17.80 per R$1, rounded to the whole rupee. Totals use Indian digit grouping and a dot before paise (₹1,23,456.78, ₹12.95). Orders store the rupees charged and the same amounts in reais, so the analytics are unchanged (`backend/app/services/money.py`).
- **Marketplace-style price block:** a big price with a small raised ₹, then "M.R.P: ~~₹1,780~~ (60% off)", the shopper's offer line, the **plus** membership badge, and "FREE delivery **Mon, 16 Nov**". Every number comes from real data:
  - **M.R.P.** is the highest price the product actually sold for in Olist. It is shown only when today's price is 5–60% below it; bigger gaps are one-off outliers.
  - **The delivery date** is today plus the product's **median real delivery time**, computed with MongoDB 7's `$median` accumulator (`data/enrich_products.py`).
- **Free delivery:** delivery is FREE on orders of ₹2,500 or more, and always for **Kartiq Plus** members (the High-Value Loyal segment). The cart shows a progress bar with a truck riding on it ("Add ₹X more for FREE delivery") and the savings against M.R.P.
- **Feedback you can see:** "Add to cart" flies a +1 into the cart icon, the order tracker's line grows as each status arrives, and a placed order gets a confetti burst. All motion switches off when the system asks for reduced motion.
- **Today's deals:** well-rated products priced 15–60% below the highest price they really sold for.
- **Personal offers:** each offer follows the shopper's K-Means segment.
- **Recommendations:** "Recommended for you" uses the collaborative-filtering model. A new user with no purchases gets recommendations from what they browse.
- **Checkout:** one multi-document ACID transaction covers the order, emptying the cart, sales counters, events, customer counters and the notification. Payment is simulated; there is a test card that always declines.
- **Live order tracking:** a simulated fulfilment worker moves orders processing → shipped → delivered. Each status update reaches the browser through a Change Stream and a WebSocket, with a notification.
- **Live re-segmentation:** when an order ships, the customer is re-scored (Pipelines A and B for that customer, then K-Means with the saved model), so their offer updates in real time.
- **Reviews:** a buyer can review a delivered product. The review insert and the product's running average are updated in one transaction.

**For the store admin** (`/admin`, `/admin/customers/:id`):
- **Held orders:** orders from customers rated HIGH risk wait in a review queue, with Approve and Reject.
- **Risk alerts:** an alert appears the moment the Change Stream sees 3+ abandoned carts in 30 min, or 2+ declined payments in 10 min, and the live Isolation Forest score is HIGH.
- **Live activity:** a feed of app and synthetic events, and a switch to start or stop simulated traffic.
- **Analytics:** segment and risk distributions, and a button that re-runs the whole analytics chain with its metrics.
- **Customer 360:** RFM values, segment, recommendations, risk features, and the `$setWindowFields` rolling-activity chart.

## Data: what is real and what is not

| Data | Source | Label in MongoDB |
|---|---|---|
| Customers, orders, products, reviews, sellers | **Real.** Olist Brazilian E-Commerce (Kaggle `olistbr/brazilian-ecommerce`), 2016–2018 | `source: "olist"` |
| Browsing / cart / purchase events | **Synthetic.** `simulator/event_simulator.py`, with documented assumptions | `metadata.is_synthetic: true`, `metadata.source: "simulator"` |
| Accounts, carts, orders, reviews and events created in the app | People using this store | `source: "app"` / `metadata.source: "app"` |
| Test fixture | `data/generate_sample_seed.py`, only ever in `retail_intel_test` | `source: "fixture"` |

Olist publishes no product names or photos. Display names are derived from real attributes, e.g. `Bed Bath Table #99A478` is the category plus the start of the product id, and images are category icons. Price, rating, review count, sales count, seller city and dimensions are all real. Payments and fulfilment are simulated, and the UI says so.

## Run it

**On any computer (Windows, macOS or Linux): follow [`START_HERE.md`](START_HERE.md).** Two scripts do everything after MongoDB is running as a replica set:
- `scripts/setup_windows.bat` or `scripts/setup_mac_linux.sh` set up the environment and packages, check MongoDB (and initiate the replica set if needed), load the data, and train the models;
- `scripts/start_app_windows.bat` or `scripts/start_app.sh` start the store.

`scripts/setup_kartiq.py` is the cross-platform setup those scripts call. The manual steps below do the same.

You need Python 3.11+ and MongoDB 7.0+ running as a replica set; Node 18+ only if you change the front end. On this Mac it is already set up as `rs0`.

```bash
brew services start mongodb-community@7.0          # first time only: see "Replica set" below
cd retail-intelligence-platform
python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

Load the data and train the models (one time, about 2 minutes). The Olist CSVs are in `data/raw/` (or download them from Kaggle `olistbr/brazilian-ecommerce`).

```bash
venv/bin/python data/load_olist_data.py --raw-dir data/raw      # also sets delivery_days with $median
venv/bin/python schema/create_indexes.py
venv/bin/python simulator/event_simulator.py --mode batch --n-customers 1500 --n-sessions 6000 --seed 42
venv/bin/python ml/run_all.py
```

Build the front end and start the app on one port:

```bash
(cd frontend && npm install && npm run build)
./scripts/start_app.sh                          # http://localhost:8100   (API docs: /docs)
```

For front-end development with hot reload, also run `cd frontend && npm run dev` (port 5190; it proxies `/api` and `/ws` to 8100).

**Demo accounts.** These are created on start-up by `backend/app/seed.py` and are test values only; override them with `ADMIN_PASSWORD` / `DEMO_PASSWORD`.

| Account | Email | Password |
|---|---|---|
| Admin (Operations area) | `admin@retail-intel.test` | `Admin#2026demo` |
| Loyal shopper (a real Olist repeat customer) | `loyal@retail-intel.test` | `Shopper#2026demo` |
| Big spender | `bigspender@retail-intel.test` | `Shopper#2026demo` |
| At-risk customer | `atrisk@retail-intel.test` | `Shopper#2026demo` |

**A 3-minute demo:**
1. Open the home page and watch the taste map: tap an aisle to see where its shoppers go next. Then open **How Kartiq works** and scroll.
2. Sign up. The WELCOME10 offer appears. Open **Today's deals** to see real M.R.P. discounts and delivery dates.
3. Search "garden tools", open a product, add 2 to the cart, and check out with card `4242 4242 4242 4242`.
4. Watch the order page move to *Shipped*, then *Delivered*, by itself (20-second steps). A "new perk" notification arrives when you are re-segmented.
5. Try card `4000 0000 0000 0002` to see a declined payment that leaves the cart intact.
6. Log in as admin and open **Operations**. Start simulated traffic to see the live feed.
7. As a shopper, open checkout and click *Back to cart* three times with items in the cart. The risk alert appears live in Operations, and that shopper's next order lands in the review queue.

**Replica set (one-time).** Add the following to `/opt/homebrew/etc/mongod.conf` (Intel Macs: `/usr/local/etc/mongod.conf`), then restart MongoDB and run `mongosh --eval "rs.initiate()"`. Atlas clusters are replica sets already.

```yaml
replication:
  replSetName: rs0
```

## Tests

```bash
venv/bin/python -m pytest          # 27 tests, ~9 s, uses the throw-away database retail_intel_test
```

- **`tests/test_pipelines_ml.py`** runs Pipelines A/B/C and Modules 1–3 against real MongoDB. That covers `$setWindowFields`, `$merge` and `$lookup`, and checks the window outputs against a hand computation.
- **`backend/tests/test_api.py`** covers:
  - sign-up and login;
  - search, facets and the substring fallback, with price filters and buckets in rupees;
  - the checkout transaction: commit, the decline path, validation, and cancel restoring counters;
  - the held-order and approve flow, and admin-only access;
  - the pricing rules: rupee conversion and ₹1,23,456.78 formatting, M.R.P. from the real highest price (outliers ignored), free delivery over ₹2,500 or for Plus members, deals showing only real discounts, and orders storing rupees charged plus the same amounts in reais;
  - the taste-map endpoint (only real categories, similarity weights scaled to at most 1);
  - the Change Stream handler, the abandon threshold, the fulfilment step, and WebSocket authentication.

## Results (full Olist data, simulator seed 42)

| | Result |
|---|---|
| Customers (real people) | 96,096; 2,997 placed more than one order (up to 17), and 2,861 have 2+ completed orders |
| K-Means | k = 4 by silhouette (0.369; k=5: 0.350, k=6: 0.342) |
| Segments | Bargain Browser 36,314 · Big Spender 27,972 · At-Risk 27,252 · High-Value Loyal 2,861 |
| Recommendations, HitRate@3 / @5 on held-out customers | CF + popularity blend **0.345 / 0.472** vs CF alone 0.245 / 0.362 vs popularity 0.290 / 0.456 |
| Isolation Forest | 1,464 simulated customers scored; catches 17 of 19 (89%) of the simulator's known "intense" shoppers as HIGH, 95% as HIGH or MEDIUM |
| Full analytics chain (`ml/run_all.py`) | about 20 s |

These numbers are from the first full run. Re-running analytics from the admin page also includes new app and simulated activity, so segment sizes shift slightly over time.

The reasoning behind each choice is in `notebooks/ml_analysis.ipynb` (executed, with plots) and `docs/report.md`.

## Project layout

```
config.py                    MongoDB connection + collection names (env: MONGO_URI, MONGO_DB)
schema/schema_design.md      document structures, embed-vs-reference decisions, indexes
schema/create_indexes.py     every index, incl. $text and a TTL index
data/load_olist_data.py      REAL data loader (one customer per real person)
data/enrich_products.py      delivery_days per product = $median of real delivery times
data/generate_sample_seed.py placeholder fixture for tests only
simulator/event_simulator.py SYNTHETIC clickstream (batch + live)
pipelines/pipeline_a_rfm.py               $group + $lookup + $merge
pipelines/pipeline_b_affinity.py          $unwind + $group + $merge
pipelines/pipeline_c_rolling_metrics.py   two $setWindowFields stages + $merge
ml/module1_kmeans.py · module2_collaborative_filtering.py · module3_isolation_forest.py · run_all.py
backend/app/                 FastAPI: routers/ (auth, catalog, shopping, admin, system), services/ (catalog,
                             cart, checkout, money, personalization, intelligence, realtime, fulfillment), seed.py
frontend/src/                React app: pages/ (incl. HowItWorks), components.jsx, state.jsx (auth + WebSocket),
                             layout.jsx, globe.jsx (3-D taste map on canvas), motion.js (fly-to-cart, confetti, reveals)
notebooks/ml_analysis.ipynb  EDA, k selection, CF evaluation, anomaly evaluation
docs/report.md               the written report
tests/, backend/tests/       pytest suites
scripts/                     setup_kartiq.py (+ setup_windows.bat / setup_mac_linux.sh): one-time setup;
                             start_app.sh / start_app_windows.bat: start the API + built front end on :8100
START_HERE.md                step-by-step guide for running it on another computer
```
