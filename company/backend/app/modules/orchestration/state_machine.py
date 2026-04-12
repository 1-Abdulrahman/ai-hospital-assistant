from __future__ import annotations

from dataclasses import dataclass


NEW = "NEW"
AWAITING_SPECIALTY_SELECTION = "AWAITING_SPECIALTY_SELECTION"
AWAITING_CONTINUITY_IDENTITY = "AWAITING_CONTINUITY_IDENTITY"
AWAITING_SLOT_SELECTION = "AWAITING_SLOT_SELECTION"
AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
AWAITING_RENEWAL_IDENTITY = "AWAITING_RENEWAL_IDENTITY"
AWAITING_RENEWAL_SELECTION = "AWAITING_RENEWAL_SELECTION"
COMPLETED = "COMPLETED"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    NEW: {
        AWAITING_SPECIALTY_SELECTION,
        AWAITING_RENEWAL_IDENTITY,
        COMPLETED,
    },
    AWAITING_RENEWAL_IDENTITY: {
        AWAITING_RENEWAL_SELECTION,
        AWAITING_RENEWAL_IDENTITY,
        COMPLETED,
    },
    AWAITING_SPECIALTY_SELECTION: {
        AWAITING_CONTINUITY_IDENTITY,
        AWAITING_SLOT_SELECTION,
        AWAITING_SPECIALTY_SELECTION,
        COMPLETED,
    },
    AWAITING_CONTINUITY_IDENTITY: {
        AWAITING_SLOT_SELECTION,
        AWAITING_CONTINUITY_IDENTITY,
        COMPLETED,
    },
    AWAITING_SLOT_SELECTION: {
        AWAITING_CONFIRMATION,
        AWAITING_SLOT_SELECTION,
        COMPLETED,
    },
    AWAITING_CONFIRMATION: {
        COMPLETED,
        AWAITING_CONFIRMATION,
    },
    AWAITING_RENEWAL_SELECTION: {
        AWAITING_CONFIRMATION,
        AWAITING_RENEWAL_SELECTION,
        COMPLETED,
    },
    COMPLETED: {
        NEW,
        AWAITING_SPECIALTY_SELECTION,
        AWAITING_RENEWAL_SELECTION,
        COMPLETED,
    },
}


@dataclass(frozen=True)
class StateTransitionError(Exception):
    current_state: str
    target_state: str

    def __str__(self) -> str:
        return f"Illegal state transition from {self.current_state} to {self.target_state}."


def transition_or_raise(*, current_state: str | None, target_state: str) -> str:
    current = current_state or NEW
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target_state not in allowed:
        raise StateTransitionError(current_state=current, target_state=target_state)
    return target_state