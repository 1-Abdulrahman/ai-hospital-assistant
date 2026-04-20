from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from app.modules.nlp.normalization import basic_cleanup_text
from app.modules.nlp.training.source_files import list_training_source_files
from app.modules.nlp.training.taxonomy import (
    ALLOWED_LABELS,
    TARGET_MIN_PER_LABEL,
    TARGET_RECOMMENDED_PER_LABEL,
    assert_supported_label,
    assert_supported_source_type,
    validate_augmentation_tags,
    validate_secondary_labels,
)

BUILD_FILE = Path(__file__).resolve()
TRAINING_DIR = BUILD_FILE.parent
SOURCES_DIR = TRAINING_DIR / "sources"

OUTPUT_DATASET_PATH = TRAINING_DIR / "dataset.jsonl"
OUTPUT_MANIFEST_PATH = TRAINING_DIR / "dataset_manifest.json"
OUTPUT_BUILD_REPORT_PATH = TRAINING_DIR / "dataset_build_report.json"
OUTPUT_STABILITY_CASES_PATH = TRAINING_DIR / "stability_cases.jsonl"

TRACKED_SOURCE_TYPES: tuple[str, ...] = (
    "gold_seed",
    "hard_negative",
    "public_mapped",
    "generated_variant",
)

REVIEWED_SOURCE_TYPES: tuple[str, ...] = (
    "gold_seed",
    "hard_negative",
    "public_mapped",
)

PILOT_REVIEWED_THRESHOLD = 25
GOLD_TARGET_PER_LABEL = 100


@dataclass
class SourceRecord:
    text: str
    label: str
    source_type: str
    family_id: str
    reviewed: bool
    secondary_labels: list[str] = field(default_factory=list)
    notes: str | None = None
    include_in_stability_set: bool = False
    allow_augmentation: bool = False
    augmentation_tags: list[str] = field(default_factory=list)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_row(raw: dict[str, Any], source_file: str) -> SourceRecord:
    required = {"text", "label", "source_type", "family_id", "reviewed"}
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError(f"{source_file}: missing required fields: {missing}")

    record = SourceRecord(
        text=str(raw["text"]).strip(),
        label=str(raw["label"]).strip(),
        source_type=str(raw["source_type"]).strip(),
        family_id=str(raw["family_id"]).strip(),
        reviewed=bool(raw["reviewed"]),
        secondary_labels=[str(x).strip() for x in raw.get("secondary_labels", [])],
        notes=str(raw["notes"]).strip() if raw.get("notes") is not None else None,
        include_in_stability_set=bool(raw.get("include_in_stability_set", False)),
        allow_augmentation=bool(raw.get("allow_augmentation", False)),
        augmentation_tags=[str(x).strip() for x in raw.get("augmentation_tags", [])],
    )

    if not record.text:
        raise ValueError(f"{source_file}: text cannot be empty")
    if not record.family_id:
        raise ValueError(f"{source_file}: family_id cannot be empty")

    assert_supported_label(record.label)
    assert_supported_source_type(record.source_type)
    validate_secondary_labels(record.label, record.secondary_labels)
    validate_augmentation_tags(record.augmentation_tags)

    if not record.reviewed:
        raise ValueError(
            f"{source_file}: reviewed must be true before dataset build. "
            f"family_id={record.family_id}"
        )

    return record


def load_source_records() -> list[tuple[SourceRecord, str]]:
    source_files = list_training_source_files(
        SOURCES_DIR,
        include_generated_variants=True,
    )
    if not source_files:
        raise FileNotFoundError(f"No source JSONL files found under {SOURCES_DIR}")

    records: list[tuple[SourceRecord, str]] = []
    for path in source_files:
        for raw in read_jsonl(path):
            records.append((parse_row(raw, path.name), path.name))
    return records


def merge_records(records: list[tuple[SourceRecord, str]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    by_text_and_label: dict[tuple[str, str], dict[str, Any]] = {}
    label_by_text: dict[str, str] = {}
    family_groups: defaultdict[str, list[dict[str, str]]] = defaultdict(list)

    for record, source_file in records:
        cleaned_text = basic_cleanup_text(record.text)
        if not cleaned_text:
            raise ValueError(f"{source_file}: cleaned text is empty for family_id={record.family_id}")

        if cleaned_text in label_by_text and label_by_text[cleaned_text] != record.label:
            raise ValueError(
                f"Conflicting labels for the same cleaned complaint text: "
                f"'{cleaned_text}' -> '{label_by_text[cleaned_text]}' vs '{record.label}'"
            )

        label_by_text[cleaned_text] = record.label
        key = (cleaned_text, record.label)

        if key not in by_text_and_label:
            by_text_and_label[key] = {
                "text": cleaned_text,
                "label": record.label,
                "source_types": [record.source_type],
                "family_ids": [record.family_id],
                "secondary_labels": sorted(set(record.secondary_labels)),
                "notes": [record.notes] if record.notes else [],
                "include_in_stability_set": record.include_in_stability_set,
                "source_files": [source_file],
            }
        else:
            item = by_text_and_label[key]
            item["source_types"] = sorted(set(item["source_types"] + [record.source_type]))
            item["family_ids"] = sorted(set(item["family_ids"] + [record.family_id]))
            item["secondary_labels"] = sorted(
                set(item["secondary_labels"] + record.secondary_labels)
            )
            if record.notes:
                item["notes"] = sorted(set(item["notes"] + [record.notes]))
            item["include_in_stability_set"] = (
                item["include_in_stability_set"] or record.include_in_stability_set
            )
            item["source_files"] = sorted(set(item["source_files"] + [source_file]))

        family_groups[record.family_id].append(
            {
                "text": cleaned_text,
                "label": record.label,
                "family_id": record.family_id,
            }
        )

    manifest = sorted(
        by_text_and_label.values(),
        key=lambda item: (item["label"], item["text"]),
    )

    stability_cases: list[dict[str, str]] = []
    for family_id, rows in sorted(family_groups.items()):
        unique_rows = {
            (row["text"], row["label"], row["family_id"])
            for row in rows
        }
        if len(unique_rows) > 1:
            stability_cases.extend(
                {
                    "text": text,
                    "label": label,
                    "family_id": fam,
                }
                for text, label, fam in sorted(unique_rows)
            )

    # also include any manifest rows explicitly flagged even if family size is 1
    explicit = [
        {
            "text": item["text"],
            "label": item["label"],
            "family_id": item["family_ids"][0],
        }
        for item in manifest
        if item["include_in_stability_set"]
    ]

    combined = {
        (row["text"], row["label"], row["family_id"]): row
        for row in stability_cases + explicit
    }

    stability_cases = sorted(
        combined.values(),
        key=lambda row: (row["family_id"], row["label"], row["text"]),
    )

    return manifest, stability_cases

def _zero_label_counts() -> dict[str, int]:
    return {label: 0 for label in ALLOWED_LABELS}


def _label_source_type_matrix() -> dict[str, dict[str, int]]:
    return {
        label: {source_type: 0 for source_type in TRACKED_SOURCE_TYPES}
        for label in ALLOWED_LABELS
    }


def _label_family_sets() -> dict[str, set[str]]:
    return {label: set() for label in ALLOWED_LABELS}


def _reviewed_status_for_label(*, gold_seed: int, reviewed_total: int) -> str:
    if gold_seed >= GOLD_TARGET_PER_LABEL:
        return "gold_target_met"
    if reviewed_total >= TARGET_MIN_PER_LABEL:
        return "minimum_reviewed_met"
    if reviewed_total >= PILOT_REVIEWED_THRESHOLD:
        return "pilot_reviewed_met"
    return "needs_curation"


def _global_retrain_recommendation(
    *,
    generated_total: int,
    reviewed_total: int,
    labels_below_pilot_reviewed: list[str],
    labels_below_min_reviewed: list[str],
    labels_below_gold_target: list[str],
) -> dict[str, object]:
    if labels_below_pilot_reviewed:
        return {
            "status": "not_ready",
            "recommendation": "Continue gold_seed and hard_negative curation before any meaningful retrain.",
            "reason": "At least one label is still below the pilot reviewed threshold.",
        }

    if generated_total > reviewed_total:
        return {
            "status": "not_ready",
            "recommendation": "Continue reviewed curation before retraining. Generated variants still outnumber reviewed rows.",
            "reason": "generated_variant rows are dominating the dataset.",
        }

    if labels_below_min_reviewed:
        return {
            "status": "pilot_only",
            "recommendation": "You may run a pipeline or pilot retrain, but not a quality-signoff retrain yet.",
            "reason": "All labels cleared pilot reviewed threshold, but some are still below the minimum reviewed target.",
        }

    if labels_below_gold_target:
        return {
            "status": "minimum_ready",
            "recommendation": "You can run a serious retrain, but keep curating toward 100 gold per specialty.",
            "reason": "All labels cleared minimum reviewed threshold, but not all reached the gold target.",
        }

    return {
        "status": "gold_ready",
        "recommendation": "Gold target met for every specialty. Proceed with retraining and full evaluation.",
        "reason": "Every label reached the gold target.",
    }

def build_report(manifest: list[dict[str, Any]], source_records_count: int) -> dict[str, Any]:
    class_counts = Counter(item["label"] for item in manifest)
    source_type_counts = Counter(
        source_type
        for item in manifest
        for source_type in item["source_types"]
    )

    by_label_source_type = _label_source_type_matrix()
    family_sets_by_label = _label_family_sets()
    hard_negative_confusion_pair_counts: Counter[str] = Counter()

    for item in manifest:
        label = item["label"]
        source_types = set(item["source_types"])
        family_ids = set(item["family_ids"])
        secondary_labels = list(item.get("secondary_labels", []))

        for source_type in source_types:
            if source_type in TRACKED_SOURCE_TYPES:
                by_label_source_type[label][source_type] += 1

        for family_id in family_ids:
            family_sets_by_label[label].add(family_id)

        if "hard_negative" in source_types:
            for secondary in secondary_labels:
                pair_key = f"{label} -> {secondary}"
                hard_negative_confusion_pair_counts[pair_key] += 1

    label_breakdown: dict[str, dict[str, Any]] = {}
    labels_below_min_total = []
    labels_below_min_reviewed = []
    labels_below_pilot_reviewed = []
    labels_below_gold_target = []

    for label in ALLOWED_LABELS:
        total_rows = class_counts.get(label, 0)
        gold_seed_rows = by_label_source_type[label]["gold_seed"]
        hard_negative_rows = by_label_source_type[label]["hard_negative"]
        public_mapped_rows = by_label_source_type[label]["public_mapped"]
        generated_variant_rows = by_label_source_type[label]["generated_variant"]

        reviewed_total_rows = gold_seed_rows + hard_negative_rows + public_mapped_rows
        family_count = len(family_sets_by_label[label])

        generated_ratio = round(generated_variant_rows / total_rows, 4) if total_rows else 0.0
        reviewed_ratio = round(reviewed_total_rows / total_rows, 4) if total_rows else 0.0

        if total_rows < TARGET_MIN_PER_LABEL:
            labels_below_min_total.append(label)
        if reviewed_total_rows < TARGET_MIN_PER_LABEL:
            labels_below_min_reviewed.append(label)
        if reviewed_total_rows < PILOT_REVIEWED_THRESHOLD:
            labels_below_pilot_reviewed.append(label)
        if gold_seed_rows < GOLD_TARGET_PER_LABEL:
            labels_below_gold_target.append(label)

        label_breakdown[label] = {
            "total_rows": total_rows,
            "gold_seed_rows": gold_seed_rows,
            "hard_negative_rows": hard_negative_rows,
            "public_mapped_rows": public_mapped_rows,
            "generated_variant_rows": generated_variant_rows,
            "reviewed_total_rows": reviewed_total_rows,
            "family_count": family_count,
            "reviewed_ratio": reviewed_ratio,
            "generated_ratio": generated_ratio,
            "gap_to_minimum_reviewed_target": max(0, TARGET_MIN_PER_LABEL - reviewed_total_rows),
            "gap_to_pilot_reviewed_threshold": max(0, PILOT_REVIEWED_THRESHOLD - reviewed_total_rows),
            "gap_to_gold_target": max(0, GOLD_TARGET_PER_LABEL - gold_seed_rows),
            "status": _reviewed_status_for_label(
                gold_seed=gold_seed_rows,
                reviewed_total=reviewed_total_rows,
            ),
        }

    reviewed_total_dataset_rows = sum(source_type_counts.get(t, 0) for t in REVIEWED_SOURCE_TYPES)
    generated_total_dataset_rows = source_type_counts.get("generated_variant", 0)

    retrain_readiness = _global_retrain_recommendation(
        generated_total=generated_total_dataset_rows,
        reviewed_total=reviewed_total_dataset_rows,
        labels_below_pilot_reviewed=labels_below_pilot_reviewed,
        labels_below_min_reviewed=labels_below_min_reviewed,
        labels_below_gold_target=labels_below_gold_target,
    )

    return {
        "source_records_count": source_records_count,
        "deduped_records_count": len(manifest),
        "class_counts": dict(sorted(class_counts.items())),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "reviewed_total_dataset_rows": reviewed_total_dataset_rows,
        "generated_total_dataset_rows": generated_total_dataset_rows,
        "reviewed_vs_generated_ratio": round(
            reviewed_total_dataset_rows / generated_total_dataset_rows, 4
        ) if generated_total_dataset_rows else None,
        "below_min_target_labels": labels_below_min_total,
        "below_recommended_target_labels": [
            label
            for label in ALLOWED_LABELS
            if class_counts.get(label, 0) < TARGET_RECOMMENDED_PER_LABEL
        ],
        "below_min_reviewed_labels": labels_below_min_reviewed,
        "below_pilot_reviewed_labels": labels_below_pilot_reviewed,
        "below_gold_target_labels": labels_below_gold_target,
        "targets": {
            "minimum_per_label": TARGET_MIN_PER_LABEL,
            "recommended_per_label": TARGET_RECOMMENDED_PER_LABEL,
            "pilot_reviewed_per_label": PILOT_REVIEWED_THRESHOLD,
            "gold_seed_per_label": GOLD_TARGET_PER_LABEL,
        },
        "label_breakdown": label_breakdown,
        "hard_negative_confusion_pair_counts": dict(
            sorted(hard_negative_confusion_pair_counts.items())
        ),
        "retrain_readiness": retrain_readiness,
        "notes": [
            "dataset.jsonl is generated; do not edit it directly",
            "same cleaned text cannot exist with conflicting labels",
            "family_id is used for stability evaluation",
            "gold_seed_rows are the main quality target for long-term curation",
            "generated_variant rows should support, not dominate, the reviewed dataset",
        ],
    }


def main() -> None:
    records = load_source_records()
    manifest, stability_cases = merge_records(records)

    dataset_rows = [
        {
            "text": item["text"],
            "label": item["label"],
        }
        for item in manifest
    ]

    report = build_report(manifest, source_records_count=len(records))

    write_jsonl(OUTPUT_DATASET_PATH, dataset_rows)
    write_json(OUTPUT_MANIFEST_PATH, manifest)
    write_json(OUTPUT_BUILD_REPORT_PATH, report)
    write_jsonl(OUTPUT_STABILITY_CASES_PATH, stability_cases)

    print(f"Wrote dataset rows       -> {OUTPUT_DATASET_PATH}")
    print(f"Wrote dataset manifest   -> {OUTPUT_MANIFEST_PATH}")
    print(f"Wrote build report       -> {OUTPUT_BUILD_REPORT_PATH}")
    print(f"Wrote stability cases    -> {OUTPUT_STABILITY_CASES_PATH}")
    print(f"Deduped training rows    -> {len(dataset_rows)}")


if __name__ == "__main__":
    main()