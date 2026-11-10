"""
Root pytest configuration. Runs before any project module is imported, so the
whole test session uses a separate database (retail_intel_test), a temporary
model folder, and no background threads. Tests need a running MongoDB replica
set (the same local mongod the app uses); they never touch `retail_intel`.
"""

import os
import sys
import tempfile

os.environ["MONGO_DB"] = "retail_intel_test"
os.environ["APP_BACKGROUND"] = "0"
os.environ.setdefault("RETAIL_MODEL_DIR", tempfile.mkdtemp(prefix="retail_models_"))
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-use-0123456789")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
