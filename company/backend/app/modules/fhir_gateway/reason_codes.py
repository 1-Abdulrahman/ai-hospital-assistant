from __future__ import annotations


FHIR_UNAVAILABLE = "FHIR_UNAVAILABLE"
FHIR_TIMEOUT = "FHIR_TIMEOUT"
PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
NO_SLOTS_AVAILABLE = "NO_SLOTS_AVAILABLE"
SLOT_NO_LONGER_AVAILABLE = "SLOT_NO_LONGER_AVAILABLE"
APPOINTMENT_CONFLICT = "APPOINTMENT_CONFLICT"
APPOINTMENT_CREATE_FAILED = "APPOINTMENT_CREATE_FAILED"
INVALID_REQUEST = "INVALID_REQUEST"
TASK_CREATE_FAILED = "TASK_CREATE_FAILED"


DEFAULT_MESSAGES: dict[str, str] = {
    FHIR_UNAVAILABLE: "FHIR service is unavailable.",
    FHIR_TIMEOUT: "FHIR request timed out.",
    PATIENT_NOT_FOUND: "Patient was not found.",
    NO_SLOTS_AVAILABLE: "No slots are available.",
    SLOT_NO_LONGER_AVAILABLE: "Selected slot is no longer available.",
    APPOINTMENT_CONFLICT: "Appointment conflicts with an existing booking.",
    APPOINTMENT_CREATE_FAILED: "Appointment could not be created.",
    INVALID_REQUEST: "FHIR request is invalid.",
    TASK_CREATE_FAILED: "FHIR Task could not be created.",
}


def message_for(reason_code: str) -> str:
    """Return the user-facing message for a FHIR gateway reason code."""
    return DEFAULT_MESSAGES.get(reason_code, "FHIR request failed.")


def default_status_code_for(reason_code: str) -> int:
    """Map a FHIR gateway reason code to the default HTTP status code."""
    # Specific client and availability failures are mapped first so callers get
    # a predictable status even when a reason code is reused across flows.
    if reason_code in {FHIR_UNAVAILABLE, FHIR_TIMEOUT, APPOINTMENT_CREATE_FAILED, TASK_CREATE_FAILED}:
        return 503
    if reason_code in {APPOINTMENT_CONFLICT, SLOT_NO_LONGER_AVAILABLE}:
        return 409
    if reason_code == PATIENT_NOT_FOUND:
        return 404
    if reason_code == INVALID_REQUEST:
        return 400
    return 500


def is_retryable(reason_code: str) -> bool:
    """Return whether the failure should be treated as retryable."""
    return reason_code in {FHIR_UNAVAILABLE, FHIR_TIMEOUT}


class FhirGatewayError(Exception):
    """Exception raised when the FHIR gateway cannot complete an operation."""

    def __init__(
        self,
        *,
        reason_code: str,
        user_message: str | None = None,
        status_code: int | None = None,
        details: str | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.user_message = user_message or message_for(reason_code)
        self.status_code = status_code or default_status_code_for(reason_code)
        self.details = details
        self.retryable = is_retryable(reason_code)
        super().__init__(self.user_message)