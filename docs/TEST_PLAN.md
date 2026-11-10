# Kartiq: Test Plan & Demo Script

**Project:** Kartiq, a real-time retail intelligence platform on MongoDB
**Course:** 21CSE562T SQL and NoSQL for Data Science, CLA-2 (MongoDB Application Development)
**Stack:** MongoDB 9.0 (replica set `rs0`) · FastAPI (Python) · React 18 · pandas / scikit-learn
**Data:** real Olist Brazilian e-commerce dataset (99,441 orders) + labelled synthetic shopping events

---

## 1. Purpose and scope

This plan proves four things, in the order an examiner usually asks for them:

1. **CRUD works** on every main collection (users, customers, carts, orders, reviews).
2. **MongoDB-specific features work**: aggregation pipelines, `$setWindowFields`, `$facet` search, text indexes, TTL indexes, multi-document **transactions**, and **Change Streams**.
3. **The "intelligence" works**: K-Means segments set offers, collaborative filtering sets recommendations, and Isolation Forest holds risky orders.
4. **It is safe and correct**: roles, validation, declined payments, and the automated test suite.

Out of scope: real payments (all payments are simulated), real shipping (fulfilment is simulated every 20 s), and load or performance testing.

---

## 2. Test environment

| Item | Value |
|---|---|
| Machine | Windows laptop, PowerShell 5.1 |
| Python | 3.11.9 (project `venv`) |
| MongoDB | Community Server **9.0.8**, Windows service `MongoDB`, single-node replica set `rs0` |
| Database | `retail_intel` (tests use a separate `retail_intel_test`) |
| App URL | http://localhost:8100 · API docs: http://localhost:8100/docs |
| GUI | MongoDB Compass → `mongodb://localhost:27017/?directConnection=true` |
| Project folder | `C:\Users\THE GOD\Documents\Github\retail-intelligence-platform` |

### Test accounts (created by the setup)

| Role | Email | Password | Segment |
|---|---|---|---|
| Admin | `admin@retail-intel.test` | `Admin#2026demo` | n/a |
| Shopper "Lara" | `loyal@retail-intel.test` | `Shopper#2026demo` | High-Value Loyal (Kartiq Plus) |
| Shopper "Bruno" | `bigspender@retail-intel.test` | `Shopper#2026demo` | Big Spender |
| Shopper "Alice" | `atrisk@retail-intel.test` | `Shopper#2026demo` | At-Risk |

### Test cards (simulated)

| Card number | Result |
|---|---|
| `4242 4242 4242 4242` (any future expiry, any CVV) | Approved |
| `4000 0000 0000 0002` | Always declined |

### Segment offers (coupon codes)

| Segment | Code | Offer |
|---|---|---|
| High-Value Loyal | `PLUS10` | 10% off over ₹1,500 + always free delivery |
| Big Spender | `PREMIUM10` | 10% off over ₹3,000 |
| At-Risk | `COMEBACK15` | 15% off |
| Bargain Browser | `DEALS10` | 10% off over ₹999 |
| New Customer (fresh sign-up) | `WELCOME10` | 10% off first order |

---

## 3. Pre-demo checklist (run 10 minutes before)

Open **two** PowerShell windows.

**Window 1: start the app (leave it open):**

```powershell
cd "C:\Users\THE GOD\Documents\Github\retail-intelligence-platform"
.\scripts\start_app_windows.bat
```

**Window 2: checks:**

```powershell
cd "C:\Users\THE GOD\Documents\Github\retail-intelligence-platform"
Get-Service MongoDB                                   # Running
Invoke-RestMethod "http://localhost:8100/api/health"  # ok / rs0 / True
.\venv\Scripts\python -m pytest -p no:warnings        # 27 passed
```

- [ ] MongoDB service is **Running**
- [ ] Health shows `status ok`, `replica_set rs0`, `change_stream True`
- [ ] **27 passed**
- [ ] Browser tabs open: http://localhost:8100 · http://localhost:8100/docs
- [ ] Compass connected, `retail_intel` database open
- [ ] Laptop charger in, notifications off, browser zoom ~110%

---

## 4. Test cases

Status column: mark ✅ pass / ❌ fail during your run.

### 4.1 Setup and infrastructure

| ID | Test | Steps | Expected result | MongoDB feature | Status |
|---|---|---|---|---|---|
| ENV-01 | MongoDB service | `Get-Service MongoDB` | `Running` | n/a | |
| ENV-02 | Replica set | `.\venv\Scripts\python scripts\setup_kartiq.py --check` | `OK MongoDB 9.0.8, replica set 'rs0'` and `OK transactions and Change Streams work` | Replica set | |
| ENV-03 | Data loaded | Compass → `retail_intel` → collection list | orders ≈ 99,441 · customers ≈ 96,096 · products 32,951 · reviews 102,230 · events ≈ 25,000+ | Bulk insert | |
| ENV-04 | Indexes | Compass → `products` → **Indexes** tab | Includes `txt_product_search` (text) and `uniq_product_id` (unique) | Text + unique index | |
| ENV-05 | TTL index | Compass → `notifications` → Indexes | `ttl_notifications_30d` with TTL 2592000 s | TTL index | |
| ENV-06 | Health API | `Invoke-RestMethod http://localhost:8100/api/health` | `ok`, `rs0`, `True` | Change Stream open | |

### 4.2 Authentication (Create / Read on `users`, `customers`)

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| AUTH-01 | Sign up | Sign up with a new email, name, password ≥ 8 chars | Logged in; welcome notification appears in the bell | |
| AUTH-02 | Duplicate email | Sign up again with the same email | "An account with this email already exists. Try logging in." (unique index on `users.email`) | |
| AUTH-03 | Weak input | Sign up with a 3-char password or a bad email | Validation error, nothing created | |
| AUTH-04 | Log in | Log in as Lara | Home page greets Lara, shows the Plus badge | |
| AUTH-05 | Wrong password | Log in with a wrong password | "Email or password is incorrect." | |
| AUTH-06 | Sign-up is atomic | After AUTH-01, Compass → `users` and `customers` filter by the new email / `source: "app"` | One user **and** one customer document, linked by `customer_id` (created in one transaction) | |

### 4.3 Catalog and search (Read on `products`, `reviews`)

| ID | Test | Steps | Expected result | MongoDB feature | Status |
|---|---|---|---|---|---|
| CAT-01 | Text search | Search `watch` | Watch products, ranked by relevance | `$text` + text score | |
| CAT-02 | Facets | On search results, look at the left filters | Category counts, price buckets (₹), rating buckets, all in one request | `$facet` + `$bucket` | |
| CAT-03 | Filter + sort | Apply a price range and sort by price | List updates; prices in whole rupees | Indexed range query | |
| CAT-04 | Product page | Open a product | Price, M.R.P. struck through + % off (only if real), delivery date, reviews | `$median` delivery | |
| CAT-05 | Today's deals | Open **Today's deals** | Only products 15–60% below their highest real price | `$addFields` + `$match` | |
| CAT-06 | "Also bought" | Product page, scroll down | Products bought by the same customers | `$unwind` + `$group` + `$lookup` | |

### 4.4 Cart (full CRUD on `carts`)

| ID | Operation | Steps | Expected result | Status |
|---|---|---|---|---|
| CART-01 | **Create** | Add a product to cart | "+1" flies into the cart icon; cart count = 1 | |
| CART-02 | **Read** | Open the cart | Item, price, savings vs M.R.P., free-delivery progress bar | |
| CART-03 | **Update** | Change quantity to 3 | Line total and cart total update | |
| CART-04 | Quantity limit | Try to set quantity above 20 | Not allowed: maximum 20 per line (validation) | |
| CART-05 | **Delete** | Remove the item | Cart empty | |
| CART-06 | Verify in Compass | `carts` → filter `{ _id: "<customer id>" }` | One document per customer, items embedded | |

### 4.5 Checkout (transaction on `orders`, `carts`, `products`, `events`, `notifications`)

| ID | Test | Steps | Expected result | MongoDB feature | Status |
|---|---|---|---|---|---|
| CHK-01 | Coupon auto-applied | As Lara, go to checkout with ≥ ₹1,500 in cart | `PLUS10` applied, delivery free | Segment → offer | |
| CHK-02 | Declined payment | Pay with `4000 0000 0000 0002` | "Your payment was declined. Try another card or payment method."; **no order created**, cart still full | Transaction never opens | |
| CHK-03 | Successful order | Pay with `4242 4242 4242 4242`, `12/29`, `123` | Confetti; order page opens with status **Processing** | **Multi-document transaction** | |
| CHK-04 | Everything committed | Compass: `orders` filter `{ source: "app" }`, sort `{ order_purchase_timestamp: -1 }` | New order with embedded `line_items`, `payment` (card last-4 only), `charged` in INR; cart is now empty | Embedded documents | |
| CHK-05 | Boleto / UPI-style | Checkout with **Boleto** | Order created without card details | Variable schema | |

### 4.6 Live order tracking (Update on `orders`, Change Streams)

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| LIVE-01 | Status moves by itself | Stay on the order page after CHK-03 | Processing → **Shipped** (~20 s) → **Delivered** (~40 s), with no page refresh | |
| LIVE-02 | Notification | Watch the bell icon | "Your order is on its way", then "Delivered" pop in live | |
| LIVE-03 | History | Compass → that order → `status_history` | One entry per status with timestamps | |
| LIVE-04 | Live re-segmentation | After a new sign-up's orders ship, check Account page / Compass `customers.segment` | Segment updated with `method: "kmeans-live"` | |

### 4.7 Cancel order (Update + transaction)

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| CAN-01 | Cancel | Place an order, immediately click **Cancel order** | Status **Canceled**; product sales counters restored | |
| CAN-02 | Cannot cancel shipped | Try to cancel a shipped/delivered order | Cancel button gone; the API refuses: "This order is already shipped and can't be cancelled." | |

### 4.8 Reviews (Create on `reviews` + update on `products`)

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| REV-01 | Write a review | On a product from a shipped/delivered order, give 5 stars + title | Review appears at the top; product rating count +1 | |
| REV-02 | Review before shipping | Try to review a product whose order is still processing | "You can review products you've bought once they've shipped." | |
| REV-03 | Duplicate review | Review the same product again | "You've already reviewed this product." | |
| REV-04 | Verify | Compass → `reviews` filter `{ source: "app" }` | New review document referencing `product_id` | |

### 4.9 Personalisation (ML outputs used live)

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| ML-01 | Segment offer | Log in as Lara, Bruno, Alice in turn | Each sees a different offer (PLUS10 / PREMIUM10 / COMEBACK15) | |
| ML-02 | Recommendations | Home → "Recommended for you" | Categories with a reason, e.g. "because you shop in Bed Bath Table" | |
| ML-03 | Taste map | Home page globe | Dots = aisles, lines = similarities; pulse starts from your aisles; drag works | |
| ML-04 | Segments in data | Compass → `customers` filter `{ "segment.label": "High-Value Loyal" }` | ≈ 2,861 documents | |

### 4.10 Risk detection flow (Change Stream + Isolation Forest)

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| RISK-01 | Trigger | As a shopper with items in cart: go to Checkout → **Back to cart**, 3 times | 3 `cart_abandon` events recorded | |
| RISK-02 | Alert raised | Log in as admin → Operations | New **HIGH** alert: "3+ abandoned carts in 30 min" | |
| RISK-03 | Order held | As that shopper, place an order | Status **Under review** (held) | |
| RISK-04 | Admin approves | Admin → Held orders → **Approve** | Order moves to Processing, then ships live | |
| RISK-05 | Resolve | Admin → alert → **Resolve** | Alert closed | |

### 4.11 Admin area

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| ADM-01 | Overview | Admin → Operations | Customers, 24 h revenue, held orders, open alerts, segment & risk charts | |
| ADM-02 | Live traffic | Press **Start simulated traffic** | Live activity feed fills (~30 sessions/min) | |
| ADM-03 | Customer 360 | Open any customer | RFM values, segment, risk score, rolling metrics, orders | |
| ADM-04 | Re-run analytics | Press **Re-run analytics** | Pipelines A, B, C and Modules 1–3 run (~35 s); new run in history | |

### 4.12 Security

| ID | Test | Steps | Expected result | Status |
|---|---|---|---|---|
| SEC-01 | Shopper blocked from admin | As a shopper, open http://localhost:8100/admin (or call `/api/admin/overview`) | 403 "Admins only" | |
| SEC-02 | No token | Call `/api/cart` without logging in | 401 | |
| SEC-03 | Passwords hashed | Compass → `users` | `password_hash` starts with `scrypt$`, no plain text | |
| SEC-04 | Cards never stored | Compass → app order → `payment` | Only brand + last 4 digits | |

### 4.13 Automated tests

| ID | Test | Command | Expected |
|---|---|---|---|
| AUTO-01 | Full suite | `.\venv\Scripts\python -m pytest -p no:warnings` | **27 passed** (~9 s) |

What the 27 tests cover: Pipeline A frequency = completed orders; Pipeline B spend = line-item sum; every Pipeline C window value matches a hand calculation; K-Means / CF / Isolation Forest save and score; sign-up, login, roles; search facets and rupee prices; checkout transaction commits everything; declined payment creates nothing; cancel restores counters; held-order approval; Change Stream handlers; WebSocket auth.

---

## 5. Demo script (about 10 minutes)

| Time | Show | Say (one line) |
|---|---|---|
| 0:00 | Slide deck: problem + architecture | "Stores have data but act on it too late. Kartiq acts while the customer is shopping." |
| 1:00 | Compass: collections + one order document | "Real Olist data: 99k orders. Line items and payment are embedded; events are separate." |
| 2:00 | Home page as guest: taste map | "Each dot is an aisle; lines come from our collaborative-filtering model." |
| 2:45 | Search `watch` | "One `$facet` aggregation returns results and every filter count in a single round trip." |
| 3:30 | Log in as Lara → add to cart → change qty → remove → add again | "That's full CRUD on the cart." |
| 4:30 | Checkout with **declined** card | "Payment failed, so no order exists and the cart is untouched." |
| 5:00 | Checkout with **4242** card | "Now one transaction writes the order, empties the cart, updates stock counters and logs events." |
| 5:30 | Stay on order page | "No refresh: a Change Stream pushes Shipped, then Delivered, over a WebSocket." |
| 6:30 | Compass: refresh `orders` filter `{source:"app"}` | "Here's the order we just placed, with status history." |
| 7:00 | Back to cart ×3, then admin → Operations | "Three abandons in 30 min: the Change Stream re-scores the customer with Isolation Forest → HIGH alert." |
| 8:00 | Place order as that user → admin approves | "A HIGH-risk customer's order is held until an admin approves it." |
| 8:45 | Start simulated traffic; open Customer 360 | "Segments, RFM and rolling window metrics, all computed by MongoDB pipelines." |
| 9:30 | `/docs` and the pytest run | "Every API is documented, and 27 automated tests pass." |
| 10:00 | Closing slide | Questions |

**Backup plan:** if live tracking is slow, refresh the order page. If anything breaks, show the screenshots in the slide deck.

---

## 6. Handy Compass queries

Paste into Compass's **Filter** bar (Documents tab).

| Collection | Filter | Shows |
|---|---|---|
| `orders` | `{ source: "app" }` + Sort `{ order_purchase_timestamp: -1 }` | Orders placed in the demo |
| `orders` | `{ order_status: "under_review" }` | Held orders |
| `customers` | `{ "segment.label": "At-Risk" }` | One K-Means segment |
| `customers` | `{ "anomaly.risk_label": "HIGH" }` | Risky customers |
| `events` | `{ "metadata.source": "app" }` | Events from real clicks |
| `events` | `{ "metadata.is_synthetic": true }` | Simulated events |
| `alerts` | `{ status: "open" }` | Open risk alerts |
| `rolling_behavioral_metrics` | `{}` | `$setWindowFields` output |

**Aggregation to run live** (Compass → `customers` → Aggregations → paste as text):

```json
[
  { "$group": { "_id": "$segment.label", "customers": { "$sum": 1 } } },
  { "$sort": { "customers": -1 } }
]
```

Expected: Bargain Browser ≈ 36k, Big Spender ≈ 28k, At-Risk ≈ 27k, High-Value Loyal ≈ 2.9k.

---

## 7. Troubleshooting during the demo

| Problem | Fix |
|---|---|
| Page won't load | Window 1 closed → run `.\scripts\start_app_windows.bat` again |
| "Could not reach MongoDB" | Admin PowerShell: `net start MongoDB` |
| Order not moving | Wait 20 s per step; refresh the page |
| No alert after 3 abandons | Cart must have items each time you leave checkout; all 3 within 30 min |
| `DLL load failed … Application Control policy` | `.\venv\Scripts\python -m pip install --force-reinstall --no-cache-dir numpy pandas scikit-learn` |
| Port 8100 busy | `$env:PORT=8200; .\scripts\start_app_windows.bat` → open http://localhost:8200 |

---

## 8. Results log

| Date | Check | Result |
|---|---|---|
| 10 Nov 2026 | Setup on Windows (Python 3.11.9, MongoDB 9.0.8) | ✅ Kartiq ready in 2.6 min |
| 10 Nov 2026 | Health endpoint | ✅ ok / rs0 / change_stream True |
| 10 Nov 2026 | Automated tests | ✅ 27 passed in 8.62 s |
| 10 Nov 2026 | Browser: login, add to cart, checkout, live tracking, admin traffic, analytics run | ✅ |
| | Full manual run of section 4 | |
