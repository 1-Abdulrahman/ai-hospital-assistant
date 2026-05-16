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
    """Read a JSONL (JSON Lines) file and return a list of parsed dictionaries.

    Each line should contain a valid JSON object. Empty lines are silently ignored.

    Args:
        path (Path): File path to read from.

    Returns:
        list[dict]: List of parsed JSON objects, one per line.
    """
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write a list of dictionaries to a JSONL (JSON Lines) file.

    One JSON object per line. Creates parent directories if needed.

    Args:
        path (Path): Output file path.
        rows (list[dict]): List of dictionaries to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate_article_variants(text: str) -> set[str]:
    """Generate text variants by adding or removing indefinite articles (a/an).

    For example, 'pain in chest' could become 'a pain in chest', helping the model
    learn to recognize the same concept even when articles are used inconsistently.

    Args:
        text (str): Input text to augment.

    Returns:
        set[str]: Set of unique cleaned variants (excluding the original).
    """
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
    """Generate text variants by introducing common Arabic/medical terminology typos.

    Real-world user input often contains misspellings. This augmentation helps the
    model learn to recognize symptoms and complaints despite spelling variations.

    Uses predefined canonical->typo mappings from taxonomy.

    Args:
        text (str): Input text to augment.

    Returns:
        set[str]: Set of unique cleaned variants with typos (excluding the original).
    """
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
    """Generate text variants by altering common sentence openers.

    Real user queries often use phrases like 'I have...', 'I feel...', 'My...' to
    express the same underlying symptoms. This augmentation helps the model learn
    that the core complaint matters more than the phrasing.

    For example, 'headache and fever' can be expanded to 'I have headache and fever'.

    Args:
        text (str): Input text to augment.

    Returns:
        set[str]: Set of unique cleaned variants with different prefixes (excluding the original).
    """
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
    """Generate augmented training rows from reviewed source data.

    For each source row marked with allow_augmentation=True and augmentation_tags,
    applies selected variant generators and creates new SourceRecord-like rows.
    
    De-duplication ensures that if a variant already exists with the same label,
    it's not added twice. Generated rows are marked for stability testing and
    with a note linking them to the original family_id.

    Args:
        source_rows (list[dict]): Source rows loaded from JSONL files.

    Returns:
        list[dict]: New rows with source_type='generated_variant', ready to be merged
            into the dataset.
    """
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
    """Generate all requested text variants from augmentation-enabled source rows.

    Pipeline:
    1. Load all source JSONL files (excluding previously generated variants)
    2. Filter for rows marked with allow_augmentation=True
    3. Apply selected augmentation strategies (based on augmentation_tags)
    4. Deduplicate variants and output as JSONL
    5. Output is ready to be merged into the dataset in the next build step
    """
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