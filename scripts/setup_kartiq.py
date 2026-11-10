"""
setup_kartiq.py - one-time setup for Kartiq on any computer (Windows, macOS, Linux).

Normally you don't run this file yourself: scripts/setup_windows.bat and
scripts/setup_mac_linux.sh create the virtual environment, install the
packages and then run it. To run it directly, use the project's environment:

    Windows        venv\\Scripts\\python scripts\\setup_kartiq.py
    macOS / Linux  venv/bin/python scripts/setup_kartiq.py

What it does, in order:
  1. checks Python, the packages and the data files in data/raw;
  2. checks MongoDB: reachable, version 7.0 or newer, running as a replica set.
     If MongoDB was started with a replica-set name but never initiated, it
     initiates a single-node set (the same as running rs.initiate() in mongosh);
  3. proves that transactions and Change Streams work;
  4. loads the real Olist data, creates the indexes, generates the synthetic
     shopping activity, and runs the analytics (3 pipelines + 3 models);
  5. creates the demo accounts.

It takes about 3-5 minutes and is safe to run again: each run replaces the
previous data load (accounts and orders created in the app are kept).

    --check    only run the checks (steps 1-3)

MongoDB address: MONGO_URI (default mongodb://localhost:27017).
Database name:   MONGO_DB  (default retail_intel).
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "raw"
DATA_FILES = [
    "olist_customers_dataset.csv", "olist_orders_dataset.csv", "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv", "olist_products_dataset.csv", "olist_order_reviews_dataset.csv",
    "olist_sellers_dataset.csv", "product_category_name_translation.csv",
]
KAGGLE = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
STEPS = [
    ("Load the real Olist data (1-2 minutes)", ["data/load_olist_data.py", "--raw-dir", "data/raw"]),
    ("Create the indexes", ["schema/create_indexes.py"]),
    ("Generate the synthetic shopping activity", ["simulator/event_simulator.py", "--mode", "batch",
                                                  "--n-customers", "1500", "--n-sessions", "6000",
                                                  "--seed", "42"]),
    ("Run the pipelines and train the three models", ["ml/run_all.py"]),
]
WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"


def say(msg=""):
    print(msg, flush=True)


def stop(problem, *fix):
    say()
    say("SETUP STOPPED: " + problem)
    for line in fix:
        say("  " + line)
    say("  (START_HERE.md, section 'If something goes wrong', has more help.)")
    sys.exit(1)


# ---- 1. Python, packages, data ------------------------------------------------
def check_python():
    if sys.version_info < (3, 10):
        stop(f"Python {sys.version.split()[0]} is too old.",
             "Install Python 3.11, 3.12 or 3.13 from https://www.python.org and run the setup again.")
    say(f"OK  Python {sys.version.split()[0]}")


def check_packages():
    missing = []
    for module in ("pymongo", "pandas", "numpy", "sklearn", "joblib", "fastapi", "uvicorn", "jwt"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        pip = r"venv\Scripts\python -m pip" if WINDOWS else "venv/bin/python -m pip"
        stop("Missing Python packages: " + ", ".join(missing),
             f"Install them into the project's environment:  {pip} install -r requirements.txt")
    say("OK  Python packages")


def check_data():
    missing = [f for f in DATA_FILES if not (DATA_DIR / f).is_file()]
    if missing:
        stop(f"{len(missing)} data file(s) missing from data/raw: " + ", ".join(missing),
             f"Download the Olist dataset from {KAGGLE}",
             "and put its CSV files in the data/raw folder.")
    size = sum((DATA_DIR / f).stat().st_size for f in DATA_FILES) / 1e6
    say(f"OK  Olist data files in data/raw ({size:.0f} MB)")


# ---- 2-3. MongoDB ---------------------------------------------------------------
def start_mongo_help():
    if WINDOWS:
        return ["Is MongoDB installed and running? Start its service in a Command Prompt opened",
                "as administrator:  net start MongoDB"]
    if MAC:
        return ["Is MongoDB installed and running? Start it with:",
                "  brew services start mongodb-community   (or mongodb-community@7.0)"]
    return ["Is MongoDB installed and running? Start it with:  sudo systemctl start mongod"]


def replica_set_help():
    if WINDOWS:
        where = r"C:\Program Files\MongoDB\Server\<version>\bin\mongod.cfg  (open Notepad as administrator)"
        restart = "In a Command Prompt opened as administrator:  net stop MongoDB  then  net start MongoDB"
    elif MAC:
        where = "$(brew --prefix)/etc/mongod.conf   (usually /opt/homebrew/etc/mongod.conf)"
        restart = "brew services restart mongodb-community   (or mongodb-community@7.0)"
    else:
        where = "/etc/mongod.conf   (edit with sudo)"
        restart = "sudo systemctl restart mongod"
    return ["Kartiq needs MongoDB to run as a replica set (for transactions and Change Streams).",
            f"1. Open {where}",
            "2. Add these two lines at the end (replace a '#replication:' line if there is one):",
            "       replication:",
            "         replSetName: rs0",
            f"3. Restart MongoDB: {restart}",
            "4. Run this setup again; it initiates the replica set for you."]


def wait_for_primary(client, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        hello = client.admin.command("hello")
        if hello.get("isWritablePrimary"):
            return hello
        time.sleep(0.5)
    stop("The replica set did not elect a primary within 40 seconds.",
         "Restart MongoDB and run the setup again.")


def check_mongo():
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure, PyMongoError

    import config

    uri = config.MONGO_URI
    shown = uri.split("@")[-1] if "@" in uri else uri          # never print a password
    say(f"..  Connecting to MongoDB at {shown}  (database '{config.MONGO_DB}')")
    hosts = uri.split("://", 1)[-1].split("/", 1)[0]
    single = uri.startswith("mongodb://") and "," not in hosts and "replicaset=" not in uri.lower()
    try:
        # A direct connection reaches the server even before its replica set exists.
        client = MongoClient(uri, serverSelectionTimeoutMS=6000, **({"directConnection": True} if single else {}))
        hello = client.admin.command("hello")
        version = client.server_info()["version"]
    except PyMongoError as exc:
        stop(f"Could not reach MongoDB ({type(exc).__name__}).", *start_mongo_help())

    if int(version.split(".")[0]) < 7:
        stop(f"MongoDB {version} is too old.",
             "Kartiq needs MongoDB 7.0 or newer (it uses the $median accumulator).",
             "Install MongoDB Community Server 7.0 or 8.0.")

    if not hello.get("setName"):
        name = None
        if single:
            try:
                parsed = client.admin.command("getCmdLineOpts").get("parsed", {})
                replication = parsed.get("replication") or {}
                name = replication.get("replSetName") or replication.get("replSet")
            except PyMongoError:
                name = None
        if not name:
            stop("MongoDB is running, but not as a replica set.", *replica_set_help())
        host, port = client.address
        say(f"..  Initiating replica set '{name}' on {host}:{port} (one time, like rs.initiate())")
        try:
            client.admin.command("replSetInitiate", {"_id": name, "members": [{"_id": 0, "host": f"{host}:{port}"}]})
        except OperationFailure as exc:
            if exc.code != 23:                                  # 23 = AlreadyInitialized
                stop(f"Could not initiate the replica set: {exc}", *replica_set_help())
        hello = wait_for_primary(client)
    elif not hello.get("isWritablePrimary"):
        hello = wait_for_primary(client)
    say(f"OK  MongoDB {version}, replica set '{hello['setName']}'")

    # The app's own connection must manage a transaction and a Change Stream.
    from config import get_db
    try:
        db = get_db()
        probe = db["_setup_probe"]
        with probe.watch(max_await_time_ms=100):
            pass
        with db.client.start_session() as session:
            session.with_transaction(lambda s: probe.insert_one({"ok": True}, session=s))
        probe.drop()
    except PyMongoError as exc:
        stop(f"MongoDB answered, but a transaction or Change Stream failed: {exc}",
             f"Replica-set members: {', '.join(hello.get('hosts', []))}. If that address can't be reached,",
             "set MONGO_URI to  mongodb://localhost:27017/?directConnection=true  and run the setup again.")
    say("OK  transactions and Change Streams work")


# ---- 4-5. data, analytics, accounts ----------------------------------------------
def run_steps():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    for i, (title, args) in enumerate(STEPS, 1):
        say(f"\n[{i}/{len(STEPS)}] {title}")
        t0 = time.time()
        code = subprocess.call([sys.executable, *args], cwd=str(ROOT), env=env)
        if code != 0:
            stop(f"Step {i} failed: {title}.",
                 "The error is printed just above. Fix it and run the setup again; every step is safe to repeat.")
        say(f"    done in {time.time() - t0:.0f} s")


def seed_accounts():
    from backend.app.seed import seed_users
    from config import get_db

    seed_users(get_db())
    say("\nOK  demo accounts ready (the logins are in START_HERE.md)")


def main():
    parser = argparse.ArgumentParser(description="One-time setup for Kartiq (checks, data, models, accounts).")
    parser.add_argument("--check", action="store_true", help="only check Python, the data files and MongoDB")
    args = parser.parse_args()

    say("Kartiq setup")
    say("------------")
    check_python()
    check_packages()
    check_data()
    check_mongo()
    if args.check:
        say("\nAll checks passed.")
        return
    t0 = time.time()
    run_steps()
    seed_accounts()
    start = r"scripts\start_app_windows.bat" if WINDOWS else "bash scripts/start_app.sh"
    say(f"\nKartiq is ready (setup took {(time.time() - t0) / 60:.1f} min).")
    say(f"Start the store with:  {start}")
    say("then open  http://localhost:8100  in your browser.  Stop it with Ctrl+C.")


if __name__ == "__main__":
    main()
