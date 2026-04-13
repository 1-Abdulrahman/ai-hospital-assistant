from __future__ import annotations

from app.modules.fhir_gateway.reason_codes import (
    APPOINTMENT_CONFLICT,
    FHIR_TIMEOUT,
    INVALID_REQUEST,
    SLOT_NO_LONGER_AVAILABLE,
    default_status_code_for,
    is_retryable,
    message_for,
)


def test_reason_code_messages_are_stable() -> None:
    assert message_for(FHIR_TIMEOUT) == "FHIR request timed out."
    assert message_for(APPOINTMENT_CONFLICT) == "Appointment conflicts with an existing booking."
    assert message_for(SLOT_NO_LONGER_AVAILABLE) == "Selected slot is no longer available."


def test_reason_code_status_mapping_is_stable() -> None:
    assert default_status_code_for(FHIR_TIMEOUT) == 503
    assert default_status_code_for(APPOINTMENT_CONFLICT) == 409
    assert default_status_code_for(SLOT_NO_LONGER_AVAILABLE) == 409
    assert default_status_code_for(INVALID_REQUEST) == 400


def test_retryable_flags_are_stable() -> None:
    assert is_retryable(FHIR_TIMEOUT) is True
    assert is_retryable(APPOINTMENT_CONFLICT) is False
    assert is_retryable(SLOT_NO_LONGER_AVAILABLE) is False