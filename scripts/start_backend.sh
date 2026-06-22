#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt -q
export PYTHONPATH="$PWD"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
