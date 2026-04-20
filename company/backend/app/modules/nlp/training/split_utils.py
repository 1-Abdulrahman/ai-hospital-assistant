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
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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
    family_ids = sorted(set(item.get("family_ids", [])))
    if family_ids:
        return "|".join(family_ids)

    # Fallback only if manifest is missing family_ids
    return f"{item['label']}::{item['text']}"


def load_training_rows() -> list[TrainingRow]:
    """
    Prefer dataset_manifest.json because it contains family_ids.
    Fall back to dataset.jsonl if needed, but then every row becomes its own group.
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
    return dict(sorted(Counter(row.label for row in rows).items()))


def _safe_group_train_test_split(
    group_keys: list[str],
    group_labels: list[str],
    *,
    test_size: float,
    seed: int,
) -> tuple[list[str], list[str]]:
    """
    First try stratified split at group level.
    If sklearn refuses because a class is too small for the requested split,
    fall back to deterministic non-stratified split rather than crashing.
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
    if not path.exists():
        raise FileNotFoundError(f"Split manifest not found: {path}")
    return _read_json(path)


def apply_saved_group_split(
    rows: list[TrainingRow],
    split_manifest: dict[str, Any],
) -> dict[str, Any]:
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