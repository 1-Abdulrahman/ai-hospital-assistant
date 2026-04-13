#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPANY_DIR="$REPO_ROOT/company"
HOSPITAL_DIR="$REPO_ROOT/hospital"
BACKEND_DIR="$REPO_ROOT/company/backend"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env.localdev}"

REBUILD_HOSPITAL_UI=0
SEED_FHIR=0
CLEAN_START=0

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [--rebuild-hospital-ui] [--seed-fhir] [--clean-start]

Options:
  --rebuild-hospital-ui   Rebuild Hospital UI container before starting it
  --seed-fhir             Run FHIR seed after backend env is loaded
  --clean-start           Stop/remove existing company-fhir, company-mailhog, and hospital-ui containers first
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-hospital-ui)
      REBUILD_HOSPITAL_UI=1
      shift
      ;;
    --seed-fhir)
      SEED_FHIR=1
      shift
      ;;
    --clean-start)
      CLEAN_START=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

wait_for_url() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-40}"
  local sleep_seconds="${4:-2}"

  echo "==> Waiting for $name at $url"

  local attempt=1
  while [[ "$attempt" -le "$max_attempts" ]]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "==> $name is ready"
      return 0
    fi

    echo "   [$attempt/$max_attempts] $name not ready yet..."
    sleep "$sleep_seconds"
    attempt=$((attempt + 1))
  done

  echo "ERROR: $name did not become ready in time."
  return 1
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $cmd"
    exit 1
  fi
}

echo "==> Validating prerequisites"
require_command docker
require_command curl
require_command python3.13

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  echo "ERROR: backend virtual environment not found at:"
  echo "  $BACKEND_DIR/.venv"
  echo
  echo "Create it first:"
  echo "  cd $BACKEND_DIR"
  echo "  python3.13 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: backend env file not found:"
  echo "  $ENV_FILE"
  exit 1
fi

if [[ "$CLEAN_START" -eq 1 ]]; then
  echo "==> Clean starting Docker services"
  docker stop company-fhir company-mailhog hospital-ui >/dev/null 2>&1 || true
  docker rm company-fhir company-mailhog hospital-ui >/dev/null 2>&1 || true
fi

echo "==> Starting FHIR and MailHog in Docker"
cd "$COMPANY_DIR"
docker compose up -d fhir mailhog

echo "==> Starting Hospital UI in Docker"
cd "$HOSPITAL_DIR"
if [[ "$REBUILD_HOSPITAL_UI" -eq 1 ]]; then
  docker compose up -d --build hospital-ui
else
  docker compose up -d hospital-ui
fi

wait_for_url "FHIR" "http://localhost:8080/fhir/metadata" 50 2
wait_for_url "MailHog UI" "http://localhost:8025" 30 2
wait_for_url "Hospital UI" "http://localhost:3000" 40 2

echo "==> Loading backend environment from $ENV_FILE"
cd "$BACKEND_DIR"
set -a
source "$ENV_FILE"
set +a

echo "==> Activating backend virtual environment"
# shellcheck disable=SC1091
source "$BACKEND_DIR/.venv/bin/activate"

echo "==> Running Alembic migrations"
alembic upgrade head

if [[ "$SEED_FHIR" -eq 1 ]]; then
  echo "==> Running FHIR scheduling seed"
  python -m app.modules.fhir_gateway.seed
fi

echo
echo "==> Runtime summary"
echo "Backend      : http://localhost:8000"
echo "Hospital UI  : http://localhost:3000"
echo "FHIR         : http://localhost:8080/fhir/metadata"
echo "MailHog UI   : http://localhost:8025"
echo
echo "==> Starting backend locally with auto-reload"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload