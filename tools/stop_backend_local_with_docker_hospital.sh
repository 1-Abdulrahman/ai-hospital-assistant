#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT/company"
docker compose stop fhir mailhog || true

cd "$REPO_ROOT/hospital"
docker compose stop hospital-ui || true

echo "Stopped FHIR, MailHog, and Hospital UI containers."