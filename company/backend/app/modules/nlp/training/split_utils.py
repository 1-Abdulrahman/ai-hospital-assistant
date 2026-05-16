from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.model_selection import train_test_split

SPLIT_UTILS_FILE = Path(__file__).resolve()
TRAINING_DIR = SPLIT_UTILS_FILE.parent

DATASET_JSONL_PATH = TRAINING_DIR / "dataset.jsonl"
DATASET_MANIFEST_PATH = TRAINING_DIR / "dataset_manifest.json"
SPLIT_MANIFEST_PATH = TRAINING_DIR / "split_manifest.json"


@dataclass(frozen=True)
class TrainingRow:
    text: str
    label: str
    group_key: str
    sample_key: str


def _read_json(path: Path) -> Any:
    """Load and parse a JSON file.

    Args:
        path (Path): File path to read from.

    Returns:
        Any: Parsed JSON object from the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL (JSON Lines) file and return a list of parsed dictionaries.

    Each line in the file should contain a valid JSON object. Empty lines are skipped.
    Line numbers in error messages are 1-indexed for user convenience.

    Args:
        path (Path): File path to read from.

    Returns:
        list[dict[str, Any]]: List of parsed JSON objects, one per line.

    Raises:
        ValueError: If any line contains invalid JSON, with line number context.
    """
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name} line {line_number}: invalid JSON: {exc}") from exc
    return rows


def _build_group_key(item: dict[str, Any]) -> str:
    """Create a unique group key from an item's family IDs.

    Family-aware grouping ensures that rows from the same family (patient/source)
    stay together during train/val/test splits. This helps prevent data leakage
    where similar samples from the same family appear in multiple splits.

    Args:
        item (dict[str, Any]): Data item with optional 'family_ids' and fallback fields.

    Returns:
        str: Pipe-separated family IDs if present, otherwise fallback key using label and text.
    """
    family_ids = sorted(set(item.get("family_ids", [])))
    if family_ids:
        return "|".join(family_ids)

    # Fallback only if manifest is missing family_ids
    return f"{item['label']}::{item['text']}"


def load_training_rows() -> list[TrainingRow]:
    """Load training data from manifest or raw dataset file.

    This function prioritizes dataset_manifest.json (which includes family_ids for
    family-aware grouping) but gracefully falls back to dataset.jsonl if the manifest
    doesn't exist. When falling back, each row becomes its own group, which may
    result in different split characteristics.

    Returns:
        list[TrainingRow]: List of parsed training rows with family grouping information.

    Raises:
        FileNotFoundError: If neither manifest nor dataset file exists.
    """
    rows: list[TrainingRow] = []

    if DATASET_MANIFEST_PATH.exists():
        manifest = _read_json(DATASET_MANIFEST_PATH)
        for item in manifest:
            text = str(item["text"]).strip()
            label = str(item["label"]).strip()
            group_key = _build_group_key(item)
            sample_key = f"{label}::{group_key}::{text}"
            rows.append(
                TrainingRow(
                    text=text,
                    label=label,
                    group_key=group_key,
                    sample_key=sample_key,
                )
            )
        return rows

    if not DATASET_JSONL_PATH.exists():
        raise FileNotFoundError(
            f"Neither {DATASET_MANIFEST_PATH.name} nor {DATASET_JSONL_PATH.name} exists."
        )

    dataset_rows = _read_jsonl(DATASET_JSONL_PATH)
    for item in dataset_rows:
        text = str(item["text"]).strip()
        label = str(item["label"]).strip()
        group_key = f"{label}::{text}"
        sample_key = f"{label}::{group_key}::{text}"
        rows.append(
            TrainingRow(
                text=text,
                label=label,
                group_key=group_key,
                sample_key=sample_key,
            )
        )
    return rows


def _group_rows(rows: list[TrainingRow]) -> tuple[dict[str, list[TrainingRow]], dict[str, str]]:
    """Group training rows by their group key (family ID) with label consistency validation.

    All rows in the same group must have the same label. This prevents data integrity
    issues where a family group contains conflicting labels, which would corrupt
    the model's ability to learn consistent decision boundaries.

    Args:
        rows (list[TrainingRow]): Unsorted list of training rows.

    Returns:
        tuple: (by_group dict mapping group_key to list of rows, group_label dict mapping group_key to label).

    Raises:
        ValueError: If any group has rows with conflicting labels.
    """
    by_group: dict[str, list[TrainingRow]] = defaultdict(list)
    group_label: dict[str, str] = {}

    for row in rows:
        by_group[row.group_key].append(row)
        existing = group_label.get(row.group_key)
        if existing is None:
            group_label[row.group_key] = row.label
        elif existing != row.label:
            raise ValueError(
                f"Group {row.group_key} has conflicting labels: {existing} vs {row.label}"
            )

    return dict(by_group), group_label


def _class_counts(rows: list[TrainingRow]) -> dict[str, int]:
    """Count the number of rows for each label class.

    Useful for understanding class distribution and checking for imbalance in splits.

    Args:
        rows (list[TrainingRow]): List of training rows to count.

    Returns:
        dict[str, int]: Sorted dictionary mapping label to count of rows with that label.
    """
    return dict(sorted(Counter(row.label for row in rows).items()))


def _safe_group_train_test_split(
    group_keys: list[str],
    group_labels: list[str],
    *,
    test_size: float,
    seed: int,
) -> tuple[list[str], list[str]]:
    """Perform train/test split with graceful fallback when stratification is not possible.

    Stratified splitting ensures that class distribution is preserved across splits.
    However, if any class has fewer examples than required by the split parameters,
    sklearn raises ValueError. In such cases, we fall back to a simple random split
    to ensure the function never fails during dataset preparation.

    Args:
        group_keys (list[str]): Unique group identifiers to split.
        group_labels (list[str]): Corresponding label for each group (same length as group_keys).
        test_size (float): Proportion of data to assign to the test set (0.0 to 1.0).
        seed (int): Random seed for reproducibility.

    Returns:
        tuple[list[str], list[str]]: (train_group_keys, test_group_keys) both sorted.
    """
    try:
        train_keys, test_keys = train_test_split(
            group_keys,
            test_size=test_size,
            random_state=seed,
            shuffle=True,
            stratify=group_labels,
        )
    except ValueError:
        train_keys, test_keys = train_test_split(
            group_keys,
            test_size=test_size,
            random_state=seed,
            shuffle=True,
            stratify=None,
        )

    return sorted(train_keys), sorted(test_keys)


def split_rows_family_aware(
    rows: list[TrainingRow],
    *,
    seed: int = 42,
    train_fraction: float = 0.8,
    val_fraction: float = 0.1,
    test_fraction: float = 0.1,
) -> dict[str, Any]:
    """Split training data into train/val/test sets while keeping family groups together.

    This function ensures that all rows from the same family (same group_key) remain
    in the same split. This is critical for medical datasets where multiple samples
    may come from the same patient or source, and we want to prevent data leakage.

    The split is done at the group level first (stratified by label when possible),
    then expanded to include all rows in each group.

    Args:
        rows (list[TrainingRow]): All training rows to split.
        seed (int): Random seed for reproducible splits. Defaults to 42.
        train_fraction (float): Fraction of groups for training (default 0.8).
        val_fraction (float): Fraction of groups for validation (default 0.1).
        test_fraction (float): Fraction of groups for testing (default 0.1).

    Returns:
        dict[str, Any]: Dictionary containing split metadata and row assignments:
            - 'splitStrategy': Description of the splitting method
            - 'randomSeed': The seed used
            - 'train_rows': List of TrainingRow objects for training
            - 'val_rows': List of TrainingRow objects for validation
            - 'test_rows': List of TrainingRow objects for testing
            - 'summary': Aggregate statistics for each split

    Raises:
        ValueError: If split fractions don't sum to 1.0 or if no rows are provided.
    """
    if not rows:
        raise ValueError("No training rows provided.")

    total = train_fraction + val_fraction + test_fraction
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"Split fractions must sum to 1.0, got {train_fraction}+{val_fraction}+{test_fraction}={total}"
        )

    by_group, group_label = _group_rows(rows)
    all_group_keys = sorted(by_group.keys())
    all_group_labels = [group_label[group_key] for group_key in all_group_keys]

    train_group_keys, temp_group_keys = _safe_group_train_test_split(
        all_group_keys,
        all_group_labels,
        test_size=(1.0 - train_fraction),
        seed=seed,
    )

    temp_group_labels = [group_label[group_key] for group_key in temp_group_keys]
    test_fraction_of_temp = test_fraction / (val_fraction + test_fraction)

    val_group_keys, test_group_keys = _safe_group_train_test_split(
        temp_group_keys,
        temp_group_labels,
        test_size=test_fraction_of_temp,
        seed=seed,
    )

    def expand(group_keys: list[str]) -> list[TrainingRow]:
        expanded: list[TrainingRow] = []
        for group_key in group_keys:
            expanded.extend(by_group[group_key])
        return sorted(expanded, key=lambda row: (row.label, row.text, row.sample_key))

    train_rows = expand(train_group_keys)
    val_rows = expand(val_group_keys)
    test_rows = expand(test_group_keys)

    return {
        "splitStrategy": "family-aware group split by family_ids",
        "randomSeed": seed,
        "train_group_keys": train_group_keys,
        "val_group_keys": val_group_keys,
        "test_group_keys": test_group_keys,
        "train_rows": train_rows,
        "val_rows": val_rows,
        "test_rows": test_rows,
        "summary": {
            "train": {
                "rowCount": len(train_rows),
                "groupCount": len(train_group_keys),
                "classCounts": _class_counts(train_rows),
            },
            "val": {
                "rowCount": len(val_rows),
                "groupCount": len(val_group_keys),
                "classCounts": _class_counts(val_rows),
            },
            "test": {
                "rowCount": len(test_rows),
                "groupCount": len(test_group_keys),
                "classCounts": _class_counts(test_rows),
            },
        },
    }


def save_split_manifest(split_result: dict[str, Any], *, path: Path = SPLIT_MANIFEST_PATH) -> None:
    """Persist train/val/test split metadata to a JSON file for reproducible future loading.

    Saves only the metadata needed to reconstruct splits (group keys and counts),
    not the full row data, to keep file size manageable and enable reload of splits
    when new training data is added.

    Args:
        split_result (dict[str, Any]): Result dictionary from split_rows_family_aware().
        path (Path): Output file path. Defaults to SPLIT_MANIFEST_PATH.
    """
    payload = {
        "splitStrategy": split_result["splitStrategy"],
        "randomSeed": split_result["randomSeed"],
        "train": {
            "groupKeys": split_result["train_group_keys"],
            **split_result["summary"]["train"],
        },
        "val": {
            "groupKeys": split_result["val_group_keys"],
            **split_result["summary"]["val"],
        },
        "test": {
            "groupKeys": split_result["test_group_keys"],
            **split_result["summary"]["test"],
        },
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_split_manifest(path: Path = SPLIT_MANIFEST_PATH) -> dict[str, Any]:
    """Load previously saved split manifest metadata.

    Args:
        path (Path): File path to load from. Defaults to SPLIT_MANIFEST_PATH.

    Returns:
        dict[str, Any]: Split metadata dictionary.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Split manifest not found: {path}")
    return _read_json(path)


def apply_saved_group_split(
    rows: list[TrainingRow],
    split_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Apply a previously saved split to a new set of training rows.

    This enables reproducible splits when retraining with updated data. The split
    definition from the manifest is applied to the provided rows, raising an error
    if any expected group is missing from the new data.

    Args:
        rows (list[TrainingRow]): New training rows to apply the saved split to.
        split_manifest (dict[str, Any]): Split metadata loaded via load_split_manifest().

    Returns:
        dict[str, Any]: Split result with the same structure as split_rows_family_aware().

    Raises:
        ValueError: If saved split references group keys that don't exist in the new rows.
    """
    by_group, _group_label = _group_rows(rows)

    train_group_keys = split_manifest["train"]["groupKeys"]
    val_group_keys = split_manifest["val"]["groupKeys"]
    test_group_keys = split_manifest["test"]["groupKeys"]

    def expand(group_keys: list[str]) -> list[TrainingRow]:
        expanded: list[TrainingRow] = []
        missing: list[str] = []

        for group_key in group_keys:
            if group_key not in by_group:
                missing.append(group_key)
                continue
            expanded.extend(by_group[group_key])

        if missing:
            raise ValueError(
                f"Saved split references missing group keys: {missing[:5]}"
                + (" ..." if len(missing) > 5 else "")
            )

        return sorted(expanded, key=lambda row: (row.label, row.text, row.sample_key))

    train_rows = expand(train_group_keys)
    val_rows = expand(val_group_keys)
    test_rows = expand(test_group_keys)

    return {
        "splitStrategy": split_manifest.get(
            "splitStrategy",
            "family-aware group split by family_ids",
        ),
        "randomSeed": split_manifest.get("randomSeed", 42),
        "train_group_keys": train_group_keys,
        "val_group_keys": val_group_keys,
        "test_group_keys": test_group_keys,
        "train_rows": train_rows,
        "val_rows": val_rows,
        "test_rows": test_rows,
        "summary": {
            "train": {
                "rowCount": len(train_rows),
                "groupCount": len(train_group_keys),
                "classCounts": _class_counts(train_rows),
            },
            "val": {
                "rowCount": len(val_rows),
                "groupCount": len(val_group_keys),
                "classCounts": _class_counts(val_rows),
            },
            "test": {
                "rowCount": len(test_rows),
                "groupCount": len(test_group_keys),
                "classCounts": _class_counts(test_rows),
            },
        },
    }