# Showing MongoDB Live: Data-Change Demo Guide

The goal: every time you click something in Kartiq, the examiner **sees the data change in MongoDB**, live in a terminal and then in Compass.

---

## 1. Screen layout (set up before the demo)

Open three things and arrange them side by side:

| Where | What | How |
|---|---|---|
| Left half | **Browser**: http://localhost:8100 | Store running from window 1 (`.\scripts\start_app_windows.bat`) |
| Right half, top | **MongoDB Compass**: `mongodb://localhost:27017/?directConnection=true` → database `retail_intel` | |
| Right half, bottom | **Change monitor**: a PowerShell window running `watch_changes.py` | Command below |

**Start the change monitor** in a new PowerShell window:

```powershell
cd "C:\Users\THE GOD\Documents\Github\retail-intelligence-platform"
.\venv\Scripts\python scripts\watch_changes.py
```

It prints one coloured line for every insert / update / delete, the moment it happens:

- **INSERT** green · **UPDATE** yellow · **DELETE** red
- Changes made inside one **transaction** are grouped in a purple box: `┌─ TRANSACTION … (all of these commit together) ─`
- Synthetic simulator events are hidden. Add `--all` to show them, or `--only orders,carts` to watch just some collections.

> **What to say:** "This window is a MongoDB **Change Stream**: the database itself pushes every change to us. The app uses the same feature to update the browser live."

**Useful ids:**

| Who | Customer id |
|---|---|
| Lara (`loyal@retail-intel.test`) | `c_8d50f5eadf50201ccdcedfb9e2ac8455` |
| A new sign-up | shown in the monitor as `NEW CUSTOMER c_app_…` |

---

## 2. Compass tour (2 minutes, before you click anything)

| Step | In Compass | Point at / say |
|---|---|---|
| 1 | Click `retail_intel` | 14 collections. Document counts: orders 99,441 · customers 96,096 · products 32,951 · reviews 102,230 |
| 2 | `orders` → Documents → open one document | `line_items` (array) and `payment` (object) are **embedded** inside the order: one read gets the whole order |
| 3 | `orders` → **Schema** tab → *Analyze* | MongoDB shows each field's type and how often it appears |
| 4 | `events` → **Schema** tab | `metadata` has different fields per event type (`query`, `reason`, `order_id`…). Flexible schema, no ALTER TABLE |
| 5 | `products` → **Indexes** tab | `txt_product_search` = **text index** (powers search), `uniq_product_id` = unique |
| 6 | `notifications` → **Indexes** | `ttl_notifications_30d` = **TTL index**: MongoDB deletes old notifications by itself |
| 7 | `orders` → Filter `{ customer_id: "c_8d50f5eadf50201ccdcedfb9e2ac8455" }` → **Explain** | Plan shows **IXSCAN** on `idx_customer_recency`: the index is used, no full scan |
| 8 | `customers` → **Aggregations** → *Text* view → paste the pipeline below → Run | Segment sizes, computed by MongoDB |

```json
[
  { "$group": { "_id": "$segment.label", "customers": { "$sum": 1 } } },
  { "$sort": { "customers": -1 } }
]
```

---

## 3. Click → watch → verify (the main part)

For each action: do it in the **browser**, point at the **monitor**, then show the document in **Compass** (press the ⟳ refresh button in Compass after each action).

### 3.1 Sign up (CREATE + transaction)

| | |
|---|---|
| **Do** | Sign up with a new email |
| **Monitor shows** | `┌─ TRANSACTION` → `INSERT customers  NEW CUSTOMER c_app_…` + `INSERT users  NEW LOGIN you@…  password stored as scrypt$…` → `INSERT notifications "Welcome, …!"` |
| **Compass** | `users` → Filter `{ email: "you@example.com" }` → `password_hash` starts with `scrypt$` (never plain text). `customer_id` links to the `customers` document |
| **Say** | "The customer profile and the login are created in **one transaction**: both or neither." |

### 3.2 Add to cart (CREATE / UPDATE)

| | |
|---|---|
| **Do** | Log in as Lara, add a product |
| **Monitor shows** | `UPDATE carts  cart c_8d50…  1 line(s): <product>×1` and `INSERT events  add_to_cart … source=app` |
| **Compass** | `carts` → Filter `{ _id: "c_8d50f5eadf50201ccdcedfb9e2ac8455" }` → `items` array is embedded in the cart |
| **Say** | "The cart's `_id` *is* the customer id, so it's found by primary key with no extra index." |

### 3.3 Change quantity (UPDATE) and remove (DELETE item)

| | |
|---|---|
| **Do** | Cart page: change qty to 3, then remove the item |
| **Monitor shows** | `UPDATE carts … ×3`, then `UPDATE carts … is now EMPTY` |
| **Compass** | Refresh the cart document: `quantity: 3`, then `items: []` |

### 3.4 Declined payment (nothing is written)

| | |
|---|---|
| **Do** | Add an item, checkout with `4000 0000 0000 0002` |
| **Monitor shows** | Only `INSERT events  payment_failed … source=app`. **No orders line, no TRANSACTION box** |
| **Compass** | `orders` → Filter `{ source: "app" }` → no new order. `carts` → items still there |
| **Say** | "A failed payment never opens the transaction, so no half-finished order exists." |

### 3.5 Successful checkout (multi-document ACID transaction) ⭐

| | |
|---|---|
| **Do** | Checkout with `4242 4242 4242 4242`, `12/29`, `123` |
| **Monitor shows** | One purple **TRANSACTION** box with 6 changes in the same second:<br>`INSERT orders  NEW ORDER o_app_…  status=processing  total=₹…`<br>`UPDATE carts  is now EMPTY`<br>`UPDATE products  sales_count=…` (went up by 1)<br>`INSERT events  purchase`<br>`UPDATE customers  order_count=…`<br>`INSERT notifications  "Order placed"` |
| **Compass** | `orders` → Filter `{ source: "app" }` · Sort `{ order_purchase_timestamp: -1 }` → top document. Expand `line_items`, `payment` (only brand + last 4 digits), `charged` (rupees), `status_history` |
| **Say** | "Five collections changed in one transaction. If any step failed, MongoDB would roll back all of them." |

### 3.6 Live order tracking (UPDATE pushed by Change Stream)

| | |
|---|---|
| **Do** | Stay on the order page for ~40 s |
| **Monitor shows** | `UPDATE orders  order_status → shipped`, then `INSERT notifications "Your order is on its way"`, then `UPDATE customers  segment…  method=kmeans-live`, then `order_status → delivered` |
| **Browser** | Status moves by itself, with no refresh |
| **Compass** | Refresh the order → `order_status: "delivered"`, `status_history` has 3 entries with timestamps |
| **Say** | "When the order ships, the customer is re-scored by the saved K-Means model on the spot. If their segment changes, a 'New perk unlocked' notification appears." |

### 3.7 Cancel order (UPDATE in a transaction)

| | |
|---|---|
| **Do** | Place another order and immediately click **Cancel order** |
| **Monitor shows** | `TRANSACTION`: `UPDATE orders  order_status → canceled` + `UPDATE products  sales_count=…` (went back down) |
| **Say** | "We never hard-delete orders: cancelling is a status change, and the stock counter is restored in the same transaction." |

### 3.8 Write a review (CREATE + UPDATE)

| | |
|---|---|
| **Do** | Open a product from an order that has **shipped or delivered** (e.g. the one from 3.5), give 5 stars. Reviews are refused before the order ships |
| **Monitor shows** | `TRANSACTION`: `INSERT reviews  NEW REVIEW 5★` + `UPDATE products  review_count=…` (and `rating_avg` if the average changed) |
| **Compass** | `reviews` → Filter `{ source: "app" }` |

### 3.9 Risk detection (Change Stream → ML → alert) ⭐

| | |
|---|---|
| **Do** | As a shopper with items in the cart: go to Checkout → **Back to cart**, 3 times |
| **Monitor shows** | `INSERT events  cart_abandon` ×3 → `UPDATE customers  anomaly.risk_label=HIGH  anomaly.score=-0.08…  method=isolation-forest-live` → `INSERT alerts  RISK ALERT HIGH … 3+ abandoned carts in 30 min` |
| **Then do** | Place an order as that shopper |
| **Monitor shows** | `NEW ORDER … status=under_review` (held) |
| **Then do** | Log in as admin → Operations → **Approve** |
| **Monitor shows** | `UPDATE orders  order_status → processing` + `"Order approved"` notification |
| **Compass** | `alerts` → `{ status: "open" }` · `customers` → `{ "anomaly.risk_label": "HIGH" }` · `orders` → `{ order_status: "under_review" }` |
| **Say** | "The Change Stream counted 3 abandons, re-ran Pipeline C for just this customer, scored them with the saved Isolation Forest, and wrote the result back. All within a second." |

### 3.10 Admin: re-run analytics and simulated traffic

| | |
|---|---|
| **Do** | Admin → **Re-run analytics** (~35 s) |
| **Compass** | `ml_runs` → Sort `{ _id: -1 }` → newest run with timings and metrics. `rfm_features`, `category_affinity`, `rolling_behavioral_metrics` are rewritten by `$merge` |
| **Do** | Admin → **Start simulated traffic** |
| **Monitor** | Stop it (Ctrl+C) and restart with `--all`: synthetic events stream in (~30 sessions/min). Compass: `events` count keeps rising on refresh |

---

## 4. The same checks in Compass's shell

Compass has a built-in shell: click **`>_MONGOSH`** at the bottom of the Compass window. Paste one line at a time:

```javascript
use retail_intel

// how many orders were placed in the app today
db.orders.countDocuments({ source: "app" })

// the latest app order, only the interesting fields
db.orders.find({ source: "app" }, { order_status: 1, charged: 1, status_history: 1 }).sort({ order_purchase_timestamp: -1 }).limit(1)

// Lara's cart
db.carts.findOne({ _id: "c_8d50f5eadf50201ccdcedfb9e2ac8455" })

// segment sizes (aggregation)
db.customers.aggregate([{ $group: { _id: "$segment.label", n: { $sum: 1 } } }, { $sort: { n: -1 } }])

// text search using the text index
db.products.find({ $text: { $search: "watch" } }, { name: 1, price: 1 }).limit(3)

// proof the index is used (look for IXSCAN / idx_customer_recency)
db.orders.find({ customer_id: "c_8d50f5eadf50201ccdcedfb9e2ac8455" }).explain().queryPlanner.winningPlan

// the TTL index on notifications
db.notifications.getIndexes()

// open risk alerts
db.alerts.find({ status: "open" })
```

---

## 5. One-line answers for the examiner

| Question | Answer |
|---|---|
| How does the browser update without refresh? | A Change Stream on MongoDB tells the back end about every change, and it pushes it over a WebSocket. |
| Why does checkout need a transaction? | It changes 5 collections (orders, carts, products, events, customers) plus a notification. All must succeed or none. |
| Why a replica set on one laptop? | Transactions and Change Streams only work on a replica set. A single-node set is enough. |
| Why is the cart's `_id` the customer id? | One cart per customer, so it's read by primary key with no extra index. |
| Where do deleted things go? | Cart items are removed from the array. Orders are never deleted (status → canceled). Notifications are deleted by a TTL index after 30 days. |
