from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ClarificationQuickReply:
    """Represents a quick reply option for user clarification prompts.
    
    Attributes:
        label: The text displayed to the user for this option.
        value: The value submitted when the user selects this option.
        action: Optional action type to trigger specific behavior (e.g., "PROMPT_FOR_TEXT").
    """
    label: str
    value: str
    action: str | None = None


@dataclass(frozen=True)
class ClarificationPrompt:
    """Defines a clarification prompt to ask users for additional context.
    
    This is used when the NLP system needs more information to confidently 
    determine the appropriate medical specialty or provide better guidance.
    
    Attributes:
        key: Unique identifier for this clarification prompt type.
        question: The question text presented to the user.
        quick_replies: A tuple of quick reply options available to the user.
    """
    key: str
    question: str
    quick_replies: tuple[ClarificationQuickReply, ...]


def build_clarification_prompt(*, top_specialty_ids: Sequence[str]) -> ClarificationPrompt:
    """Build a simplified clarification prompt for MVP phase.
    
    Creates a clarification prompt asking the user for additional details when 
    the NLP system is not confident enough to determine the appropriate medical specialty.
    
    This MVP implementation uses a simplified strategy:
    - No specialty name quick replies are exposed to avoid confusion
    - No symptom-specific question variants are generated
    - Only one helper option is shown to encourage users to provide more detail
    - Specialty selection remains as an explicit manual fallback
    
    Args:
        top_specialty_ids: Sequence of specialty IDs that could be relevant
                          (currently not used in MVP, reserved for future enhancement).
    
    Returns:
        ClarificationPrompt: A prompt object with question text and quick reply options.
    """
    return ClarificationPrompt(
        key="free-text-clarification-only",
        question=(
            "I am not fully confident yet. Add more detail if you want, "
            "or choose one of the suggested specialties to continue."
        ),
        quick_replies=(
            # Single quick reply option encouraging user to provide more details
            ClarificationQuickReply(
                label="I will give more details",
                value="I will give more details.",
                action="PROMPT_FOR_TEXT",
            ),
        ),
    )