from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.nlp.normalization import (
    BASE_DICTIONARY_PATH,
    OVERLAY_DICTIONARY_PATH,
    PROTECTED_TERMS_PATH,
    get_default_normalizer,
)


def _assets_present() -> bool:
    return (
        BASE_DICTIONARY_PATH.exists()
        and OVERLAY_DICTIONARY_PATH.exists()
        and PROTECTED_TERMS_PATH.exists()
    )


pytestmark = pytest.mark.skipif(
    not _assets_present(),
    reason="Real SymSpell asset files are not present.",
)


def test_real_assets_normalizer_loads() -> None:
    get_default_normalizer.cache_clear()
    normalizer = get_default_normalizer()

    assert normalizer.enabled is True
    assert normalizer.sym_spell is not None
    assert "base" in normalizer.dictionary_version.lower()


def test_real_assets_correct_common_typo() -> None:
    get_default_normalizer.cache_clear()
    normalizer = get_default_normalizer()

    result = normalizer.normalize("I feel nausia")
    assert result.cleaned_text == "i feel nausia"
    assert result.corrected_text == "i feel nausea"


def test_real_assets_split_merged_word() -> None:
    get_default_normalizer.cache_clear()
    normalizer = get_default_normalizer()

    result = normalizer.normalize("I have sorethroat")
    assert result.corrected_text == "i have sore throat"


def test_real_assets_do_not_overcorrect_clean_text() -> None:
    get_default_normalizer.cache_clear()
    normalizer = get_default_normalizer()

    result = normalizer.normalize("I have chest pain")
    assert result.cleaned_text == "i have chest pain"
    assert result.corrected_text == "i have chest pain"


def test_real_assets_preserve_meaningful_modifier() -> None:
    get_default_normalizer.cache_clear()
    normalizer = get_default_normalizer()

    result = normalizer.normalize("my chest pain gets worse when walking")
    assert "when" in result.corrected_text
    assert "walking" in result.corrected_text