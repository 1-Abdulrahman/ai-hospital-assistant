from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.modules.nlp.normalization import get_default_normalizer

from app.modules.nlp.clarification import (
    ClarificationQuickReply,
    build_clarification_prompt,
)

# ============================================================
# Paths and constants
# ============================================================

INFERENCE_FILE = Path(__file__).resolve()
BACKEND_ROOT = INFERENCE_FILE.parents[3]  # company/backend
APP_ROOT = BACKEND_ROOT / "app"
MODEL_DIR = APP_ROOT / "assets" / "nlp_models" / "distilbert-specialty"

LABEL_TO_ID_PATH = MODEL_DIR / "label_to_id.json"
LABELS_PATH = MODEL_DIR / "labels.json"
THRESHOLDS_PATH = MODEL_DIR / "thresholds.json"
MODEL_VERSION_PATH = MODEL_DIR / "model_version.txt"
METRICS_PATH = MODEL_DIR / "metrics.json"

DEFAULT_THRESHOLDS = {
    "minConfidence": 0.70,
    "ambiguityDelta": 0.10,
}

DEFAULT_MAX_LENGTH = 96
DEFAULT_MODEL_NAME = "distilbert-specialty"
DEFAULT_CLARIFIER_QUESTION = (
    "I am not fully confident about the specialty. "
    "Please choose the most suitable specialty from the suggested options."
)


# ============================================================
# DTOs
# ============================================================

@dataclass(frozen=True)
class NlpCandidate:
    specialty_id: str
    confidence: float


@dataclass(frozen=True)
class NlpPrediction:
    primary_specialty_id: str | None
    top_candidates: list[NlpCandidate]
    needs_clarification: bool
    reason_code: str
    clarifier_question: str | None
    clarification_key: str | None
    clarification_quick_replies: tuple
    model_name: str
    model_version: str | None
    input_summary: str
    original_input_summary: str
    cleaned_input_summary: str
    normalized_input_summary: str
    preprocessing_actions: tuple[str, ...]


# ============================================================
# Helpers
# ============================================================

def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None

def _safe_text_summary(text: str, max_len: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def _prepare_input_trace(text: str) -> tuple[str, str, str, str, tuple[str, ...]]:
    normalized_case = get_default_normalizer().normalize(text)

    original_input_summary = _safe_text_summary(text)
    cleaned_input_summary = _safe_text_summary(normalized_case.cleaned_text)
    normalized_input_summary = _safe_text_summary(normalized_case.corrected_text)
    preprocessing_actions = tuple(normalized_case.applied_rules)

    return (
        normalized_case.corrected_text,
        original_input_summary,
        cleaned_input_summary,
        normalized_input_summary,
        preprocessing_actions,
    )


def _normalize_text(text: str) -> str:
    return get_default_normalizer().normalize(text).corrected_text


def _safe_input_summary(text: str, max_len: int = 80) -> str:
    return _safe_text_summary(_normalize_text(text), max_len=max_len)


class NlpServiceError(Exception):
    pass


# ============================================================
# Main service
# ============================================================

class NlpService:
    def __init__(
        self,
        tokenizer: Any,
        model: Any,
        label_to_id: dict[str, int],
        id_to_label: dict[int, str],
        min_confidence: float,
        ambiguity_delta: float,
        model_name: str,
        model_version: str | None,
        device: torch.device,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.label_to_id = label_to_id
        self.id_to_label = id_to_label
        self.min_confidence = min_confidence
        self.ambiguity_delta = ambiguity_delta
        self.model_name = model_name
        self.model_version = model_version
        self.device = device
        self.max_length = max_length
        self.loaded_at_utc = datetime.now(timezone.utc)

    @classmethod
    def load_from_disk(
        cls,
        model_dir: Path = MODEL_DIR,
        local_files_only: bool | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> "NlpService":
        """
        Load the tokenizer, model, labels, thresholds, and model version
        from the local artifact directory.

        This must be called once at backend startup, not on every request.
        """
        if local_files_only is None:
            local_files_only = os.getenv("HF_LOCAL_FILES_ONLY", "0") == "1"

        if not model_dir.exists():
            raise NlpServiceError(f"Model directory does not exist: {model_dir}")

        if not LABEL_TO_ID_PATH.exists():
            raise NlpServiceError(f"Missing label_to_id.json: {LABEL_TO_ID_PATH}")

        label_to_id: dict[str, int] = _read_json(LABEL_TO_ID_PATH)
        id_to_label = {v: k for k, v in label_to_id.items()}

        thresholds = _read_json(THRESHOLDS_PATH) if THRESHOLDS_PATH.exists() else DEFAULT_THRESHOLDS
        min_confidence = float(thresholds.get("minConfidence", DEFAULT_THRESHOLDS["minConfidence"]))
        ambiguity_delta = float(thresholds.get("ambiguityDelta", DEFAULT_THRESHOLDS["ambiguityDelta"]))

        model_version = _safe_read_text(MODEL_VERSION_PATH)
        model_name = DEFAULT_MODEL_NAME

        tokenizer = AutoTokenizer.from_pretrained(
            str(model_dir),
            local_files_only=local_files_only,
        )

        model = AutoModelForSequenceClassification.from_pretrained(
            str(model_dir),
            local_files_only=local_files_only,
        )

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()

        return cls(
            tokenizer=tokenizer,
            model=model,
            label_to_id=label_to_id,
            id_to_label=id_to_label,
            min_confidence=min_confidence,
            ambiguity_delta=ambiguity_delta,
            model_name=model_name,
            model_version=model_version,
            device=device,
            max_length=max_length,
        )

    def status(self) -> dict[str, Any]:
        return {
            "available": True,
            "modelName": self.model_name,
            "modelVersion": self.model_version,
            "labelsCount": len(self.label_to_id),
            "thresholds": {
                "minConfidence": self.min_confidence,
                "ambiguityDelta": self.ambiguity_delta,
            },
            "device": str(self.device),
            "loadedAt": self.loaded_at_utc.isoformat(),
        }

    def classify(self, complaint_text: str) -> NlpPrediction:
        (
            normalized,
            original_input_summary,
            cleaned_input_summary,
            normalized_input_summary,
            preprocessing_actions,
        ) = _prepare_input_trace(complaint_text)

        input_summary = normalized_input_summary

        if not normalized:
            prompt = build_clarification_prompt(top_specialty_ids=[])

            return NlpPrediction(
                primary_specialty_id=None,
                top_candidates=[],
                needs_clarification=True,
                reason_code="NLP_PROCESSING_FAILED",
                clarifier_question=prompt.question,
                clarification_key=prompt.key,
                clarification_quick_replies=prompt.quick_replies,
                model_name=self.model_name,
                model_version=self.model_version,
                input_summary=input_summary,
                original_input_summary=original_input_summary,
                cleaned_input_summary=cleaned_input_summary,
                normalized_input_summary=normalized_input_summary,
                preprocessing_actions=preprocessing_actions,
            )

        encoded = self.tokenizer(
            normalized,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors="pt",
        )

        encoded = {key: value.to(self.device) for key, value in encoded.items()}

        with torch.no_grad():
            outputs = self.model(**encoded)
            logits = outputs.logits
            probabilities = F.softmax(logits, dim=-1).squeeze(0)

        scored_items: list[tuple[int, float]] = [
            (idx, float(probabilities[idx].item()))
            for idx in range(probabilities.shape[0])
        ]
        scored_items.sort(key=lambda item: (-item[1], item[0]))

        top3 = scored_items[:3]
        top_candidates = [
            NlpCandidate(
                specialty_id=self.id_to_label[idx],
                confidence=round(score, 6),
            )
            for idx, score in top3
        ]

        p1 = top3[0][1] if len(top3) >= 1 else 0.0
        p2 = top3[1][1] if len(top3) >= 2 else 0.0

        confident = p1 >= self.min_confidence and (p1 - p2) >= self.ambiguity_delta
        primary_specialty_id = self.id_to_label[top3[0][0]] if top3 else None

        if confident:
            return NlpPrediction(
                primary_specialty_id=primary_specialty_id,
                top_candidates=top_candidates,
                needs_clarification=False,
                reason_code="OK",
                clarifier_question=None,
                clarification_key=None,
                clarification_quick_replies=(),
                model_name=self.model_name,
                model_version=self.model_version,
                input_summary=input_summary,
                original_input_summary=original_input_summary,
                cleaned_input_summary=cleaned_input_summary,
                normalized_input_summary=normalized_input_summary,
                preprocessing_actions=preprocessing_actions,
            )
            
        prompt = build_clarification_prompt(
            top_specialty_ids=[candidate.specialty_id for candidate in top_candidates]
        )

        return NlpPrediction(
            primary_specialty_id=None,
            top_candidates=top_candidates,
            needs_clarification=True,
            reason_code="NEEDS_CLARIFICATION",
            clarifier_question=prompt.question,
            clarification_key=prompt.key,
            clarification_quick_replies=prompt.quick_replies,
            model_name=self.model_name,
            model_version=self.model_version,
            input_summary=input_summary,
            original_input_summary=original_input_summary,
            cleaned_input_summary=cleaned_input_summary,
            normalized_input_summary=normalized_input_summary,
            preprocessing_actions=preprocessing_actions,
        )

# ============================================================
# Safe wrapper for startup fallback
# ============================================================

def try_load_nlp_service(
    model_dir: Path = MODEL_DIR,
    local_files_only: bool | None = None,
) -> tuple[NlpService | None, dict[str, Any]]:
    try:
        service = NlpService.load_from_disk(
            model_dir=model_dir,
            local_files_only=local_files_only,
        )
        return service, {
            "available": True,
            "reasonCode": "OK",
            "message": "NLP model loaded successfully.",
            "modelName": service.model_name,
            "modelVersion": service.model_version,
            "loadedAt": service.loaded_at_utc.isoformat(),
        }
    except Exception as exc:
        return None, {
            "available": False,
            "reasonCode": "NLP_PROCESSING_FAILED",
            "message": "NLP model could not be loaded. Manual specialty selection will be used.",
            "details": str(exc),
        }