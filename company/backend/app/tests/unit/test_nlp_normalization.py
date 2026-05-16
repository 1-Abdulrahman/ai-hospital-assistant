from app.modules.nlp.normalization import ComplaintTextNormalizer


def build_normalizer() -> ComplaintTextNormalizer:
    return ComplaintTextNormalizer.from_assets()


def test_basic_cleanup_lowercases_and_removes_noise() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("  I HAVE!!! chest pain??  ")

    assert result.cleaned_text == "i have chest pain"
    assert result.corrected_text == "i have chest pain"


def test_symspell_corrects_common_typo() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("I feel nausia")

    assert result.corrected_text == "i feel nausea"


def test_symspell_splits_common_merged_word() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("I have sorethroat")

    assert result.corrected_text == "i have sore throat"


def test_semantic_guard_preserves_when() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("chest pain when walking")

    assert "when" in result.corrected_text
    assert "walking" in result.corrected_text


def test_semantic_guard_preserves_not() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("not dizzy but weak")

    assert "not" in result.corrected_text


def test_protected_terms_are_not_overcorrected() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("ent review")

    assert "ent" in result.corrected_text
    
def test_clean_sentence_is_not_overcorrected() -> None:
    normalizer = build_normalizer()

    result = normalizer.normalize("I have chest pain")

    assert result.cleaned_text == "i have chest pain"
    assert result.corrected_text == "i have chest pain"