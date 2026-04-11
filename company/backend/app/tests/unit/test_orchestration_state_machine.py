from __future__ import annotations

import pytest

from app.modules.orchestration.state_machine import (
    NEW,
    AWAITING_SPECIALTY_SELECTION,
    AWAITING_SLOT_SELECTION,
    AWAITING_CONFIRMATION,
    AWAITING_RENEWAL_SELECTION,
    COMPLETED,
    StateTransitionError,
    transition_or_raise,
)


def test_none_current_state_defaults_to_new() -> None:
    result = transition_or_raise(
        current_state=None,
        target_state=AWAITING_SPECIALTY_SELECTION,
    )
    assert result == AWAITING_SPECIALTY_SELECTION


@pytest.mark.parametrize(
    ("current_state", "target_state"),
    [
        (NEW, AWAITING_SPECIALTY_SELECTION),
        (NEW, AWAITING_RENEWAL_SELECTION),
        (NEW, COMPLETED),
        (AWAITING_SPECIALTY_SELECTION, AWAITING_SLOT_SELECTION),
        (AWAITING_SPECIALTY_SELECTION, AWAITING_SPECIALTY_SELECTION),
        (AWAITING_SPECIALTY_SELECTION, COMPLETED),
        (AWAITING_SLOT_SELECTION, AWAITING_CONFIRMATION),
        (AWAITING_SLOT_SELECTION, AWAITING_SLOT_SELECTION),
        (AWAITING_SLOT_SELECTION, COMPLETED),
        (AWAITING_CONFIRMATION, AWAITING_CONFIRMATION),
        (AWAITING_CONFIRMATION, COMPLETED),
        (AWAITING_RENEWAL_SELECTION, AWAITING_CONFIRMATION),
        (AWAITING_RENEWAL_SELECTION, AWAITING_RENEWAL_SELECTION),
        (AWAITING_RENEWAL_SELECTION, COMPLETED),
        (COMPLETED, NEW),
        (COMPLETED, AWAITING_SPECIALTY_SELECTION),
        (COMPLETED, AWAITING_RENEWAL_SELECTION),
        (COMPLETED, COMPLETED),
    ],
)
def test_allowed_transitions_return_target_state(
    current_state: str,
    target_state: str,
) -> None:
    result = transition_or_raise(
        current_state=current_state,
        target_state=target_state,
    )
    assert result == target_state


@pytest.mark.parametrize(
    ("current_state", "target_state"),
    [
        (NEW, AWAITING_SLOT_SELECTION),
        (NEW, AWAITING_CONFIRMATION),
        (AWAITING_SPECIALTY_SELECTION, AWAITING_CONFIRMATION),
        (AWAITING_SLOT_SELECTION, AWAITING_SPECIALTY_SELECTION),
        (AWAITING_CONFIRMATION, AWAITING_SLOT_SELECTION),
        (AWAITING_RENEWAL_SELECTION, AWAITING_SLOT_SELECTION),
    ],
)
def test_illegal_transitions_raise_state_transition_error(
    current_state: str,
    target_state: str,
) -> None:
    with pytest.raises(StateTransitionError) as exc_info:
        transition_or_raise(
            current_state=current_state,
            target_state=target_state,
        )

    exc = exc_info.value
    assert exc.current_state == current_state
    assert exc.target_state == target_state
    assert str(exc) == f"Illegal state transition from {current_state} to {target_state}."


def test_unknown_current_state_is_treated_as_invalid() -> None:
    with pytest.raises(StateTransitionError) as exc_info:
        transition_or_raise(
            current_state="UNKNOWN_STATE",
            target_state=AWAITING_SPECIALTY_SELECTION,
        )

    assert exc_info.value.current_state == "UNKNOWN_STATE"
    assert exc_info.value.target_state == AWAITING_SPECIALTY_SELECTION