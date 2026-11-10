"""
settings.py — runtime configuration for the FastAPI back end, from environment variables.

Every default here is a local-development value. Set real values through the
environment for anything beyond a laptop demo (especially JWT_SECRET).
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]          # retail-intelligence-platform/
if str(ROOT_DIR) not in sys.path:                        # so `config`, `pipelines`, `ml` import
    sys.path.insert(0, str(ROOT_DIR))

import config  # noqa: E402


class Settings:
    mongo_uri: str = os.environ.get("MONGO_URI", config.MONGO_URI)
    mongo_db: str = os.environ.get("MONGO_DB", config.MONGO_DB)

    # Signs login tokens. The default is for local development only.
    jwt_secret: str = os.environ.get("JWT_SECRET", "local-dev-only-retail-intel-secret-change-me")
    jwt_expire_minutes: int = int(os.environ.get("JWT_EXPIRE_MINUTES", str(60 * 24)))

    # Background workers: the Change Stream listener and the order-fulfilment
    # simulator. Tests switch them off and call the handlers directly.
    background: bool = os.environ.get("APP_BACKGROUND", "1") == "1"
    # Demo pace: an app order moves processing -> shipped -> delivered every N seconds.
    fulfillment_step_seconds: int = int(os.environ.get("FULFILLMENT_STEP_SECONDS", "20"))

    # Risk triggers watched on the events Change Stream.
    abandon_threshold: int = int(os.environ.get("ABANDON_THRESHOLD", "3"))
    abandon_window_minutes: int = int(os.environ.get("ABANDON_WINDOW_MINUTES", "30"))
    payment_fail_threshold: int = int(os.environ.get("PAYMENT_FAIL_THRESHOLD", "2"))
    payment_fail_window_minutes: int = int(os.environ.get("PAYMENT_FAIL_WINDOW_MINUTES", "10"))

    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"
    cors_origins = [o.strip() for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5190,http://127.0.0.1:5190").split(",") if o.strip()]


settings = Settings()
