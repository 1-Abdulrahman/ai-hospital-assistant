from __future__ import annotations

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE_DIR / "app" / "assets" / "nlp_models" / "distilbert-specialty"

REQUIRED_EXACT = [
    "config.json",
    "label_to_id.json",
    "labels.json",
    "thresholds.json",
    "model_version.txt",
    "dataset_report.json",
    "training_report.json",
    "metrics.json",
]

WEIGHTS_ANY_OF = [
    "model.safetensors",
    "pytorch_model.bin",
]

TOKENIZER_ANY_OF = [
    "tokenizer.json",
    "vocab.txt",
]

TOKENIZER_NICE_TO_HAVE = [
    "tokenizer_config.json",
    "special_tokens_map.json",
]


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    sys.exit(1)


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def main() -> None:
    if not MODEL_DIR.exists():
        fail(f"Model directory does not exist: {MODEL_DIR}")

    ok(f"Model directory found: {MODEL_DIR}")

    for filename in REQUIRED_EXACT:
        path = MODEL_DIR / filename
        if not path.exists():
            fail(f"Missing required file: {filename}")
        ok(f"Found required file: {filename}")

    if not any((MODEL_DIR / name).exists() for name in WEIGHTS_ANY_OF):
        fail(
            "Missing model weights. Expected one of: "
            + ", ".join(WEIGHTS_ANY_OF)
        )
    ok("Model weights file found")

    if not any((MODEL_DIR / name).exists() for name in TOKENIZER_ANY_OF):
        fail(
            "Missing tokenizer assets. Expected one of: "
            + ", ".join(TOKENIZER_ANY_OF)
        )
    ok("Tokenizer assets found")

    for filename in TOKENIZER_NICE_TO_HAVE:
        path = MODEL_DIR / filename
        if path.exists():
            ok(f"Found optional tokenizer file: {filename}")
        else:
            warn(f"Optional tokenizer file not found: {filename}")

    print("\nArtifact validation completed successfully.")


if __name__ == "__main__":
    main()