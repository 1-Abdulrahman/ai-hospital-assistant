#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT/company"
docker compose stop fhir mailhog portal-ui || true

cd "$REPO_ROOT/hospital"
docker compose stop hospital-ui || true

echo "Stopped FHIR, MailHog, Portal UI, and Hospital UI containers."