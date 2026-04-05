from __future__ import annotations

import json
import os
import random
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer


# ============================================================
# Configuration
# ============================================================

RANDOM_SEED = 42
MAX_LENGTH = 96

# Strict offline option. Set to 1 in the environment when needed.
LOCAL_FILES_ONLY = os.getenv("HF_LOCAL_FILES_ONLY", "0") == "1"

EVAL_FILE = Path(__file__).resolve()
BACKEND_ROOT = EVAL_FILE.parents[4]  # company/backend
APP_ROOT = BACKEND_ROOT / "app"
TRAINING_DIR = EVAL_FILE.parent
MODEL_DIR = APP_ROOT / "assets" / "nlp_models" / "distilbert-specialty"

DATASET_PATH = TRAINING_DIR / "dataset.jsonl"
LABEL_TO_ID_PATH = MODEL_DIR / "label_to_id.json"
LABELS_PATH = MODEL_DIR / "labels.json"
MODEL_VERSION_PATH = MODEL_DIR / "model_version.txt"
METRICS_PATH = MODEL_DIR / "metrics.json"

# Outputs produced by eval.py
EVAL_REPORT_PATH = MODEL_DIR / "eval_report.json"
PER_LABEL_METRICS_PATH = MODEL_DIR / "per_label_metrics.json"
CONFUSION_MATRIX_JSON_PATH = MODEL_DIR / "confusion_matrix.json"
CONFUSION_MATRIX_PNG_PATH = MODEL_DIR / "confusion_matrix.png"


# ============================================================
# Helpers
# ============================================================

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_jsonl(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc

            if "text" not in item or "label" not in item:
                raise ValueError(
                    f"Line {line_number} must contain both 'text' and 'label'."
                )

            text = str(item["text"]).strip()
            label = str(item["label"]).strip()

            if not text:
                raise ValueError(f"Line {line_number} contains empty text.")
            if not label:
                raise ValueError(f"Line {line_number} contains empty label.")

            rows.append({"text": text, "label": label})

    if not rows:
        raise ValueError("Dataset is empty.")

    return rows


class ComplaintDataset(Dataset):
    def __init__(
        self,
        texts: list[str],
        label_ids: list[int],
        tokenizer: Any,
        max_length: int,
    ) -> None:
        self.texts = texts
        self.label_ids = label_ids
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        encoded = self.tokenizer(
            self.texts[idx],
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )
        item = {k: v.squeeze(0) for k, v in encoded.items()}
        item["labels"] = torch.tensor(self.label_ids[idx], dtype=torch.long)
        return item


def rebuild_test_split(
    texts: list[str],
    label_ids: list[int],
) -> tuple[list[str], list[int]]:
    """
    Rebuild the exact same deterministic split logic used in train.py:
    80% train, 10% validation, 10% test with stratification.

    Important:
    This works only if dataset.jsonl content and ordering are unchanged
    since training time.
    """
    _, temp_texts, _, temp_ids = train_test_split(
        texts,
        label_ids,
        test_size=0.20,
        random_state=RANDOM_SEED,
        shuffle=True,
        stratify=label_ids,
    )

    _, test_texts, _, test_ids = train_test_split(
        temp_texts,
        temp_ids,
        test_size=0.50,
        random_state=RANDOM_SEED,
        shuffle=True,
        stratify=temp_ids,
    )

    return test_texts, test_ids


def predict_all(
    model: Any,
    dataset: ComplaintDataset,
    device: torch.device,
) -> tuple[list[int], list[int]]:
    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []

    with torch.no_grad():
        for i in range(len(dataset)):
            item = dataset[i]

            labels = item["labels"].unsqueeze(0).to(device)

            inputs = {
                "input_ids": item["input_ids"].unsqueeze(0).to(device),
                "attention_mask": item["attention_mask"].unsqueeze(0).to(device),
            }

            if "token_type_ids" in item:
                inputs["token_type_ids"] = item["token_type_ids"].unsqueeze(0).to(device)

            outputs = model(**inputs)
            predicted_class = int(torch.argmax(outputs.logits, dim=-1).item())

            y_true.append(int(labels.item()))
            y_pred.append(predicted_class)

    return y_true, y_pred


def main() -> None:
    set_seed(RANDOM_SEED)

    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    if not MODEL_DIR.exists():
        raise FileNotFoundError(f"Model directory not found: {MODEL_DIR}")

    if not LABEL_TO_ID_PATH.exists():
        raise FileNotFoundError(f"Missing label_to_id.json: {LABEL_TO_ID_PATH}")

    label_to_id: dict[str, int] = read_json(LABEL_TO_ID_PATH)
    id_to_label = {v: k for k, v in label_to_id.items()}

    if LABELS_PATH.exists():
        labels_list: list[str] = read_json(LABELS_PATH)
    else:
        labels_list = [id_to_label[i] for i in sorted(id_to_label)]

    model_version = (
        MODEL_VERSION_PATH.read_text(encoding="utf-8").strip()
        if MODEL_VERSION_PATH.exists()
        else "unknown"
    )

    rows = read_jsonl(DATASET_PATH)
    unknown_labels = sorted({row["label"] for row in rows if row["label"] not in label_to_id})
    if unknown_labels:
        raise ValueError(
            f"Dataset contains labels not present in label_to_id.json: {unknown_labels}"
        )

    texts = [row["text"] for row in rows]
    labels = [row["label"] for row in rows]
    label_ids = [label_to_id[label] for label in labels]

    test_texts, test_ids = rebuild_test_split(texts, label_ids)

    tokenizer = AutoTokenizer.from_pretrained(
        str(MODEL_DIR),
        local_files_only=LOCAL_FILES_ONLY,
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        str(MODEL_DIR),
        local_files_only=LOCAL_FILES_ONLY,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    test_dataset = ComplaintDataset(
        texts=test_texts,
        label_ids=test_ids,
        tokenizer=tokenizer,
        max_length=MAX_LENGTH,
    )

    y_true, y_pred = predict_all(model=model, dataset=test_dataset, device=device)

    accuracy = float(accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro"))

    per_label_report = classification_report(
        y_true,
        y_pred,
        labels=list(range(len(labels_list))),
        target_names=labels_list,
        output_dict=True,
        zero_division=0,
    )

    matrix = confusion_matrix(
        y_true,
        y_pred,
        labels=list(range(len(labels_list))),
    )

    # Save raw confusion matrix data
    confusion_payload = {
        "labels": labels_list,
        "matrix": matrix.tolist(),
    }
    write_json(CONFUSION_MATRIX_JSON_PATH, confusion_payload)

    # Save image artifact
    fig, ax = plt.subplots(figsize=(10, 8))
    display = ConfusionMatrixDisplay(
        confusion_matrix=matrix,
        display_labels=labels_list,
    )
    display.plot(ax=ax, xticks_rotation=45, colorbar=False)
    ax.set_title(f"NLP Confusion Matrix | version={model_version}")
    fig.tight_layout()
    fig.savefig(CONFUSION_MATRIX_PNG_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Save per-label metrics only
    per_label_metrics = {
        label: per_label_report[label]
        for label in labels_list
        if label in per_label_report
    }
    write_json(PER_LABEL_METRICS_PATH, per_label_metrics)

    # Save summary evaluation report
    eval_report = {
        "modelVersion": model_version,
        "device": str(device),
        "localFilesOnly": LOCAL_FILES_ONLY,
        "dataset": {
            "totalSamples": len(rows),
            "testSamples": len(test_dataset),
            "classCounts": dict(sorted(Counter(labels).items())),
            "splitStrategy": "reconstructed deterministic 80/10/10 stratified split",
            "randomSeed": RANDOM_SEED,
        },
        "metrics": {
            "accuracy": accuracy,
            "macroF1": macro_f1,
            "targetAccuracy": 0.75,
            "targetMacroF1": 0.70,
            "meetsAccuracyTarget": accuracy >= 0.75,
            "meetsMacroF1Target": macro_f1 >= 0.70,
        },
        "artifacts": {
            "perLabelMetrics": str(PER_LABEL_METRICS_PATH.name),
            "confusionMatrixJson": str(CONFUSION_MATRIX_JSON_PATH.name),
            "confusionMatrixPng": str(CONFUSION_MATRIX_PNG_PATH.name),
        },
    }
    write_json(EVAL_REPORT_PATH, eval_report)

    # Optionally merge test metrics into metrics.json if it already exists
    if METRICS_PATH.exists():
        existing_metrics = read_json(METRICS_PATH)
    else:
        existing_metrics = {}

    existing_metrics["evaluation"] = eval_report
    write_json(METRICS_PATH, existing_metrics)

    print("Evaluation completed successfully.")
    print(json.dumps(eval_report, indent=2))


if __name__ == "__main__":
    main()