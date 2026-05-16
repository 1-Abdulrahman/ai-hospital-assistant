from __future__ import annotations

from app.modules.nlp.training.build_dataset import merge_records, SourceRecord


def test_merge_records_dedupes_same_text_same_label() -> None:
    records = [
        (
            SourceRecord(
                text="I have a stomach ache",
                label="gastroenterology",
                source_type="gold_seed",
                family_id="fam-1",
                reviewed=True,
                secondary_labels=["general_practice"],
                notes="seed",
                include_in_stability_set=True,
                allow_augmentation=False,
                augmentation_tags=[],
            ),
            "00_gold_seed.jsonl",
        ),
        (
            SourceRecord(
                text="I have a stomach ache",
                label="gastroenterology",
                source_type="generated_variant",
                family_id="fam-1",
                reviewed=True,
                secondary_labels=["general_practice"],
                notes="generated",
                include_in_stability_set=True,
                allow_augmentation=False,
                augmentation_tags=[],
            ),
            "50_generated_variants.jsonl",
        ),
    ]

    manifest, stability_cases = merge_records(records)

    assert len(manifest) == 1
    assert manifest[0]["label"] == "gastroenterology"
    assert sorted(manifest[0]["source_types"]) == ["generated_variant", "gold_seed"]


def test_merge_records_rejects_same_text_conflicting_labels() -> None:
    records = [
        (
            SourceRecord(
                text="I have a stomach ache",
                label="gastroenterology",
                source_type="gold_seed",
                family_id="fam-1",
                reviewed=True,
                secondary_labels=["general_practice"],
                notes=None,
                include_in_stability_set=True,
                allow_augmentation=False,
                augmentation_tags=[],
            ),
            "00_gold_seed.jsonl",
        ),
        (
            SourceRecord(
                text="I have a stomach ache",
                label="general_practice",
                source_type="hard_negative",
                family_id="fam-2",
                reviewed=True,
                secondary_labels=["gastroenterology"],
                notes=None,
                include_in_stability_set=True,
                allow_augmentation=False,
                augmentation_tags=[],
            ),
            "10_hard_negatives.jsonl",
        ),
    ]

    try:
        merge_records(records)
        assert False, "Expected conflicting labels to raise ValueError"
    except ValueError as exc:
        assert "Conflicting labels" in str(exc)