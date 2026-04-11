from __future__ import annotations


OK = "OK"
OTP_NOT_VERIFIED = "OTP_NOT_VERIFIED"
NO_PROVIDERS_AVAILABLE = "NO_PROVIDERS_AVAILABLE"
NO_SLOTS_AVAILABLE = "NO_SLOTS_AVAILABLE"
SLOT_TAKEN = "SLOT_TAKEN"
DUPLICATE_APPOINTMENT_BLOCKED = "DUPLICATE_APPOINTMENT_BLOCKED"
IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
IDEMPOTENCY_KEY_REUSE_MISMATCH = "IDEMPOTENCY_KEY_REUSE_MISMATCH"
FHIR_UNAVAILABLE = "FHIR_UNAVAILABLE"
APPOINTMENT_CREATE_FAILED = "APPOINTMENT_CREATE_FAILED"
INVALID_REQUEST = "INVALID_REQUEST"
INTERNAL_ERROR = "INTERNAL_ERROR"


DEFAULT_MESSAGES: dict[str, str] = {
    OK: "Request completed successfully.",
    OTP_NOT_VERIFIED: "OTP must be verified before booking.",
    NO_PROVIDERS_AVAILABLE: "No schedules are configured for the selected specialty.",
    NO_SLOTS_AVAILABLE: "No slots are available for the selected specialty.",
    SLOT_TAKEN: "Selected slot is no longer available.",
    DUPLICATE_APPOINTMENT_BLOCKED: "A duplicate appointment was blocked.",
    IDEMPOTENCY_KEY_REQUIRED: "Idempotency-Key header is required.",
    IDEMPOTENCY_KEY_REUSE_MISMATCH: "Idempotency key was reused with a different request.",
    FHIR_UNAVAILABLE: "FHIR service is unavailable.",
    APPOINTMENT_CREATE_FAILED: "Appointment could not be created.",
    INVALID_REQUEST: "Scheduling request is invalid.",
    INTERNAL_ERROR: "Scheduling failed unexpectedly.",
}


def message_for(reason_code: str) -> str:
    return DEFAULT_MESSAGES.get(reason_code, DEFAULT_MESSAGES[INTERNAL_ERROR])


def default_status_code_for(reason_code: str) -> int:
    if reason_code in {OK, NO_SLOTS_AVAILABLE, NO_PROVIDERS_AVAILABLE}:
        return 200
    if reason_code in {INVALID_REQUEST, IDEMPOTENCY_KEY_REQUIRED, OTP_NOT_VERIFIED}:
        return 400
    if reason_code in {
        SLOT_TAKEN,
        DUPLICATE_APPOINTMENT_BLOCKED,
        IDEMPOTENCY_KEY_REUSE_MISMATCH,
    }:
        return 409
    if reason_code in {FHIR_UNAVAILABLE, APPOINTMENT_CREATE_FAILED}:
        return 503
    return 500


def is_retryable(reason_code: str) -> bool:
    return reason_code in {FHIR_UNAVAILABLE, APPOINTMENT_CREATE_FAILED, INTERNAL_ERROR}


class SchedulingError(Exception):
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