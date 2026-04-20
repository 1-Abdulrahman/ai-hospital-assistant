from __future__ import annotations

from pathlib import Path

from app.modules.nlp.training.source_files import (
    list_training_source_files,
    resolve_generated_variants_output_path,
)


def test_resolve_generated_output_uses_next_prefix(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    (sources_dir / "00_gold_seed.jsonl").write_text("", encoding="utf-8")
    (sources_dir / "10_hard_negatives.jsonl").write_text("", encoding="utf-8")
    (sources_dir / "11_hard_negatives_batch_v2.jsonl").write_text("", encoding="utf-8")

    output_path = resolve_generated_variants_output_path(sources_dir)

    assert output_path.name == "12_generated_variants_auto.jsonl"


def test_resolve_generated_output_migrates_legacy_file(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    (sources_dir / "00_gold_seed.jsonl").write_text("", encoding="utf-8")
    (sources_dir / "10_hard_negatives.jsonl").write_text("", encoding="utf-8")
    legacy = sources_dir / "50_generated_variants.jsonl"
    legacy.write_text('{"text":"x","label":"general_practice"}\n', encoding="utf-8")

    output_path = resolve_generated_variants_output_path(sources_dir)

    assert output_path.name == "11_generated_variants_auto.jsonl"
    assert output_path.exists()
    assert not legacy.exists()


def test_list_training_source_files_excludes_generated_variants_when_requested(
    tmp_path: Path,
) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    manual = sources_dir / "00_gold_seed.jsonl"
    generated = sources_dir / "11_generated_variants_auto.jsonl"

    manual.write_text("", encoding="utf-8")
    generated.write_text("", encoding="utf-8")

    files = list_training_source_files(
        sources_dir,
        include_generated_variants=False,
    )

    assert [path.name for path in files] == ["00_gold_seed.jsonl"]