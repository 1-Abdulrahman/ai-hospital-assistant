from __future__ import annotations

import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE_DIR / "app" / "assets" / "nlp_models" / "distilbert-specialty"

EVAL_REPORT = MODEL_DIR / "eval_report.json"
PER_LABEL_METRICS = MODEL_DIR / "per_label_metrics.json"
CONFUSION_MATRIX_JSON = MODEL_DIR / "confusion_matrix.json"
CONFUSION_MATRIX_PNG = MODEL_DIR / "confusion_matrix.png"


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    sys.exit(1)


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def main() -> None:
    for path in [
        EVAL_REPORT,
        PER_LABEL_METRICS,
        CONFUSION_MATRIX_JSON,
        CONFUSION_MATRIX_PNG,
    ]:
        if not path.exists():
            fail(f"Missing evaluation output: {path.name}")
        ok(f"Found evaluation output: {path.name}")

    eval_report = json.loads(EVAL_REPORT.read_text(encoding="utf-8"))
    cm = json.loads(CONFUSION_MATRIX_JSON.read_text(encoding="utf-8"))

    metrics = eval_report.get("metrics", {})
    accuracy = metrics.get("accuracy")
    macro_f1 = metrics.get("macroF1")

    if accuracy is None:
        fail("eval_report.json is missing metrics.accuracy")
    if macro_f1 is None:
        fail("eval_report.json is missing metrics.macroF1")

    ok(f"Accuracy found: {accuracy:.4f}")
    ok(f"Macro F1 found: {macro_f1:.4f}")

    if accuracy >= 0.75:
        ok("Accuracy meets target (>= 0.75)")
    else:
        warn("Accuracy is below target (>= 0.75)")

    if macro_f1 >= 0.70:
        ok("Macro F1 meets target (>= 0.70)")
    else:
        warn("Macro F1 is below target (>= 0.70)")

    labels = cm.get("labels", [])
    matrix = cm.get("matrix", [])

    if not labels or not matrix:
        fail("confusion_matrix.json is missing labels or matrix")

    n = len(labels)
    if len(matrix) != n:
        fail("Confusion matrix row count does not match labels count")

    for row in matrix:
        if len(row) != n:
            fail("Confusion matrix is not square")

    ok(f"Confusion matrix shape is valid: {n} x {n}")
    print("\nEvaluation artifact validation completed successfully.")


if __name__ == "__main__":
    main()