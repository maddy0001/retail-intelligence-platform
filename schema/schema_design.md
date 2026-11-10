# Schema Design — Real-Time Retail Intelligence Platform

## Optimisation assumptions, stated up front

The store has two different workloads in one database, and each collection is designed for the workload it actually carries:

- **Read-heavy** (`products`, `reviews`, `customers`, `orders`): every page view reads these, and writes happen only at checkout or when an analytics job writes a result back. Here we embed what is read together and index the query patterns.
- **Write-heavy** (`events`): every click, add-to-cart and abandon is an insert, from the app and from the simulator. This collection gets the minimum indexes, because every index slows every insert.

Where a choice trades off differently under the two assumptions, the section says which side it optimises for.

---

## 1. `customers`: one document per real person

```json
{
  "_id": "c_861eff4711a542e4b93843c6dd7febb0",
  "customer_unique_id": "861eff4711a542e4b93843c6dd7febb0",
  "olist_customer_ids": ["06b8999e2fba1a1fbc88172c00ba8bc7"],
  "customer_city": "franca", "customer_state": "SP", "customer_zip_prefix": "14409",
  "first_order_at": "ISODate(2017-05-16)", "last_order_at": "ISODate(2017-05-16)", "order_count": 1,
  "source": "olist",
  "segment": { "label": "Bargain Browser", "cluster_id": 1, "method": "kmeans", "computed_at": "ISODate(...)" },
  "anomaly": { "risk_label": "LOW", "score": 0.0712, "method": "isolation-forest", "flags": [], "computed_at": "ISODate(...)" }
}
```

- **Keyed on the person, not the order.** Olist issues a new `customer_id` for every order (99,441 ids for 99,441 orders); `customer_unique_id` is the real repeat customer. Keying on it is what gives RFM a real Frequency: 2,861 people have 2+ completed orders, up to 16. The original per-order ids are kept in `olist_customer_ids` for traceability. App sign-ups get `_id: "c_app_<random>"` and `source: "app"`.
- **`segment` and `anomaly` are embedded sub-documents.** They are small, always read together with the customer (offers, checkout risk check, Customer 360), and each is written whole by exactly one process: K-Means writes `segment`, Isolation Forest writes `anomaly`. Embedding avoids a `$lookup` on the hottest read path.

## 2. `users`: login accounts (referenced to `customers`)

```json
{ "_id": "ObjectId(...)", "email": "lara@example.test", "name": "Lara", "role": "customer",
  "password_hash": "scrypt$16384$8$1$<salt>$<hash>", "customer_id": "c_app_3f1c…", "created_at": "ISODate(...)", "source": "app" }
```

**Referenced, not embedded.** Credentials are kept away from the customer analytics document, which pipelines and admin screens read often. Only the authentication code touches `users`. Admin accounts have no customer. `email` has a unique index; sign-up inserts the customer and the user in one transaction.

## 3. `orders`: line items and payment embedded

```json
{
  "_id": "o_acce194856392f074dbf9dada14d8d82", "customer_id": "c_576ea0cab426cd8a00fad9a9c90a4494",
  "order_status": "delivered", "order_purchase_timestamp": "ISODate(2018-06-04)",
  "timeline": { "approved_at": "…", "shipped_at": "…", "delivered_at": "…", "estimated_delivery_at": "…" },
  "payment": { "type": "credit_card", "installments": 10, "total_value": 227.68, "methods": ["credit_card"] },
  "line_items": [
    { "product_id": "9451e630…", "category": "baby", "category_pt": "bebes", "seller_id": "d673a59a…",
      "unit_price": 39.5, "freight_value": 48.64, "quantity": 1 }
  ],
  "items_total": 130.4, "freight_total": 97.28, "source": "olist"
}
```

App orders also carry `status_history`, `shipping_address`, `discount`, `total`, `risk_at_checkout`, and a payment block with `simulated: true` plus card brand and last 4 digits only.

**Currency.** Every amount above is in reais, the currency of the Olist data, and that is what Pipelines A and B read. The store charges rupees, so an app order also embeds what the shopper actually paid:

```json
"charged": { "currency": "INR", "inr_per_brl": 17.8, "items": 3836.0, "delivery": 0.0, "discount": 383.6, "total": 3452.4 },
"line_items": [ { "product_id": "…", "unit_price": 53.88, "unit_price_inr": 959.0, "quantity": 4, "…": "…" } ],
"total": 193.96, "payment": { "total_value": 193.96, "amount_charged": 3452.4, "currency": "INR", "…": "…" }
```

The reais fields of an app order are its rupee amounts divided by the rate it was placed at, so app orders and Olist orders share one analytics schema. Older orders without `charged` are converted at the store rate when shown.

- **`line_items` embedded.** A basket is small and bounded, never changes after checkout, and Pipelines A and B read the whole order at once. Embedding is why Pipeline B can `$unwind` instead of `$lookup`ing an `order_items` collection.
- **`payment` embedded.** It is 1-to-1 with the order and never queried on its own.
- **Product and category copied onto the line.** A line keeps the price, category and quantity *at the time of purchase* (a historical fact). The live catalog entry is still referenced by `product_id`.

## 4. `products`: referenced from orders, events, carts and reviews

```json
{
  "_id": "p_99a4788cb24856965c36a24e339b6058", "product_id": "99a4788cb24856965c36a24e339b6058",
  "name": "Bed Bath Table #99A478", "category": "bed_bath_table", "category_label": "Bed Bath Table",
  "category_pt": "cama_mesa_banho", "price": 89.9, "price_range": { "min": 79.9, "max": 99.9 },
  "freight": 15.38, "sales_count": 488, "rating_avg": 3.9, "review_count": 461,
  "seller": { "seller_id": "4a3ca931…", "city": "ibitinga", "state": "SP" },
  "photos_qty": 1, "weight_g": 1000, "dimensions_cm": { "length": 30, "height": 10, "width": 20 },
  "delivery_days": 10, "source": "olist"
}
```

**A separate, referenced collection.** Products are many-to-many with orders, carts, events and reviews, and are updated on their own (sales counter, rating). Embedding a product into every order or event would duplicate the catalog and force rewrites on every catalog change.

`price`, `rating_avg`, `review_count`, `sales_count` and `seller` are **pre-aggregated** from the real order, review and seller files when the data is loaded. This deliberately duplicates some data (a read-heavy optimisation) so a search results page needs no joins. Checkout keeps `sales_count` correct with `$inc` inside the transaction. `name` is derived (category + id prefix) because Olist publishes no names. `delivery_days` is the median number of days from purchase to delivery over the product's real orders. It is computed by one aggregation using MongoDB 7's `$median` accumulator and `$merge`d back (`data/enrich_products.py`). The store's "M.R.P." is `price_range.max`, the highest price the product really sold for. Prices stay in reais here; the API shows them as whole rupees at a fixed rate (`backend/app/services/money.py`), so the catalogue is never rewritten when the store's display currency changes.

## 5. `reviews`: separate, referenced by product

```json
{ "_id": "r_<review>_<order>_<product>", "product_id": "…", "order_id": "…", "customer_id": "c_…",
  "rating": 5, "title": null, "message": "Recebi bem antes do prazo estipulado.", "language": "pt",
  "created_at": "ISODate(...)", "verified_purchase": true, "source": "olist" }
```

**Not embedded in products.** Reviews per product are unbounded (up to hundreds), the product page shows only the latest few, and a 16 MB document limit would eventually bite. Olist reviews are per order, so a review is attached to every product in that order.

## 6. `carts`: one per customer, items embedded

```json
{ "_id": "c_app_3f1c…", "items": [ { "product_id": "…", "quantity": 2, "added_at": "ISODate(...)" } ],
  "created_at": "…", "updated_at": "…" }
```

**`_id` is the customer id.** There is one cart per customer, fetched by primary key, and no extra index is needed. Items are embedded because a cart is small, bounded (at most 20 per line) and always read and written whole. Prices are looked up live, so a cart never shows a stale price.

## 7. `events`: synthetic + app behaviour, a flat write-heavy collection

```json
{ "_id": "e_7f0012ab…", "customer_id": "c_861eff…", "session_id": "s_20f…", "event_type": "add_to_cart",
  "timestamp": "ISODate(...)", "product_id": "…", "category": "watches_gifts",
  "metadata": { "channel": "web", "is_synthetic": true, "source": "simulator", "persona": "normal" } }
```

- **A separate collection referenced by `customer_id`, never embedded in `customers`.** An active customer generates an unbounded number of events (the unbounded-array anti-pattern). A flat collection also lets `$setWindowFields` partition naturally by customer.
- **Variable shape.** `metadata` differs by `event_type` and `source`: a search carries a query, a declined payment a reason, an app purchase an order id. No schema change is needed to add a new event type.
- **Write-optimised indexes:** only `{customer_id, timestamp}` (what Pipeline C sorts and partitions on) and `{timestamp}` (the "last hour" count).

## 8. `notifications` (TTL) and `alerts`

```json
{ "user_id": "65f…", "kind": "order", "title": "Your order is on its way", "body": "…", "link": "/orders/o_app_…",
  "read": false, "created_at": "ISODate(...)" }
{ "customer_id": "c_app_…", "risk_label": "HIGH", "score": -0.0825, "reason": "3+ abandoned carts in 30 min",
  "features": { "...": "..." }, "status": "open", "created_at": "ISODate(...)" }
```

- **`notifications`** has a **TTL index** (`created_at`, 30 days), so MongoDB deletes old notifications itself and no clean-up job is needed. Inserting one is all it takes to reach the user's browser: the Change Stream picks it up and pushes it.
- **`alerts`** is written by the Change Stream worker when a live re-score comes back HIGH. Admins resolve alerts, so they keep a status.

## 9. Derived (written-back) collections

| Collection | Written by | Shape (one document per …) |
|---|---|---|
| `rfm_features` | Pipeline A (`$merge`) | customer: recency_days, frequency, monetary, first/last order, profile |
| `category_affinity` | Pipeline B (`$merge`) | (customer, category): spend, units, orders_touched |
| `rolling_behavioral_metrics` | Pipeline C (`$merge`) | event: 7-day count, gap, average gap over the last 10, purchase share, abandon share |
| `category_similarity` | Module 2 | category: top-15 similar categories + number of buyers |
| `ml_runs` | `ml/run_all.py` | analytics run: steps, timings, metrics, status |

Using `$merge` makes each pipeline's output a real, queryable collection. Every model reads a named aggregation output, never raw orders or events, and re-running a pipeline replaces its old rows.

## 10. Indexes (`schema/create_indexes.py`)

| Collection | Index | Serves |
|---|---|---|
| customers | `customer_unique_id` (unique) · `segment.label` · `anomaly.risk_label` | identity, admin filters |
| users | `email` (unique) · `customer_id` | login, user ↔ customer |
| orders | `{customer_id, order_purchase_timestamp:-1}` · `order_status` · `line_items.product_id` · `{source, order_status}` | order history, Pipelines A/B, "also bought", review queue, fulfilment |
| products | `product_id` (unique) · `{category, sales_count:-1}` · `{sales_count:-1}` · `price` · **text** (name, labels; weighted) | product page, category best-sellers, sorting, search |
| reviews | `{product_id, created_at:-1}` · `customer_id` | product page, "already reviewed?" |
| events | `{customer_id, timestamp}` · `timestamp` | Pipeline C (`$setWindowFields`), activity counts |
| notifications | `{user_id, created_at:-1}` · **TTL** `created_at` (30 days) | bell menu, automatic expiry |
| alerts | `{status, created_at:-1}` | open-alert list |
| carts | `updated_at` | (`_id` is the customer id) |

## 11. Summary

| Relationship | Decision | Why |
|---|---|---|
| order → line items, payment | embed | bounded, immutable, read together; enables `$unwind` |
| customer → segment, anomaly | embed | small, single writer, hottest read path |
| customer → cart | separate doc keyed by customer id | one per customer, read and written whole |
| customer → events | reference (separate collection) | unbounded, write-heavy, partitioned by `$setWindowFields` |
| customer → orders | reference | unbounded history |
| product → reviews | reference | unbounded, paged |
| order/event/cart/review → product | reference (+ purchase-time snapshot on order lines) | many-to-many, independently updated |
| user → customer | reference | keeps credentials out of the analytics document |
