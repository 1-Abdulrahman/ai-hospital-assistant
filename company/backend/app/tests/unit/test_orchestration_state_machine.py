from __future__ import annotations

import pytest

from app.modules.orchestration.state_machine import (
    ALLOWED_TRANSITIONS,
    NEW,
    AWAITING_SPECIALTY_SELECTION,
    AWAITING_SLOT_SELECTION,
    AWAITING_CONFIRMATION,
    AWAITING_RENEWAL_IDENTITY,
    AWAITING_RENEWAL_SELECTION,
    COMPLETED,
    transition_or_raise,
)


def test_new_allows_renewal_identity_transition() -> None:
    assert AWAITING_RENEWAL_IDENTITY in ALLOWED_TRANSITIONS[NEW]
    assert (
        transition_or_raise(
            current_state=NEW,
            target_state=AWAITING_RENEWAL_IDENTITY,
        )
        == AWAITING_RENEWAL_IDENTITY
    )


def test_new_allows_existing_scheduling_transitions() -> None:
    assert AWAITING_SPECIALTY_SELECTION in ALLOWED_TRANSITIONS[NEW]
    assert COMPLETED in ALLOWED_TRANSITIONS[NEW]

    assert (
        transition_or_raise(
            current_state=NEW,
            target_state=AWAITING_SPECIALTY_SELECTION,
        )
        == AWAITING_SPECIALTY_SELECTION
    )

    assert (
        transition_or_raise(
            current_state=NEW,
            target_state=COMPLETED,
        )
        == COMPLETED
    )


def test_awaiting_renewal_identity_allows_retrieval_of_medications() -> None:
    assert AWAITING_RENEWAL_SELECTION in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_IDENTITY]
    assert (
        transition_or_raise(
            current_state=AWAITING_RENEWAL_IDENTITY,
            target_state=AWAITING_RENEWAL_SELECTION,
        )
        == AWAITING_RENEWAL_SELECTION
    )


def test_awaiting_renewal_identity_allows_retrying_identity_step() -> None:
    assert AWAITING_RENEWAL_IDENTITY in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_IDENTITY]
    assert (
        transition_or_raise(
            current_state=AWAITING_RENEWAL_IDENTITY,
            target_state=AWAITING_RENEWAL_IDENTITY,
        )
        == AWAITING_RENEWAL_IDENTITY
    )


def test_awaiting_renewal_selection_allows_confirmation() -> None:
    assert AWAITING_CONFIRMATION in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_SELECTION]
    assert (
        transition_or_raise(
            current_state=AWAITING_RENEWAL_SELECTION,
            target_state=AWAITING_CONFIRMATION,
        )
        == AWAITING_CONFIRMATION
    )


def test_awaiting_renewal_selection_allows_retrying_selection() -> None:
    assert AWAITING_RENEWAL_SELECTION in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_SELECTION]
    assert (
        transition_or_raise(
            current_state=AWAITING_RENEWAL_SELECTION,
            target_state=AWAITING_RENEWAL_SELECTION,
        )
        == AWAITING_RENEWAL_SELECTION
    )


def test_illegal_transition_new_to_renewal_selection_is_rejected() -> None:
    assert AWAITING_RENEWAL_SELECTION not in ALLOWED_TRANSITIONS[NEW]

    with pytest.raises(Exception):
        transition_or_raise(
            current_state=NEW,
            target_state=AWAITING_RENEWAL_SELECTION,
        )


def test_illegal_transition_new_to_confirmation_is_rejected() -> None:
    assert AWAITING_CONFIRMATION not in ALLOWED_TRANSITIONS[NEW]

    with pytest.raises(Exception):
        transition_or_raise(
            current_state=NEW,
            target_state=AWAITING_CONFIRMATION,
        )


def test_illegal_transition_renewal_identity_to_slot_selection_is_rejected() -> None:
    assert AWAITING_SLOT_SELECTION not in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_IDENTITY]

    with pytest.raises(Exception):
        transition_or_raise(
            current_state=AWAITING_RENEWAL_IDENTITY,
            target_state=AWAITING_SLOT_SELECTION,
        )


def test_illegal_transition_renewal_identity_to_specialty_selection_is_rejected() -> None:
    assert AWAITING_SPECIALTY_SELECTION not in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_IDENTITY]

    with pytest.raises(Exception):
        transition_or_raise(
            current_state=AWAITING_RENEWAL_IDENTITY,
            target_state=AWAITING_SPECIALTY_SELECTION,
        )


def test_awaiting_renewal_identity_can_be_completed() -> None:
    assert COMPLETED in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_IDENTITY]
    assert (
        transition_or_raise(
            current_state=AWAITING_RENEWAL_IDENTITY,
            target_state=COMPLETED,
        )
        == COMPLETED
    )


def test_awaiting_renewal_selection_can_be_completed() -> None:
    assert COMPLETED in ALLOWED_TRANSITIONS[AWAITING_RENEWAL_SELECTION]
    assert (
        transition_or_raise(
            current_state=AWAITING_RENEWAL_SELECTION,
            target_state=COMPLETED,
        )
        == COMPLETED
    )