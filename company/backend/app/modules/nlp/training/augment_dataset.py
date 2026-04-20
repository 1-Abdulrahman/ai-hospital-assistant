from __future__ import annotations

import json
from pathlib import Path

from app.modules.nlp.normalization import basic_cleanup_text
from app.modules.nlp.training.source_files import (
    list_training_source_files,
    resolve_generated_variants_output_path,
)
from app.modules.nlp.training.taxonomy import (
    ARTICLE_VARIANT_PHRASES,
    TYPO_VARIANTS,
)

AUGMENT_FILE = Path(__file__).resolve()
TRAINING_DIR = AUGMENT_FILE.parent
SOURCES_DIR = TRAINING_DIR / "sources"


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate_article_variants(text: str) -> set[str]:
    variants: set[str] = set()
    for phrase in ARTICLE_VARIANT_PHRASES:
        if phrase in text:
            variants.add(text.replace(phrase, f"a {phrase}", 1))
            variants.add(text.replace(f"a {phrase}", phrase, 1))
    return {
        basic_cleanup_text(v)
        for v in variants
        if basic_cleanup_text(v) != basic_cleanup_text(text)
    }


def generate_typo_variants(text: str) -> set[str]:
    variants: set[str] = set()

    for canonical, typo_forms in TYPO_VARIANTS.items():
        if canonical in text:
            for typo in typo_forms:
                variants.add(text.replace(canonical, typo, 1))

    return {
        basic_cleanup_text(v)
        for v in variants
        if basic_cleanup_text(v) != basic_cleanup_text(text)
    }


def generate_prefix_variants(text: str) -> set[str]:
    variants: set[str] = set()
    lowered = basic_cleanup_text(text)

    if lowered.startswith("i have "):
        variants.add(lowered.removeprefix("i have ").strip())
    if lowered.startswith("i feel "):
        variants.add(lowered.removeprefix("i feel ").strip())
    if not lowered.startswith(("i have ", "i feel ", "my ")):
        variants.add(f"i have {lowered}")

    return {
        basic_cleanup_text(v)
        for v in variants
        if basic_cleanup_text(v) != lowered
    }


def build_generated_rows(source_rows: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for row in source_rows:
        if not row.get("reviewed", False):
            continue
        if not row.get("allow_augmentation", False):
            continue

        text = basic_cleanup_text(str(row["text"]))
        label = str(row["label"]).strip()
        family_id = str(row["family_id"]).strip()
        tags = list(row.get("augmentation_tags", []))

        variants: set[str] = set()

        if "article_variants" in tags:
            variants |= generate_article_variants(text)
        if "typo_variants" in tags:
            variants |= generate_typo_variants(text)
        if "prefix_variants" in tags:
            variants |= generate_prefix_variants(text)

        for variant in sorted(variants):
            key = (variant, label)
            if key in seen:
                continue
            seen.add(key)

            output.append(
                {
                    "text": variant,
                    "label": label,
                    "source_type": "generated_variant",
                    "family_id": family_id,
                    "secondary_labels": row.get("secondary_labels", []),
                    "reviewed": True,
                    "notes": f"auto-generated from {family_id}",
                    "include_in_stability_set": True,
                    "allow_augmentation": False,
                    "augmentation_tags": [],
                }
            )

    return output


def main() -> None:
    source_files = list_training_source_files(
        SOURCES_DIR,
        include_generated_variants=False,
    )
    source_rows: list[dict] = []

    for path in source_files:
        source_rows.extend(read_jsonl(path))

    generated = build_generated_rows(source_rows)
    output_path = resolve_generated_variants_output_path(SOURCES_DIR)

    write_jsonl(output_path, generated)

    print(f"Generated {len(generated)} variant rows -> {output_path.name}")


if __name__ == "__main__":
    main()