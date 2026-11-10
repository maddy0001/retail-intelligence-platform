#!/usr/bin/env bash
# Start the Retail Intelligence store (FastAPI API + built React app) on one port.
#   ./scripts/start_app.sh            -> http://localhost:8100
#   PORT=9000 ./scripts/start_app.sh  -> another port
# Build the React app first (cd frontend && npm install && npm run build),
# or run the Vite dev server on 5190 alongside this for hot reload.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8100}"
PY="venv/bin/python"
[ -x "$PY" ] || PY="python3"
echo "Kartiq is starting on http://localhost:$PORT   (press Ctrl+C to stop)"
exec "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT"
