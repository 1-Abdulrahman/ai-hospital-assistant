#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/company/backend"

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  echo "ERROR: backend virtual environment .venv not found"
  echo "Create it first with:"
  echo "  python3.13 -m venv .venv"
  exit 1
fi

source .venv/bin/activate
export $(grep -v '^#' .env.localdev | xargs)

echo "==> Running Alembic migrations"
alembic upgrade head

echo "==> Starting backend locally on http://localhost:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload