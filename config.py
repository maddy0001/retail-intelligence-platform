"""
config.py
---------
Central configuration for the Real-Time Retail Intelligence Platform.

Reads connection details from environment variables so the same code works
against a local mongod, a Docker container, or MongoDB Atlas without edits.

    export MONGO_URI="mongodb://localhost:27017/?replicaSet=rs0"
    export MONGO_DB="retail_intel"

Change Streams and multi-document transactions (both used by the app) need
MongoDB to run as a replica set; a single-node replica set is enough.
If MONGO_URI is not set, the code defaults to a local instance.
"""

import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "retail_intel")

# --- Core collections -------------------------------------------------------
# REAL Olist data (source: "olist") and app-created records (source: "app")
COLL_CUSTOMERS = "customers"
COLL_ORDERS = "orders"
COLL_PRODUCTS = "products"
COLL_REVIEWS = "reviews"

# Behavioral events: SYNTHETIC simulator events (metadata.is_synthetic: true)
# and events produced by people using the app (metadata.source: "app").
COLL_EVENTS = "events"

# --- App collections (created by the FastAPI back end) ----------------------
COLL_USERS = "users"                    # login accounts -> customers
COLL_CARTS = "carts"                    # one cart per customer, items embedded
COLL_NOTIFICATIONS = "notifications"    # TTL-indexed user notifications
COLL_ALERTS = "alerts"                  # risk alerts raised from Change Streams

# --- Derived / written-back collections ------------------------------------
COLL_RFM = "rfm_features"              # output of Pipeline A
COLL_AFFINITY = "category_affinity"    # output of Pipeline B
COLL_ROLLING_METRICS = "rolling_behavioral_metrics"  # output of Pipeline C
COLL_CATEGORY_SIMILARITY = "category_similarity"     # output of Module 2
COLL_ML_RUNS = "ml_runs"               # one document per analytics run

# Order statuses that count as a completed purchase for RFM / affinity.
COMPLETED_STATUSES = ["delivered", "shipped"]

# Where trained models are saved so the API can score single customers live.
# Tests point this at a temporary folder so they never overwrite the real models.
MODEL_DIR = os.environ.get("RETAIL_MODEL_DIR",
                           os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml", "models"))


def get_client(uri: str = MONGO_URI):
    """Return a pymongo MongoClient. Import is local so modules that only
    need mongomock for offline testing don't require a live pymongo driver
    at import time."""
    from pymongo import MongoClient
    return MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)


def get_db(uri: str = MONGO_URI, db_name: str = MONGO_DB):
    """Return a pymongo Database handle."""
    return get_client(uri)[db_name]
