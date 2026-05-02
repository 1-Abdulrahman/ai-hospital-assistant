#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPANY_DIR="$REPO_ROOT/company"
HOSPITAL_DIR="$REPO_ROOT/hospital"
BACKEND_DIR="$REPO_ROOT/company/backend"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env.localdev}"

RUNTIME_DIR="$REPO_ROOT/.runtime"
PORTAL_MODE_FILE="$RUNTIME_DIR/portal-ui.mode"

REBUILD_HOSPITAL_UI=0
SEED_DB=0
SEED_FHIR=0
CLEAN_START=0

# Both UIs start by default
WITH_HOSPITAL_UI=1
WITH_PORTAL_UI=1
PORTAL_MOCK=0

# Rebuild controls
REBUILD_PORTAL_UI=0
FORCE_REBUILD_PORTAL_REAL=0
FORCE_REBUILD_PORTAL_MOCK=0

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [options]

Options:
  --rebuild-hospital-ui      Rebuild Hospital UI container before starting it
  --seed-db                  Run backend DB seed after Alembic migrations
  --seed-fhir                Run FHIR seed after backend env is loaded
  --clean-start              Stop/remove existing company-fhir, company-mailhog, hospital-ui, and company-portal-ui containers first

  --no-hospital-ui           Do not start Hospital UI
  --no-portal-ui             Do not start Portal UI
  --portal-mock              Start Portal UI in mock preview mode instead of real backend mode

  --rebuild-portal-ui        Force rebuild Portal UI in the selected startup mode
  --rebuild-portal-ui-real   Force rebuild Portal UI in real mode and start it in real mode
  --rebuild-portal-ui-mock   Force rebuild Portal UI in mock mode and start it in mock mode

  -h, --help                 Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-hospital-ui)
      REBUILD_HOSPITAL_UI=1
      shift
      ;;
    --seed-db)
      SEED_DB=1
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
    --no-hospital-ui)
      WITH_HOSPITAL_UI=0
      shift
      ;;
    --no-portal-ui)
      WITH_PORTAL_UI=0
      shift
      ;;
    --portal-mock)
      PORTAL_MOCK=1
      WITH_PORTAL_UI=1
      shift
      ;;
    --rebuild-portal-ui)
      REBUILD_PORTAL_UI=1
      WITH_PORTAL_UI=1
      shift
      ;;
    --rebuild-portal-ui-real)
      FORCE_REBUILD_PORTAL_REAL=1
      REBUILD_PORTAL_UI=1
      PORTAL_MOCK=0
      WITH_PORTAL_UI=1
      shift
      ;;
    --rebuild-portal-ui-mock)
      FORCE_REBUILD_PORTAL_MOCK=1
      REBUILD_PORTAL_UI=1
      PORTAL_MOCK=1
      WITH_PORTAL_UI=1
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

ensure_runtime_dir() {
  mkdir -p "$RUNTIME_DIR"
}

selected_portal_mode() {
  if [[ "$PORTAL_MOCK" -eq 1 ]]; then
    echo "mock"
  else
    echo "real"
  fi
}

selected_portal_build_arg() {
  if [[ "$PORTAL_MOCK" -eq 1 ]]; then
    echo "true"
  else
    echo "false"
  fi
}

last_built_portal_mode() {
  if [[ -f "$PORTAL_MODE_FILE" ]]; then
    cat "$PORTAL_MODE_FILE"
  fi
}

remember_portal_mode() {
  local mode="$1"
  ensure_runtime_dir
  echo "$mode" > "$PORTAL_MODE_FILE"
}

portal_rebuild_required() {
  local selected_mode="$1"
  local last_mode
  last_mode="$(last_built_portal_mode || true)"

  if [[ "$REBUILD_PORTAL_UI" -eq 1 ]]; then
    return 0
  fi

  if [[ ! -f "$PORTAL_MODE_FILE" ]]; then
    return 0
  fi

  if [[ "$last_mode" != "$selected_mode" ]]; then
    return 0
  fi

  return 1
}

rebuild_portal_ui() {
  local mode="$1"
  local build_arg="$2"
  local build_flags=()

  if [[ "$mode" == "real" && "$FORCE_REBUILD_PORTAL_REAL" -eq 1 ]]; then
    build_flags+=(--no-cache)
  fi

  if [[ "$mode" == "mock" && "$FORCE_REBUILD_PORTAL_MOCK" -eq 1 ]]; then
    build_flags+=(--no-cache)
  fi

  if [[ ${#build_flags[@]} -gt 0 ]]; then
    echo "==> Force rebuilding Portal UI Docker image in $mode mode"
  else
    echo "==> Building Portal UI Docker image in $mode mode"
  fi

  cd "$COMPANY_DIR"
  PORTAL_VITE_USE_MOCKS="$build_arg" docker compose build "${build_flags[@]}" portal-ui

  remember_portal_mode "$mode"
}

start_portal_ui() {
  local mode="$1"
  local build_arg="$2"

  if portal_rebuild_required "$mode"; then
    rebuild_portal_ui "$mode" "$build_arg"
  else
    echo "==> Reusing existing Portal UI image built in $mode mode"
  fi

  echo "==> Starting Portal UI in Docker"
  cd "$COMPANY_DIR"
  PORTAL_VITE_USE_MOCKS="$build_arg" docker compose up -d portal-ui

  wait_for_url "Portal UI" "http://localhost:3001" 50 2
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

if [[ "$WITH_PORTAL_UI" -eq 0 ]]; then
  if [[ "$PORTAL_MOCK" -eq 1 || "$REBUILD_PORTAL_UI" -eq 1 || "$FORCE_REBUILD_PORTAL_REAL" -eq 1 || "$FORCE_REBUILD_PORTAL_MOCK" -eq 1 ]]; then
    echo "ERROR: Portal-specific flags were provided together with --no-portal-ui."
    exit 1
  fi
fi

if [[ "$WITH_HOSPITAL_UI" -eq 0 && "$REBUILD_HOSPITAL_UI" -eq 1 ]]; then
  echo "ERROR: --rebuild-hospital-ui cannot be used together with --no-hospital-ui."
  exit 1
fi

if [[ "$CLEAN_START" -eq 1 ]]; then
  echo "==> Clean starting Docker services"
  docker stop hospital-fhir company-mailhog hospital-ui company-portal-ui >/dev/null 2>&1 || true
  docker rm hospital-fhir company-mailhog hospital-ui company-portal-ui >/dev/null 2>&1 || true
fi

echo "==> Starting hospital FHIR in Docker"
cd "$HOSPITAL_DIR"
docker compose up -d fhir

echo "==> Starting MailHog in Docker"
cd "$COMPANY_DIR"
docker compose up -d mailhog

if [[ "$WITH_HOSPITAL_UI" -eq 1 ]]; then
  echo "==> Starting Hospital UI in Docker"
  cd "$HOSPITAL_DIR"
  if [[ "$REBUILD_HOSPITAL_UI" -eq 1 ]]; then
    docker compose up -d --build hospital-ui
  else
    docker compose up -d hospital-ui
  fi
fi

wait_for_url "FHIR" "http://localhost:8080/fhir/metadata" 50 2
wait_for_url "MailHog UI" "http://localhost:8025" 30 2

if [[ "$WITH_HOSPITAL_UI" -eq 1 ]]; then
  wait_for_url "Hospital UI" "http://localhost:3000" 40 2
fi

if [[ "$WITH_PORTAL_UI" -eq 1 ]]; then
  PORTAL_MODE="$(selected_portal_mode)"
  PORTAL_BUILD_ARG="$(selected_portal_build_arg)"

  if [[ "$PORTAL_MODE" == "mock" ]]; then
    echo "==> Portal UI mode: MOCK PREVIEW"
  else
    echo "==> Portal UI mode: REAL BACKEND (default)"
  fi

  start_portal_ui "$PORTAL_MODE" "$PORTAL_BUILD_ARG"
fi

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

if [[ "$SEED_DB" -eq 1 ]]; then
  echo "==> Running backend DB seed"
  python -m app.db.seed
fi

if [[ "$SEED_FHIR" -eq 1 ]]; then
  echo "==> Running FHIR scheduling seed"
  python -m app.modules.fhir_gateway.seed
fi

echo
echo "==> Runtime summary"
echo "Backend      : http://localhost:8000"
if [[ "$WITH_HOSPITAL_UI" -eq 1 ]]; then
  echo "Hospital UI  : http://localhost:3000"
fi
if [[ "$WITH_PORTAL_UI" -eq 1 ]]; then
  echo "Portal UI    : http://localhost:3001"
fi
echo "FHIR         : http://localhost:8080/fhir/metadata"
echo "MailHog UI   : http://localhost:8025"
echo

if [[ "$WITH_PORTAL_UI" -eq 1 ]]; then
  if [[ "$PORTAL_MOCK" -eq 1 ]]; then
    echo "==> Portal login (mock preview): http://localhost:3001/login?mock=1"
  else
    echo "==> Portal login (real backend): http://localhost:3001/login?mock=0"
  fi
fi

if [[ "$WITH_HOSPITAL_UI" -eq 1 ]]; then
  echo "==> Hospital app: http://localhost:3000"
fi

echo
echo "==> Starting backend locally with auto-reload"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload