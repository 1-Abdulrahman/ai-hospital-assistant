from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from itertools import zip_longest
from pathlib import Path

from symspellpy import SymSpell

NORMALIZATION_FILE = Path(__file__).resolve()
NLP_DIR = NORMALIZATION_FILE.parent
ASSETS_DIR = NLP_DIR / "assets" / "symspell"

BASE_DICTIONARY_PATH = ASSETS_DIR / "frequency_dictionary_en_82_765.txt"
OVERLAY_DICTIONARY_PATH = ASSETS_DIR / "medical_overlay_dictionary_v1.txt"
PROTECTED_TERMS_PATH = ASSETS_DIR / "protected_terms_v1.txt"
AUDIT_CASES_PATH = ASSETS_DIR / "normalization_audit_cases_v1.json"

WHITESPACE_RE = re.compile(r"\s+")
NOISE_RE = re.compile(r"[^\w\s/\-']")
SLASH_RE = re.compile(r"\s*/\s*")

SEMANTIC_GUARD_TOKENS = {
    "not",
    "no",
    "without",
    "after",
    "before",
    "during",
    "when",
    "while",
    "since",
    "sudden",
    "suddenly",
    "chronic",
    "acute",
    "severe",
    "mild",
    "worse",
    "better",
}

STABLE_SUPPORT_TOKENS = {
    "i",
    "a",
    "an",
    "have",
    "has",
    "had",
    "feel",
    "feeling",
    "my",
    "hurt",
    "hurts",
    "and",
    "with",
    "am",
    "is",
    "are",
    "it",
    "get",
    "gets",
}


@dataclass(frozen=True)
class NormalizedComplaint:
    raw_text: str
    cleaned_text: str
    corrected_text: str
    applied_rules: tuple[str, ...]


def _read_terms_file(path: Path) -> set[str]:
    if not path.exists():
        return set()

    values: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lower()
        if not line or line.startswith("#"):
            continue
        values.add(line)
    return values


def _read_frequency_terms(path: Path) -> set[str]:
    if not path.exists():
        return set()

    values: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lower()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if not parts:
            continue

        values.add(parts[0])
    return values


def _basic_cleanup(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = cleaned.strip().lower()
    cleaned = SLASH_RE.sub(" / ", cleaned)
    cleaned = NOISE_RE.sub(" ", cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


class ComplaintTextNormalizer:
    def __init__(
        self,
        *,
        sym_spell: SymSpell | None,
        protected_terms: set[str],
        known_terms: set[str],
        dictionary_version: str,
        enabled: bool,
    ) -> None:
        self.sym_spell = sym_spell
        self.protected_terms = protected_terms
        self.known_terms = known_terms
        self.dictionary_version = dictionary_version
        self.enabled = enabled

    @classmethod
    def from_assets(cls) -> "ComplaintTextNormalizer":
        if not BASE_DICTIONARY_PATH.exists():
            return cls(
                sym_spell=None,
                protected_terms=set(),
                known_terms=set(),
                dictionary_version="missing-base-dictionary",
                enabled=False,
            )

        protected_terms = _read_terms_file(PROTECTED_TERMS_PATH)

        sym_spell = SymSpell(
            max_dictionary_edit_distance=2,
            prefix_length=7,
            count_threshold=1,
        )

        loaded_base = sym_spell.load_dictionary(
            str(BASE_DICTIONARY_PATH),
            term_index=0,
            count_index=1,
            separator=" ",
        )

        if not loaded_base:
            return cls(
                sym_spell=None,
                protected_terms=protected_terms,
                known_terms=set(),
                dictionary_version="base-dictionary-load-failed",
                enabled=False,
            )

        base_terms = _read_frequency_terms(BASE_DICTIONARY_PATH)
        overlay_terms = set()

        if OVERLAY_DICTIONARY_PATH.exists():
            for raw_line in OVERLAY_DICTIONARY_PATH.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip().lower()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                term = parts[0]
                count = int(parts[1])
                sym_spell.create_dictionary_entry(term, count)
                overlay_terms.add(term)

        for term in protected_terms:
            sym_spell.create_dictionary_entry(term, 10_000_000)

        known_terms = base_terms | overlay_terms | protected_terms

        return cls(
            sym_spell=sym_spell,
            protected_terms=protected_terms,
            known_terms=known_terms,
            dictionary_version="symspell-base-en-plus-medical-overlay-v1",
            enabled=True,
        )

    def normalize(self, text: str) -> NormalizedComplaint:
        cleaned = _basic_cleanup(text)
        applied_rules: list[str] = []

        if cleaned != text.strip():
            applied_rules.append("basic_cleanup")

        if not cleaned or not self.enabled or self.sym_spell is None:
            return NormalizedComplaint(
                raw_text=text,
                cleaned_text=cleaned,
                corrected_text=cleaned,
                applied_rules=tuple(applied_rules),
            )

        if not self._needs_spelling_help(cleaned):
            return NormalizedComplaint(
                raw_text=text,
                cleaned_text=cleaned,
                corrected_text=cleaned,
                applied_rules=tuple(applied_rules),
            )

        suggestions = self.sym_spell.lookup_compound(
            cleaned,
            max_edit_distance=2,
            ignore_non_words=True,
            ignore_term_with_digits=True,
            transfer_casing=False,
        )

        if not suggestions:
            return NormalizedComplaint(
                raw_text=text,
                cleaned_text=cleaned,
                corrected_text=cleaned,
                applied_rules=tuple(applied_rules),
            )

        candidate = WHITESPACE_RE.sub(" ", suggestions[0].term).strip()

        if candidate and candidate != cleaned and self._accept_correction(cleaned, candidate):
            applied_rules.append("symspell_lookup_compound")
            return NormalizedComplaint(
                raw_text=text,
                cleaned_text=cleaned,
                corrected_text=candidate,
                applied_rules=tuple(applied_rules),
            )

        return NormalizedComplaint(
            raw_text=text,
            cleaned_text=cleaned,
            corrected_text=cleaned,
            applied_rules=tuple(applied_rules),
        )

    def _needs_spelling_help(self, text: str) -> bool:
        tokens = text.split()
        if not tokens:
            return False

        for token in tokens:
            if token not in self.known_terms:
                return True

        return False

    def _unknown_token_count(self, text: str) -> int:
        return sum(1 for token in text.split() if token not in self.known_terms)

    def _accept_correction(self, original: str, candidate: str) -> bool:
        original_tokens = original.split()
        candidate_tokens = candidate.split()

        if not original_tokens:
            return False

        original_set = set(original_tokens)
        candidate_set = set(candidate_tokens)

        for token in self.protected_terms:
            if token in original_set and token not in candidate_set:
                return False

        for token in SEMANTIC_GUARD_TOKENS:
            if token in original_set and token not in candidate_set:
                return False

        for token in STABLE_SUPPORT_TOKENS:
            if token in original_set and token not in candidate_set:
                return False

        original_unknown = self._unknown_token_count(original)
        candidate_unknown = self._unknown_token_count(candidate)

        if candidate_unknown >= original_unknown:
            return False

        changed_positions = sum(
            1
            for left, right in zip_longest(original_tokens, candidate_tokens, fillvalue="")
            if left != right
        )

        max_allowed_changes = max(2, math.ceil(len(original_tokens) * 0.40))
        if changed_positions > max_allowed_changes:
            return False

        if abs(len(candidate_tokens) - len(original_tokens)) > 2:
            return False

        return True


@lru_cache(maxsize=1)
def get_default_normalizer() -> ComplaintTextNormalizer:
    return ComplaintTextNormalizer.from_assets()


def load_normalization_audit_cases() -> list[dict[str, str]]:
    if not AUDIT_CASES_PATH.exists():
        return []
    return json.loads(AUDIT_CASES_PATH.read_text(encoding="utf-8"))