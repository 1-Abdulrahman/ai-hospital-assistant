"""Pydantic schemas for NLP prediction results.

This module defines lightweight data models used to serialize and
deserialize the output of the NLP specialty-prediction service.
These models are intended for API request/response bodies and
internal service-to-service messages.
"""

from pydantic import BaseModel
from typing import Literal


class NlpCandidate(BaseModel):
    """Single candidate specialty returned by the NLP model.

    Attributes:
        specialtyId: The identifier of the predicted specialty (string).
        confidence: Model confidence for this candidate (0.0 - 1.0).
    """

    # Identifier for the specialty the model predicted (e.g., "cardiology").
    specialtyId: str

    # Score the model assigned to this candidate; higher is better.
    confidence: float


class NlpPrediction(BaseModel):
    """Aggregate NLP prediction information.

    This model represents the NLP service's overall prediction for a
    single input. It includes the top candidates, an optional primary
    (best) specialty id, and metadata used to decide whether to ask the
    user a clarifying question.
    """

    # The top choice determined by the model. `None` if no clear winner.
    primarySpecialtyId: str | None

    # Ordered list of candidate specialties with their confidence scores.
    topCandidates: list[NlpCandidate]

    # Whether the system should ask the user for clarification.
    needsClarification: bool

    # Reason for the current prediction state. Use these exact literals
    # across services so downstream logic can branch reliably.
    reasonCode: Literal["OK", "NEEDS_CLARIFICATION", "NLP_PROCESSING_FAILED"]

    # Optional follow-up question when `needsClarification` is True.
    clarifierQuestion: str | None = None

    # Optional model version string (useful for debugging / auditing).
    modelVersion: str | None = None