#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

wait_for_url() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-30}"
  local sleep_seconds="${4:-2}"

  echo "==> Waiting for $name at $url"

  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name OK"
      return 0
    fi

    echo "   [$attempt/$max_attempts] $name not ready yet..."
    sleep "$sleep_seconds"
    attempt=$((attempt + 1))
  done

  echo "ERROR: $name did not become ready in time."
  return 1
}

echo "==> Starting infra containers only: FHIR + MailHog"
cd "$REPO_ROOT/company"
docker compose up -d fhir mailhog

wait_for_url "FHIR" "http://localhost:8080/fhir/metadata" 40 2
wait_for_url "MailHog UI" "http://localhost:8025" 20 2

echo "==> Infra is ready"

echo "==> Start backend locally in another terminal with:"
echo "  cd $REPO_ROOT && ./tools/run_backend_local.sh"

echo "==> Optional: start Hospital UI locally with:"
echo "  cd $REPO_ROOT/hospital/ui && npm run dev -- --host 0.0.0.0 --port 3000"