from pydantic import BaseModel
from typing import Literal

class NlpCandidate(BaseModel):
    specialtyId: str
    confidence: float

class NlpPrediction(BaseModel):
    primarySpecialtyId: str | None
    topCandidates: list[NlpCandidate]
    needsClarification: bool
    reasonCode: Literal["OK", "NEEDS_CLARIFICATION", "NLP_PROCESSING_FAILED"]
    clarifierQuestion: str | None = None
    modelVersion: str | None = None