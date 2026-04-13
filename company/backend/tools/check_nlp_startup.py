from __future__ import annotations

import os
import sys
from pathlib import Path

# ------------------------------------------------------------
# Make sure the backend root is on sys.path
# This file lives in: company/backend/tools/check_nlp_startup.py
# We need:             company/backend
# ------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# ------------------------------------------------------------
# Force offline mode before importing the FastAPI app
# This ensures startup loading uses local artifacts only.
# ------------------------------------------------------------
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_LOCAL_FILES_ONLY", "1")

from fastapi.testclient import TestClient
from app.main import app  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200, response.text

        if not hasattr(app.state, "nlp_available"):
            raise SystemExit("[FAIL] app.state.nlp_available was not set during startup.")

        if not hasattr(app.state, "nlp_status"):
            raise SystemExit("[FAIL] app.state.nlp_status was not set during startup.")

        print("[INFO] /health status:", response.status_code)
        print("[INFO] nlp_available:", app.state.nlp_available)
        print("[INFO] nlp_status:", app.state.nlp_status)

        if not app.state.nlp_available:
            raise SystemExit(
                "[FAIL] Backend startup completed, but NLP service was not loaded. "
                "Check artifacts, inference loader, and startup wiring."
            )

        if getattr(app.state, "nlp_service", None) is None:
            raise SystemExit(
                "[FAIL] app.state.nlp_service is None even though nlp_available is True."
            )

        service_status = app.state.nlp_service.status()
        print("[INFO] service status:", service_status)

        print("\n[OK] Backend startup loaded NLP service successfully in offline mode.")


if __name__ == "__main__":
    main()