from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ClarificationQuickReply:
    label: str
    value: str
    action: str | None = None


@dataclass(frozen=True)
class ClarificationPrompt:
    key: str
    question: str
    quick_replies: tuple[ClarificationQuickReply, ...]


def build_clarification_prompt(*, top_specialty_ids: Sequence[str]) -> ClarificationPrompt:
    """
    MVP simplified clarification strategy:
    - do not expose specialty-name quick replies
    - do not generate symptom-specific question variants
    - show only one helper option so user can type more detail
    - keep specialty selection list as the explicit manual fallback
    """
    return ClarificationPrompt(
        key="free-text-clarification-only",
        question=(
            "I am not fully confident yet. Add more detail if you want, "
            "or choose one of the suggested specialties to continue."
        ),
        quick_replies=(
            ClarificationQuickReply(
                label="I will give more details",
                value="I will give more details.",
                action="PROMPT_FOR_TEXT",
            ),
        ),
    )