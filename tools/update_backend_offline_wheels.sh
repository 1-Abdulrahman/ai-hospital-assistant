#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ_FILE="$REPO_ROOT/company/backend/requirements.txt"
WHEEL_DIR="$REPO_ROOT/docs/offline/wheels"
VERIFY_DIR="$REPO_ROOT/docs/offline/.wheel-verify-venv"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"

echo "==> Repo root: $REPO_ROOT"
echo "==> Requirements: $REQ_FILE"
echo "==> Wheel output: $WHEEL_DIR"
echo "==> Python: $PYTHON_BIN"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN not found."
  exit 1
fi

mkdir -p "$WHEEL_DIR"

echo "==> Checking Python version"
"$PYTHON_BIN" --version

echo "==> Upgrading packaging tools"
"$PYTHON_BIN" -m pip install --upgrade pip==24.2 setuptools wheel

echo "==> Cleaning wheelhouse"
find "$WHEEL_DIR" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' -delete

echo "==> Downloading pinned wheels only"
"$PYTHON_BIN" -m pip download \
  --only-binary=:all: \
  --dest "$WHEEL_DIR" \
  -r "$REQ_FILE"

echo "==> Listing downloaded files"
find "$WHEEL_DIR" -maxdepth 1 -type f | sort

echo "==> Creating verification venv"
rm -rf "$VERIFY_DIR"
"$PYTHON_BIN" -m venv "$VERIFY_DIR"

# shellcheck disable=SC1091
source "$VERIFY_DIR/bin/activate"

echo "==> Upgrading pip inside verification venv"
python -m pip install --upgrade pip==24.2

echo "==> Testing offline installation from local wheelhouse"
python -m pip install \
  --no-index \
  --find-links "$WHEEL_DIR" \
  -r "$REQ_FILE"

echo "==> Running pip check"
python -m pip check

echo "==> Smoke import test"
python - <<'PY'
import fastapi
import sqlalchemy
import httpx
import jose
import passlib
import structlog
import pytest
import transformers
import torch

print("Offline wheel verification OK")
print("fastapi:", fastapi.__version__)
print("sqlalchemy:", sqlalchemy.__version__)
print("httpx:", httpx.__version__)
print("transformers:", transformers.__version__)
print("torch:", torch.__version__)
PY

deactivate

echo "==> Cleaning verification venv"
rm -rf "$VERIFY_DIR"

echo "==> DONE: offline wheelhouse updated successfully"