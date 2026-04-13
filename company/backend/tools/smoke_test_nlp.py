from __future__ import annotations

import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_LOCAL_FILES_ONLY", "1")

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


from app.main import app  # noqa: E402


def main() -> None:
    samples = [
    {
        "text": "chest pain when walking",
        "expected_top": "cardiology",
        "allow_clarification": True,
        "strict_top_only": True,
    },
    {
        "text": "itchy red rash on my arm",
        "expected_top": "dermatology",
        "allow_clarification": True,
        "strict_top_only": True,
    },
    {
        "text": "I feel unwell",
        "expected_top": None,
        "allow_clarification": True,
        "strict_top_only": False,
    },
]

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200, health.text

        service = app.state.nlp_service
        if service is None:
            raise SystemExit("[FAIL] NLP service is not loaded.")

        print("[INFO] Using model:", service.model_name, service.model_version)
        print()

        for sample in samples:
            prediction = service.classify(sample["text"])

            top_label = (
                prediction.top_candidates[0].specialty_id
                if prediction.top_candidates
                else None
            )

            print("Input:", sample["text"])
            print("Top 3:", [(c.specialty_id, c.confidence) for c in prediction.top_candidates])
            print("primary_specialty_id:", prediction.primary_specialty_id)
            print("needs_clarification:", prediction.needs_clarification)
            print("reason_code:", prediction.reason_code)
            print()

            if sample["strict_top_only"]:
                if top_label != sample["expected_top"]:
                    raise SystemExit(
                        f"[FAIL] Expected top label {sample['expected_top']}, got {top_label}"
                    )

                if not sample["allow_clarification"] and prediction.needs_clarification:
                    raise SystemExit(
                        f"[FAIL] Unexpected clarification for input: {sample['text']}"
                    )
            else:
                if not prediction.needs_clarification:
                    print(
                        "[WARN] Vague complaint did not become ambiguous. "
                        "This may be acceptable for now, but usually vague inputs "
                        "should trigger clarification."
                    )

        print("[OK] Smoke test completed.")


if __name__ == "__main__":
    main()