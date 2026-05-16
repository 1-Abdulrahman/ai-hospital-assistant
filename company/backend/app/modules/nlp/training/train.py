from __future__ import annotations

"""Training entrypoint for fine-tuning an NLP classification model.

This module provides a small training pipeline that:
- reads a labelled JSONL dataset
- prepares family-aware train/val/test splits
- tokenizes inputs and fine-tunes a Hugging Face model
- saves model artifacts and metrics

The file is intentionally self-contained for clarity and repeatability
within the project's training tooling.
"""

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
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)
from app.modules.nlp.training.split_utils import (
    SPLIT_MANIFEST_PATH,
    load_training_rows,
    save_split_manifest,
    split_rows_family_aware,
)

# ============================================================
# Configuration
# ============================================================

RANDOM_SEED = int(os.getenv("NLP_RANDOM_SEED", "42"))
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
    """Set random seeds for Python, NumPy, and PyTorch.

    This helps ensure reproducible training runs across CPU/GPU setups.

    Args:
        seed: Integer seed to apply to all random generators.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    # If CUDA is available, set the CUDA RNGs as well for full reproducibility
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ============================================================
# File helpers
# ============================================================

def read_json(path: Path) -> Any:
    """Read a JSON file and return the parsed object.

    Args:
        path: Path to a JSON file.

    Returns:
        The Python object parsed from the JSON file.
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    """Write a Python object to a JSON file, creating parent dirs.

    Args:
        path: Destination file path to write JSON to.
        payload: JSON-serializable Python object to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_jsonl(path: Path) -> list[dict[str, str]]:
    """Read a newline-delimited JSON (JSONL) dataset with validation.

    Each line must be a JSON object containing `text` and `label` keys.
    Raises helpful ValueErrors when encountering malformed lines so the
    caller can fix dataset issues before training.

    Args:
        path: Path to a `.jsonl` file.

    Returns:
        A list of dicts with normalized `text` and `label` strings.
    """
    items: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                # Provide line number context to make debugging easier
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

def prepare_family_aware_splits(
    random_seed: int,
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str], dict[str, Any]]:
    """Prepare family-aware train/validation/test splits.

    This function uses the project's `split_utils` to create splits that keep
    related samples (by family id) together so that evaluations better reflect
    generalization to unseen families.

    Args:
        random_seed: Seed used to make the splitting deterministic.

    Returns:
        Tuple containing train_texts, train_labels, val_texts, val_labels,
        test_texts, test_labels, and a summary dict describing the split.
    """
    rows = load_training_rows()

    # Perform the family-aware split and persist a manifest for reproducibility
    split_result = split_rows_family_aware(rows, seed=random_seed)
    save_split_manifest(split_result, path=SPLIT_MANIFEST_PATH)

    train_rows = split_result["train_rows"]
    val_rows = split_result["val_rows"]
    test_rows = split_result["test_rows"]

    # Convert row objects into plain lists for the Dataset class
    train_texts = [row.text for row in train_rows]
    train_labels = [row.label for row in train_rows]

    val_texts = [row.text for row in val_rows]
    val_labels = [row.label for row in val_rows]

    test_texts = [row.text for row in test_rows]
    test_labels = [row.label for row in test_rows]

    return (
        train_texts,
        train_labels,
        val_texts,
        val_labels,
        test_texts,
        test_labels,
        split_result["summary"],
    )


# ============================================================
# Dataset class
# ============================================================

class ComplaintDataset(Dataset):
    """PyTorch Dataset wrapping tokenized texts and label ids.

    This dataset returns tokenized inputs compatible with Hugging Face
    `Trainer` (i.e., tensors for input_ids, attention_mask, etc.) along with
    a `labels` tensor for supervised training.
    """
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
        """Return a single tokenized example with label tensor.

        Args:
            idx: Index of the sample to retrieve.

        Returns:
            A dict mapping input names (e.g., `input_ids`) to tensors, and a
            `labels` tensor for the target class id.
        """
        text = self.texts[idx]
        label_id = self.label_ids[idx]

        encoded = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )

        # The tokenizer returns batch tensors; squeeze to get single-example tensors
        item = {k: v.squeeze(0) for k, v in encoded.items()}
        item["labels"] = torch.tensor(label_id, dtype=torch.long)
        return item


# ============================================================
# Training report model
# ============================================================

@dataclass
class TrainingContext:
    """Lightweight record of training hyperparameters and environment.

    This dataclass is serialized into `training_report.json` to help with
    experiment tracking and reproducibility.
    """
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
    """Compute evaluation metrics used for model selection.

    The Trainer expects a function that takes `(logits, labels)` and returns
    a dict of scalar metrics. We compute accuracy and macro-averaged F1 to
    handle class imbalance in a multi-class setting.
    """
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
    """Main training routine.

    This function orchestrates loading configuration and data, preparing
    splits, tokenizing, training with Hugging Face `Trainer`, evaluating, and
    saving artifacts such as the final model, tokenizer, and metrics.
    """
    # Reproducibility and output dirs
    set_seed(RANDOM_SEED)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Load supporting files and configuration
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    if not LABEL_TO_ID_PATH.exists():
        raise FileNotFoundError(f"label_to_id.json not found: {LABEL_TO_ID_PATH}")

    label_to_id: dict[str, int] = read_json(LABEL_TO_ID_PATH)

    # Labels file is optional; if missing infer labels from label_to_id mapping
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

    # 2) Load and validate dataset
    rows = read_jsonl(DATASET_PATH)

    # Ensure every label in the dataset is recognized by the label map
    unknown_labels = sorted({row["label"] for row in rows if row["label"] not in label_to_id})
    if unknown_labels:
        raise ValueError(
            f"Dataset contains labels not found in label_to_id.json: {unknown_labels}"
        )

    labels = [row["label"] for row in rows]
    class_counts = Counter(labels)

    # 3) Create family-aware splits to avoid leakage between related samples
    (
        train_texts,
        train_labels,
        val_texts,
        val_labels,
        test_texts,
        test_labels,
        split_summary,
    ) = prepare_family_aware_splits(random_seed=RANDOM_SEED)

    # Convert labels to integer ids for model training
    train_ids = [label_to_id[label] for label in train_labels]
    val_ids = [label_to_id[label] for label in val_labels]
    test_ids = [label_to_id[label] for label in test_labels]

    # 4) Save lightweight dataset report to aid debugging and reproducibility
    dataset_report = {
        "total_samples": len(rows),
        "labels_count": len(label_to_id),
        "class_counts": dict(sorted(class_counts.items())),
        "split_strategy": "family-aware group split by family_ids",
        "random_seed": RANDOM_SEED,
        "split_summary": split_summary,
        "split_manifest_path": str(SPLIT_MANIFEST_PATH),
    }
    write_json(DATASET_REPORT_PATH, dataset_report)

    # 5) Tokenizer and model: leverage `local_files_only` for offline usage
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

    # 6) Build PyTorch datasets used by the Trainer
    train_dataset = ComplaintDataset(train_texts, train_ids, tokenizer, MAX_LENGTH)
    val_dataset = ComplaintDataset(val_texts, val_ids, tokenizer, MAX_LENGTH)
    test_dataset = ComplaintDataset(test_texts, test_ids, tokenizer, MAX_LENGTH)

    # 7) Record environment and hyperparameters for the training report
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

    # 8) Clean any previous checkpoints to ensure a fresh run
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)

    # 9) Training arguments for Hugging Face Trainer
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

    # 10) Create Trainer and attach metric computation
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )

    # 11) Run training loop
    trainer.train()

    # 12) Evaluate on validation and test splits
    val_metrics = trainer.evaluate(eval_dataset=val_dataset)
    test_metrics = trainer.evaluate(eval_dataset=test_dataset, metric_key_prefix="test")

    # 13) Persist final model and tokenizer to the model directory
    trainer.save_model(str(MODEL_DIR))
    tokenizer.save_pretrained(str(MODEL_DIR))

    # Keep label and threshold files beside the model for serving
    write_json(LABEL_TO_ID_PATH, label_to_id)
    write_json(LABELS_PATH, labels_list)
    write_json(THRESHOLDS_PATH, thresholds)
    MODEL_VERSION_PATH.write_text(model_version, encoding="utf-8")

    # 14) Save a combined metrics summary including training context
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