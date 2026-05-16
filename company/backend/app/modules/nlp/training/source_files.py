from __future__ import annotations

import re
from pathlib import Path

SOURCE_FILE_RE = re.compile(r"^(?P<prefix>\d{2})_(?P<name>.+)\.jsonl$")
GENERATED_VARIANTS_RE = re.compile(r"^(?P<prefix>\d{2})_generated_variants(?:_auto)?\.jsonl$")
AUTO_GENERATED_VARIANTS_RE = re.compile(r"^(?P<prefix>\d{2})_generated_variants_auto\.jsonl$")


def parse_source_prefix(path: Path) -> int | None:
    match = SOURCE_FILE_RE.match(path.name)
    if not match:
        return None
    return int(match.group("prefix"))


def is_generated_variants_file(path: Path) -> bool:
    return GENERATED_VARIANTS_RE.match(path.name) is not None


def is_auto_generated_variants_file(path: Path) -> bool:
    return AUTO_GENERATED_VARIANTS_RE.match(path.name) is not None


def list_training_source_files(
    sources_dir: Path,
    *,
    include_generated_variants: bool,
) -> list[Path]:
    files = sorted(p for p in sources_dir.glob("*.jsonl") if p.is_file())

    if include_generated_variants:
        return files

    return [p for p in files if not is_generated_variants_file(p)]


def _compute_next_generated_prefix(sources_dir: Path) -> int:
    manual_files = list_training_source_files(
        sources_dir,
        include_generated_variants=False,
    )
    prefixes = [parse_source_prefix(path) for path in manual_files]
    numeric_prefixes = [value for value in prefixes if value is not None]

    if not numeric_prefixes:
        return 0

    return max(numeric_prefixes) + 1


def resolve_generated_variants_output_path(sources_dir: Path) -> Path:
    """
    Rules:
    1. If an auto-generated variants file already exists, reuse it.
    2. Else if a legacy generated variants file exists, rename it once
       to the new auto filename using the next available prefix.
    3. Else create a new auto filename using the next available prefix.
    """
    all_jsonl_files = sorted(p for p in sources_dir.glob("*.jsonl") if p.is_file())

    auto_files = [p for p in all_jsonl_files if is_auto_generated_variants_file(p)]
    if len(auto_files) > 1:
        raise ValueError(
            f"Multiple auto generated-variants files found in {sources_dir}: "
            f"{[p.name for p in auto_files]}"
        )
    if len(auto_files) == 1:
        return auto_files[0]

    legacy_files = [
        p for p in all_jsonl_files
        if is_generated_variants_file(p) and not is_auto_generated_variants_file(p)
    ]
    if len(legacy_files) > 1:
        raise ValueError(
            f"Multiple legacy generated-variants files found in {sources_dir}: "
            f"{[p.name for p in legacy_files]}"
        )

    next_prefix = _compute_next_generated_prefix(sources_dir)
    target = sources_dir / f"{next_prefix:02d}_generated_variants_auto.jsonl"

    if len(legacy_files) == 1:
        legacy = legacy_files[0]
        if legacy != target:
            legacy.rename(target)
        return target

    return target