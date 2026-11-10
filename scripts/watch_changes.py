"""
watch_changes.py: live view of every change Kartiq makes in MongoDB.

Keep this running in its own PowerShell window during the demo. Every insert,
update and delete appears here the moment it happens, read from a MongoDB
Change Stream (the same feature the app uses for live updates). Changes made
inside one multi-document transaction (checkout, cancel, sign-up, review) are
grouped under a "TRANSACTION" header, so you can show they commit together.

Run from the project folder:
    .\\venv\\Scripts\\python scripts\\watch_changes.py            # app activity only
    .\\venv\\Scripts\\python scripts\\watch_changes.py --all      # also simulator events
    .\\venv\\Scripts\\python scripts\\watch_changes.py --only orders,carts
Stop with Ctrl+C.
"""

import argparse
import os
import sys
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
DB = os.environ.get("MONGO_DB", "retail_intel")

WATCHED = ["users", "customers", "carts", "orders", "products", "reviews",
           "events", "notifications", "alerts"]

# colours (ANSI); os.system("") switches them on in the Windows console
os.system("")
try:
    sys.stdout.reconfigure(errors="replace")   # never crash on a console that lacks ₹ or box characters
except (AttributeError, ValueError):
    pass
RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
COLOUR = {"insert": "\033[92m", "update": "\033[93m", "replace": "\033[93m", "delete": "\033[91m"}
COLL_COLOUR = "\033[96m"
TX_COLOUR = "\033[95m"


def short(value, n=60):
    text = str(value)
    return text if len(text) <= n else text[: n - 1] + "…"


def money(doc):
    charged = (doc or {}).get("charged") or {}
    if charged.get("total") is not None:
        return f"₹{charged['total']:,.2f}"
    return f"R${(doc or {}).get('total', 0):,.2f}"


def describe(change):
    """One readable line for a change event."""
    op = change["operationType"]
    coll = change["ns"]["coll"]
    key = (change.get("documentKey") or {}).get("_id")
    doc = change.get("fullDocument") or {}
    upd = (change.get("updateDescription") or {}).get("updatedFields") or {}
    removed = (change.get("updateDescription") or {}).get("removedFields") or []

    if op == "delete":
        return f"document {key} deleted"

    if coll == "orders":
        if op == "insert":
            n = sum(int(li.get("quantity", 1)) for li in doc.get("line_items", []))
            return (f"NEW ORDER {key}  status={doc.get('order_status')}  items={n}  "
                    f"total={money(doc)}  payment={(doc.get('payment') or {}).get('type')}")
        if "order_status" in upd:
            return f"order {key}  order_status → {BOLD}{upd['order_status']}{RESET}"

    if coll == "carts":
        items = doc.get("items", [])
        if not items:
            return f"cart {key}  is now EMPTY"
        lines = ", ".join(f"{short(i.get('product_id'), 10)}×{i.get('quantity')}" for i in items)
        return f"cart {key}  {len(items)} line(s): {lines}"

    if coll == "events" and op == "insert":
        src = (doc.get("metadata") or {}).get("source", "?")
        return f"{doc.get('event_type')}  customer={doc.get('customer_id')}  source={src}"

    if coll == "users" and op == "insert":
        return f"NEW LOGIN {doc.get('email')}  role={doc.get('role')}  password stored as {short(doc.get('password_hash'), 14)}"

    if coll == "customers" and op == "insert":
        return f"NEW CUSTOMER {key}  source={doc.get('source')}"

    if coll == "reviews" and op == "insert":
        return f"NEW REVIEW {doc.get('rating')}★ on product {short(doc.get('product_id'), 12)}"

    if coll == "notifications" and op == "insert":
        return f"notification → \"{doc.get('title')}\""

    if coll == "alerts":
        if op == "insert":
            return f"RISK ALERT {doc.get('risk_label')} for {doc.get('customer_id')}: {doc.get('reason')}"
        if "status" in upd:
            return f"alert {key}  status → {upd['status']}"

    # generic: list the fields that changed
    if op in ("update", "replace"):
        shown = {k: v for k, v in upd.items() if not k.endswith("updated_at") and k != "status_changed_at"}
        parts = [f"{k}={short(v, 40)}" for k, v in list(shown.items())[:5]]
        if removed:
            parts.append("removed: " + ", ".join(removed))
        return f"{key}  " + ("  ".join(parts) if parts else "(timestamps only)")
    return f"{key}"


def main():
    ap = argparse.ArgumentParser(description="Live view of Kartiq's MongoDB changes")
    ap.add_argument("--all", action="store_true", help="also show synthetic simulator events")
    ap.add_argument("--only", help="comma-separated collections, e.g. orders,carts")
    args = ap.parse_args()

    colls = [c.strip() for c in args.only.split(",")] if args.only else WATCHED
    match = {"ns.coll": {"$in": colls}}
    if not args.all:
        # hide the simulator's synthetic events (they arrive ~30 sessions/min when traffic is on)
        match = {"$and": [match, {"$or": [{"ns.coll": {"$ne": "events"}},
                                           {"fullDocument.metadata.is_synthetic": {"$ne": True}}]}]}

    client = MongoClient(URI, serverSelectionTimeoutMS=5000)
    db = client[DB]
    print(f"{BOLD}Watching {DB}{RESET}  ({', '.join(colls)})  via a MongoDB Change Stream. Ctrl+C to stop.\n")

    last_txn = None
    try:
        with db.watch([{"$match": match}], full_document="updateLookup") as stream:
            for change in stream:
                txn = change.get("txnNumber")
                lsid = str((change.get("lsid") or {}).get("id"))
                tx_key = (lsid, txn) if txn is not None else None
                if tx_key and tx_key != last_txn:
                    if last_txn:
                        print(f"{TX_COLOUR}└─{RESET}")
                    print(f"{TX_COLOUR}{BOLD}┌─ TRANSACTION #{txn} (all of these commit together) ─{RESET}")
                elif not tx_key and last_txn:
                    print(f"{TX_COLOUR}└─{RESET}")
                last_txn = tx_key

                op = change["operationType"]
                stamp = datetime.now().strftime("%H:%M:%S")
                bar = f"{TX_COLOUR}│{RESET} " if tx_key else ""
                print(f"{bar}{DIM}{stamp}{RESET}  {COLOUR.get(op, '')}{op.upper():7}{RESET} "
                      f"{COLL_COLOUR}{change['ns']['coll']:<13}{RESET} {describe(change)}", flush=True)
    except KeyboardInterrupt:
        print("\nStopped.")
    except PyMongoError as exc:
        print(f"Could not watch MongoDB: {exc}")
        print("Is MongoDB running as a replica set? Check with:  Get-Service MongoDB")
        sys.exit(1)


if __name__ == "__main__":
    main()
