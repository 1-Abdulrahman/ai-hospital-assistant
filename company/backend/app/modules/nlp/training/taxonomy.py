from __future__ import annotations

ALLOWED_LABELS: tuple[str, ...] = (
    "cardiology",
    "dermatology",
    "orthopedics",
    "ent",
    "ophthalmology",
    "neurology",
    "gastroenterology",
    "pediatrics",
    "general_practice",
)

ALLOWED_SOURCE_TYPES: set[str] = {
    "gold_seed",
    "hard_negative",
    "public_mapped",
    "generated_variant",
}

TARGET_MIN_PER_LABEL = 50
TARGET_RECOMMENDED_PER_LABEL = 100

# Used for dataset review, hard negatives, and later clarification logic.
CONFUSION_MAP: dict[str, tuple[str, ...]] = {
    "cardiology": ("general_practice",),
    "dermatology": ("general_practice", "ophthalmology"),
    "orthopedics": ("general_practice", "neurology"),
    "ent": ("general_practice",),
    "ophthalmology": ("neurology", "general_practice", "dermatology"),
    "neurology": ("ophthalmology", "general_practice"),
    "gastroenterology": ("general_practice",),
    "pediatrics": ("general_practice", "gastroenterology"),
    "general_practice": (
        "cardiology",
        "dermatology",
        "orthopedics",
        "ent",
        "ophthalmology",
        "neurology",
        "gastroenterology",
        "pediatrics",
    ),
}

# Safe, controlled augmentation hooks for Phase 9.8B.
ALLOWED_AUGMENTATION_TAGS: set[str] = {
    "article_variants",
    "typo_variants",
    "prefix_variants",
}

ARTICLE_VARIANT_PHRASES: tuple[str, ...] = (
    "stomach ache",
    "sore throat",
    "headache",
    "fever",
    "skin rash",
)

TYPO_VARIANTS: dict[str, tuple[str, ...]] = {
    "stomach": ("stomache",),
    "nausea": ("nausia",),
    "vomiting": ("vomitting",),
    "throat": ("thorat",),
    "sore throat": ("sorethroat",),
    "dizziness": ("dizzyness",),
}

def assert_supported_label(label: str) -> None:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Unsupported label: {label}")

def assert_supported_source_type(source_type: str) -> None:
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {source_type}")

def validate_secondary_labels(primary_label: str, secondary_labels: list[str]) -> None:
    assert_supported_label(primary_label)
    allowed = set(CONFUSION_MAP.get(primary_label, ()))
    for candidate in secondary_labels:
        assert_supported_label(candidate)
        if candidate == primary_label:
            raise ValueError(
                f"secondary_labels cannot contain the primary label: {primary_label}"
            )
        if candidate not in allowed:
            raise ValueError(
                f"Secondary label '{candidate}' is not allowed for primary '{primary_label}'. "
                f"Allowed: {sorted(allowed)}"
            )

def validate_augmentation_tags(tags: list[str]) -> None:
    unknown = sorted(set(tags) - ALLOWED_AUGMENTATION_TAGS)
    if unknown:
        raise ValueError(f"Unsupported augmentation tags: {unknown}")