"""db.py — one shared MongoClient for the whole process (pymongo pools connections)."""

from functools import lru_cache

from pymongo import MongoClient

from .settings import settings


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000, tz_aware=True)


def get_db():
    """FastAPI dependency and plain helper: the application database."""
    return get_client()[settings.mongo_db]
