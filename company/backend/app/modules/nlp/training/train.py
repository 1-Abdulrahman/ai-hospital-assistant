from __future__ import annotations

import json
import os
import platform
import random
import shutil
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

# ============================================================
# Configuration
# ============================================================

RANDOM_SEED = 42
MAX_LENGTH = 96
NUM_EPOCHS = 4
TRAIN_BATCH_SIZE = 16
EVAL_BATCH_SIZE = 16
LEARNING_RATE = 2e-5
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.10

# For the first run, this can be a Hugging Face model ID such as:
# "distilbert-base-uncased"
# For fully offline training, point this to a LOCAL directory that already
# contains the base tokenizer/model files.
BASE_MODEL_NAME_OR_PATH = os.getenv("NLP_BASE_MODEL", "distilbert-base-uncased")

# Optional switch for strict offline loading
LOCAL_FILES_ONLY = os.getenv("HF_LOCAL_FILES_ONLY", "0") == "1"

# Resolve paths relative to this file
TRAIN_FILE = Path(__file__).resolve()
BACKEND_ROOT = TRAIN_FILE.parents[4]  # company/backend
APP_ROOT = BACKEND_ROOT / "app"
TRAINING_DIR = TRAIN_FILE.parent
MODEL_DIR = APP_ROOT / "assets" / "nlp_models" / "distilbert-specialty"

DATASET_PATH = TRAINING_DIR / "dataset.jsonl"
LABEL_TO_ID_PATH = MODEL_DIR / "label_to_id.json"
LABELS_PATH = MODEL_DIR / "labels.json"
THRESHOLDS_PATH = MODEL_DIR / "thresholds.json"
MODEL_VERSION_PATH = MODEL_DIR / "model_version.txt"
DATASET_REPORT_PATH = MODEL_DIR / "dataset_report.json"
TRAINING_REPORT_PATH = MODEL_DIR / "training_report.json"
METRICS_PATH = MODEL_DIR / "metrics.json"

CHECKPOINT_DIR = MODEL_DIR / "_checkpoints"

DEFAULT_THRESHOLDS = {
    "minConfidence": 0.70,
    "ambiguityDelta": 0.10,
}

DEFAULT_MODEL_VERSION = "1.0.0"


# ============================================================
# Reproducibility helpers
# ============================================================

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ============================================================
# File helpers
# ============================================================

def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_jsonl(path: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc

            if "text" not in row or "label" not in row:
                raise ValueError(
                    f"Line {line_number} must contain both 'text' and 'label' keys."
                )

            text = str(row["text"]).strip()
            label = str(row["label"]).strip()

            if not text:
                raise ValueError(f"Line {line_number} has empty 'text'.")
            if not label:
                raise ValueError(f"Line {line_number} has empty 'label'.")

            items.append({"text": text, "label": label})

    if not items:
        raise ValueError("Dataset is empty.")

    return items


# ============================================================
# Dataset class
# ============================================================

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
        text = self.texts[idx]
        label_id = self.label_ids[idx]

        encoded = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )

        item = {k: v.squeeze(0) for k, v in encoded.items()}
        item["labels"] = torch.tensor(label_id, dtype=torch.long)
        return item


# ============================================================
# Training report model
# ============================================================

@dataclass
class TrainingContext:
    model_name_or_path: str
    local_files_only: bool
    device: str
    cuda_available: bool
    cuda_device_name: str | None
    python_version: str
    platform: str
    torch_version: str
    random_seed: int
    max_length: int
    epochs: int
    train_batch_size: int
    eval_batch_size: int
    learning_rate: float
    weight_decay: float
    warmup_ratio: float
    train_size: int
    val_size: int
    test_size: int


# ============================================================
# Metrics
# ============================================================

def compute_metrics(eval_pred: tuple[np.ndarray, np.ndarray]) -> dict[str, float]:
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    accuracy = accuracy_score(labels, predictions)
    macro_f1 = f1_score(labels, predictions, average="macro")

    return {
        "accuracy": float(accuracy),
        "macro_f1": float(macro_f1),
    }


# ============================================================
# Main training flow
# ============================================================

def main() -> None:
    set_seed(RANDOM_SEED)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Load supporting files
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    if not LABEL_TO_ID_PATH.exists():
        raise FileNotFoundError(f"label_to_id.json not found: {LABEL_TO_ID_PATH}")

    label_to_id: dict[str, int] = read_json(LABEL_TO_ID_PATH)

    if LABELS_PATH.exists():
        labels_list: list[str] = read_json(LABELS_PATH)
    else:
        # Fallback to keys from label_to_id, sorted by id
        labels_list = [k for k, _ in sorted(label_to_id.items(), key=lambda x: x[1])]

    thresholds = read_json(THRESHOLDS_PATH) if THRESHOLDS_PATH.exists() else DEFAULT_THRESHOLDS

    model_version = (
        MODEL_VERSION_PATH.read_text(encoding="utf-8").strip()
        if MODEL_VERSION_PATH.exists()
        else DEFAULT_MODEL_VERSION
    )

    # 2) Load dataset
    rows = read_jsonl(DATASET_PATH)

    # Validate labels
    unknown_labels = sorted({row["label"] for row in rows if row["label"] not in label_to_id})
    if unknown_labels:
        raise ValueError(
            f"Dataset contains labels not found in label_to_id.json: {unknown_labels}"
        )

    texts = [row["text"] for row in rows]
    labels = [row["label"] for row in rows]
    label_ids = [label_to_id[label] for label in labels]

    class_counts = Counter(labels)

    # 3) Save dataset report before training
    dataset_report = {
        "total_samples": len(rows),
        "labels_count": len(label_to_id),
        "class_counts": dict(sorted(class_counts.items())),
        "split_strategy": "stratified train/val/test split (80/10/10)",
        "random_seed": RANDOM_SEED,
    }
    write_json(DATASET_REPORT_PATH, dataset_report)

    # 4) Stratified 80/10/10 split
    # First split: 80% train, 20% temp
    train_texts, temp_texts, train_ids, temp_ids = train_test_split(
        texts,
        label_ids,
        test_size=0.20,
        random_state=RANDOM_SEED,
        shuffle=True,
        stratify=label_ids,
    )

    # Second split: temp -> 10% val, 10% test
    val_texts, test_texts, val_ids, test_ids = train_test_split(
        temp_texts,
        temp_ids,
        test_size=0.50,
        random_state=RANDOM_SEED,
        shuffle=True,
        stratify=temp_ids,
    )

    # 5) Tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_NAME_OR_PATH,
        local_files_only=LOCAL_FILES_ONLY,
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL_NAME_OR_PATH,
        num_labels=len(label_to_id),
        id2label={v: k for k, v in label_to_id.items()},
        label2id=label_to_id,
        local_files_only=LOCAL_FILES_ONLY,
    )

    # 6) Build datasets
    train_dataset = ComplaintDataset(train_texts, train_ids, tokenizer, MAX_LENGTH)
    val_dataset = ComplaintDataset(val_texts, val_ids, tokenizer, MAX_LENGTH)
    test_dataset = ComplaintDataset(test_texts, test_ids, tokenizer, MAX_LENGTH)

    # 7) Device context for reporting
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cuda_device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None

    training_context = TrainingContext(
        model_name_or_path=BASE_MODEL_NAME_OR_PATH,
        local_files_only=LOCAL_FILES_ONLY,
        device=device,
        cuda_available=torch.cuda.is_available(),
        cuda_device_name=cuda_device_name,
        python_version=platform.python_version(),
        platform=platform.platform(),
        torch_version=torch.__version__,
        random_seed=RANDOM_SEED,
        max_length=MAX_LENGTH,
        epochs=NUM_EPOCHS,
        train_batch_size=TRAIN_BATCH_SIZE,
        eval_batch_size=EVAL_BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        warmup_ratio=WARMUP_RATIO,
        train_size=len(train_dataset),
        val_size=len(val_dataset),
        test_size=len(test_dataset),
    )

    write_json(TRAINING_REPORT_PATH, asdict(training_context))

    # 8) Clean old checkpoints
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)

    # 9) Training arguments
    training_args = TrainingArguments(
        output_dir=str(CHECKPOINT_DIR),
        overwrite_output_dir=True,
        do_train=True,
        do_eval=True,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=TRAIN_BATCH_SIZE,
        per_device_eval_batch_size=EVAL_BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        warmup_ratio=WARMUP_RATIO,
        seed=RANDOM_SEED,
        report_to="none",
    )

    # 10) Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )

    # 11) Fine-tune
    trainer.train()

    # 12) Evaluate on validation and test sets
    val_metrics = trainer.evaluate(eval_dataset=val_dataset)
    test_metrics = trainer.evaluate(eval_dataset=test_dataset, metric_key_prefix="test")

    # 13) Save final model artifacts
    trainer.save_model(str(MODEL_DIR))
    tokenizer.save_pretrained(str(MODEL_DIR))

    # Keep label and threshold files beside the model
    write_json(LABEL_TO_ID_PATH, label_to_id)
    write_json(LABELS_PATH, labels_list)
    write_json(THRESHOLDS_PATH, thresholds)
    MODEL_VERSION_PATH.write_text(model_version, encoding="utf-8")

    # 14) Save combined metrics summary
    metrics_payload = {
        "modelVersion": model_version,
        "thresholds": thresholds,
        "validation": val_metrics,
        "test": test_metrics,
        "trainingContext": asdict(training_context),
    }
    write_json(METRICS_PATH, metrics_payload)

    print("Training completed successfully.")
    print(f"Model artifacts saved to: {MODEL_DIR}")
    print(json.dumps(metrics_payload, indent=2))


if __name__ == "__main__":
    main()