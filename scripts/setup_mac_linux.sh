#!/usr/bin/env bash
# One-time setup for Kartiq on macOS or Linux:
#   a Python virtual environment, the packages, then scripts/setup_kartiq.py
#   (MongoDB check, real data, synthetic activity, models, demo accounts).
#
#   bash scripts/setup_mac_linux.sh                    uses python3
#   PYTHON=python3.12 bash scripts/setup_mac_linux.sh  uses another Python
set -euo pipefail
cd "$(dirname "$0")/.."
# Prefer a Python that every package has ready-made builds for (3.15 is too new for one of them).
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for v in python3.13 python3.12 python3.14 python3.11 python3; do
    if command -v "$v" >/dev/null 2>&1; then PY="$v"; break; fi
  done
fi
if [ ! -x venv/bin/python ]; then
  echo "Creating a Python virtual environment in ./venv with $("$PY" --version) ..."
  "$PY" -m venv venv
fi
echo "Installing the Python packages (first time: a few minutes) ..."
venv/bin/python -m pip install --upgrade pip --quiet
venv/bin/python -m pip install -r requirements.txt --quiet
venv/bin/python scripts/setup_kartiq.py "$@"
