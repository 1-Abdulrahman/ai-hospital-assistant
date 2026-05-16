from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from fastapi import BackgroundTasks

from sqlalchemy.orm import Session

from app.modules.fhir_gateway.reason_codes import FhirGatewayError
from app.api.schemas.chat import ConfirmationSummary
from app.core.correlation import get_correlation_id
from app.db.models import AssistantSession
from app.modules.fhir_gateway.client import FhirClient
from app.modules.nlp.inference import NlpService, _safe_input_summary, _safe_text_summary
from app.modules.notification.service import (
    queue_appointment_confirmation_email,
    queue_renewal_confirmation_email,
)
from app.modules.observability.emitter import emit_event
from app.modules.otp.service import (
    build_patient_key_hash,
    ensure_tenant_exists,
    ensure_tenant_header_matches_body,
    normalize_email,
)
from app.modules.otp.validators import (
    IdentityValidationError,
    validate_national_id_and_infer_type,
)
from app.modules.orchestration.state_machine import (
    AWAITING_CONFIRMATION,
    AWAITING_CONTINUITY_IDENTITY,
    AWAITING_RENEWAL_IDENTITY,
    AWAITING_RENEWAL_SELECTION,
    AWAITING_SLOT_SELECTION,
    AWAITING_SPECIALTY_SELECTION,
    COMPLETED,
    NEW,
    StateTransitionError,
    reset_to_new_or_raise,
    transition_or_raise,
)
from app.modules.scheduling.reason_codes import (
    NO_PROVIDERS_AVAILABLE,
    NO_SLOTS_AVAILABLE,
    OK,
    SchedulingError,
)
from app.modules.scheduling.service import (
    book_appointment,
    ensure_verified_otp_or_raise,
    list_available_slots,
)

PROVIDERS_PATH = Path(__file__).resolve().parents[1] / "scheduling" / "providers_static.json"


# ==============================================================================
# ERROR HANDLING
# ==============================================================================

@dataclass(frozen=True)
class ChatOrchestrationError(Exception):
    """Structured error response for orchestration service failures.
    
    This exception is used to communicate API-level errors with appropriate
    HTTP status codes and user-friendly messages while preserving technical
    reason codes for debugging and logging.
    
    Attributes:
        reason_code: Technical code identifying the error type (e.g., 'INVALID_REQUEST')
        user_message: User-friendly message explaining the error
        status_code: HTTP status code to return (default: 400)
        details: Optional technical details for logging and debugging
    """
    reason_code: str
    user_message: str
    status_code: int = 400
    details: str | None = None


def _utcnow() -> datetime:
    """Return the current UTC timestamp.
    
    Provides a consistent way to get the current time in UTC, ensuring all
    timestamps in the system are in the same timezone.
    
    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(timezone.utc)


# ==============================================================================
# TEXT NORMALIZATION & FORMATTING
# ==============================================================================

def _humanize_specialty(value: str) -> str:
    """Convert a specialty token into a UI-friendly label.
    
    Transforms internal specialty identifiers (e.g., 'general_practice') into
    human-readable labels (e.g., 'General Practice') for display in the UI.
    
    Args:
        value: Specialty token (typically snake_case)
        
    Returns:
        Title-cased display label
    """
    return value.replace("_", " ").strip().title()


def _normalize_specialty_token(value: str | None) -> str:
    """Normalize specialty text for matching and comparisons.
    
    Converts specialty identifiers to lowercase with underscores replaced by spaces,
    enabling case-insensitive and format-flexible comparison of specialty values.
    
    Args:
        value: Specialty token to normalize
        
    Returns:
        Lowercase normalized specialty text
    """
    if not value:
        return ""
    return value.strip().replace("_", " ").lower()


def _find_latest_matching_appointment(appointments: list[Any], specialty_id: str | None) -> Any | None:
    """Find the newest appointment that matches the requested specialty.
    
    Searches appointment history to locate the most recent appointment
    for a given specialty. Used in continuity-of-care flows to find the
    patient's last provider when checking for continuity eligibility.
    
    Args:
        appointments: List of past appointment records
        specialty_id: Specialty to filter by
        
    Returns:
        Most recent matching appointment, or None if no match found
    """
    specialty_token = _normalize_specialty_token(specialty_id)
    matching = [
        item
        for item in appointments
        if _normalize_specialty_token(getattr(item, "specialty", None)) == specialty_token
    ]
    if not matching:
        return None
    return sorted(
        matching,
        key=lambda item: getattr(item, "startUtc", None) or "",
        reverse=True,
    )[0]

def _normalize_message_text(value: str | None) -> str:
    """Trim free-form user text and coerce missing values to an empty string.
    
    Sanitizes user input by removing leading/trailing whitespace and converting
    None to empty string. Used for normalizing patient complaints and clarifications.
    
    Args:
        value: Raw user input string
        
    Returns:
        Trimmed string or empty string if input was None
    """
    return (value or "").strip()



# ==============================================================================
# CLARIFICATION HANDLING
# ==============================================================================
# When the NLP classifier is uncertain about specialty prediction, it can request
# clarification. These functions manage the back-and-forth dialogue and merge
# multiple clarification turns back into the original complaint for reclassification.

def _clear_clarification_context(session: AssistantSession) -> None:
    """Clear any pending clarification state from the session.
    
    Resets all clarification-specific fields so that the next complaint or flow
    starts cleanly without residual state from previous clarification turns.
    This includes the clarification flag, key, original complaint, and merged text.
    """
    session.clarification_pending = False
    session.clarification_key = None
    session.original_complaint_text = None
    session.clarification_detail_text = None
    session.merged_classification_text = None

def _candidate_payload_from_prediction(prediction: Any) -> list[dict[str, Any]]:
    """Convert classifier candidates into response payload items.
    
    Extracts the top candidate specialties from an NLP prediction and formats
    them as simple dictionaries with ID and rounded confidence scores.
    
    Args:
        prediction: NLP classification result object
        
    Returns:
        List of candidate dicts with 'id' and 'confidence' keys
    """
    return [
        {
            "id": candidate.specialty_id,
            "confidence": round(candidate.confidence, 4),
        }
        for candidate in prediction.top_candidates
    ]


# ==============================================================================
# NLP TELEMETRY & DIAGNOSTICS
# ==============================================================================
# These functions build structured telemetry payloads for monitoring NLP performance,
# classifier confidence, and ambiguity decision-making for logging and analysis.

def _classification_diagnostics(
    prediction: Any,
    *,
    min_confidence: float,
    ambiguity_delta: float,
) -> dict[str, Any]:
    """Build confidence and ambiguity diagnostics for classifier telemetry.
    
    Computes metrics for monitoring and debugging NLP classifier behavior:
    - Top candidate confidence scores
    - Gap between top two predictions
    - Whether thresholds for ambiguity were crossed
    - Decision reason (why clarification was requested, if applicable)
    
    Args:
        prediction: NLP classification result
        min_confidence: Minimum acceptable confidence threshold
        ambiguity_delta: Minimum gap between top-2 candidates
        
    Returns:
        Dictionary with diagnostic metrics and decision explanation
    """
    top_candidates = list(prediction.top_candidates or [])

    top_confidence = round(top_candidates[0].confidence, 4) if len(top_candidates) >= 1 else None
    second_confidence = round(top_candidates[1].confidence, 4) if len(top_candidates) >= 2 else None
    confidence_gap = (
        round(top_confidence - second_confidence, 4)
        if top_confidence is not None and second_confidence is not None
        else None
    )

    below_min_confidence = (
        top_confidence is not None and top_confidence < min_confidence
    )
    gap_too_small = (
        confidence_gap is not None and confidence_gap < ambiguity_delta
    )

    if prediction.needs_clarification:
        if below_min_confidence and gap_too_small:
            ambiguity_decision = "both"
        elif below_min_confidence:
            ambiguity_decision = "below_min_confidence"
        elif gap_too_small:
            ambiguity_decision = "gap_too_small"
        else:
            ambiguity_decision = "manual_fallback"
    else:
        ambiguity_decision = "accepted"

    return {
        "topConfidence": top_confidence,
        "secondConfidence": second_confidence,
        "confidenceGap": confidence_gap,
        "thresholdMinConfidence": round(min_confidence, 4),
        "thresholdAmbiguityDelta": round(ambiguity_delta, 4),
        "ambiguityDecision": ambiguity_decision,
    }


def _build_nlp_preprocessed_payload(
    *,
    prediction: Any,
    session: AssistantSession,
    classification_input: str,
    used_merged_clarification_input: bool,
) -> dict[str, Any]:
    """Build telemetry for the NLP preprocessing step.
    
    Captures information about how the input text was prepared for classification,
    including original complaint, clarification details, and any text transformations
    applied by the NLP preprocessor.
    
    Args:
        prediction: NLP classification result with preprocessing info
        session: Patient session with complaint/clarification history
        classification_input: Actual text sent to classifier
        used_merged_clarification_input: Whether clarification was merged
        
    Returns:
        Telemetry payload for event logging
    """
    payload: dict[str, Any] = {
        "component": "nlp",
        "modelVersion": prediction.model_version,
        "classifierInputSummary": prediction.original_input_summary,
        "cleanedInputSummary": prediction.cleaned_input_summary,
        "normalizedInputSummary": prediction.normalized_input_summary,
        "preprocessingActions": list(prediction.preprocessing_actions),
        "usedMergedClarificationInput": used_merged_clarification_input,
    }

    if session.original_complaint_text:
        payload["originalComplaintSummary"] = _safe_text_summary(
            session.original_complaint_text
        )

    if session.clarification_detail_text:
        payload["clarificationDetailSummary"] = _safe_text_summary(
            session.clarification_detail_text
        )

    if used_merged_clarification_input:
        payload["mergedInputSummary"] = _safe_text_summary(classification_input)

    if session.clarification_key:
        payload["clarificationKey"] = session.clarification_key

    return payload


def _build_nlp_classified_payload(
    *,
    prediction: Any,
    candidates: list[dict[str, Any]],
    min_confidence: float,
    ambiguity_delta: float,
) -> dict[str, Any]:
    """Build telemetry for the NLP classification result.
    
    Captures the classification outcome including predicted specialty, candidate
    rankings, confidence metrics, and ambiguity diagnostics for monitoring
    classifier performance.
    
    Args:
        prediction: NLP classification result
        candidates: Formatted top candidates with confidence
        min_confidence: Confidence threshold for validation
        ambiguity_delta: Gap threshold for ambiguity detection
        
    Returns:
        Telemetry payload for event logging
    """
    payload: dict[str, Any] = {
        "component": "nlp",
        "modelVersion": prediction.model_version,
        "topCandidates": candidates[:3],
        **_classification_diagnostics(
            prediction,
            min_confidence=min_confidence,
            ambiguity_delta=ambiguity_delta,
        ),
    }

    winning_label = prediction.primary_specialty_id
    if winning_label:
        payload["predictedSpecialty"] = winning_label

    return payload

def _append_clarification_detail(
    *,
    existing_detail_text: str | None,
    new_detail_text: str,
) -> str:
    """Append a clarification turn while keeping bullet formatting stable.
    
    Accumulates multiple clarification responses from the user into a single
    bullet-point list. Each clarification detail is added as a new bullet,
    making it easy to reconstruct the full context later.
    
    Args:
        existing_detail_text: Previously accumulated clarification details (if any)
        new_detail_text: New clarification response from the user
        
    Returns:
        Formatted string with all clarification details as bullet points
    """
    new_detail = _normalize_message_text(new_detail_text)

    existing_lines = [
        line.lstrip("-").strip()
        for line in (existing_detail_text or "").splitlines()
        if line.strip()
    ]

    if new_detail:
        existing_lines.append(new_detail)

    return "\n".join(f"- {line}" for line in existing_lines)


def _build_clarification_details_block(detail_text: str | None) -> str:
    """Render clarification text as a bullet block for downstream classification.
    
    Takes the accumulated clarification details and formats them as a clean
    bullet-point list that can be appended to the original complaint text
    for reclassification by the NLP model.
    
    Args:
        detail_text: Clarification details (potentially with existing bullet formatting)
        
    Returns:
        Formatted string with each line as a bullet point
    """
    lines = [
        line.lstrip("-").strip()
        for line in (detail_text or "").splitlines()
        if line.strip()
    ]

    return "\n".join(f"- {line}" for line in lines)


def _merge_clarification_text(
    *,
    original_complaint: str,
    clarification_detail: str,
) -> str:
    """Combine the complaint and clarification details into one classifier input.
    
    Creates a structured text block that preserves the original complaint while
    appending follow-up clarification details. This merged text is sent to the
    NLP classifier for re-classification with additional context.
    
    The format is:
        Original complaint: <complaint>
        Clarification details:
        - <detail 1>
        - <detail 2>
        ...
        
    Args:
        original_complaint: Initial patient complaint text
        clarification_detail: Accumulated clarification details
        
    Returns:
        Merged text ready for NLP classification
    """
    original = _normalize_message_text(original_complaint)
    detail_block = _build_clarification_details_block(clarification_detail)

    if not original:
        return detail_block
    if not detail_block:
        return original

    return (
        f"Original complaint: {original}\n"
        f"Clarification details:\n{detail_block}"
    )
    
    
def _sort_slots_for_preferred_practitioner(
    items: list[Any],
    preferred_practitioner_ref: str | None,
) -> list[Any]:
    """Prioritize slots for the preferred practitioner when one is known.
    
    Continuity-of-care feature: When a patient has an existing relationship with
    a specific practitioner, slots with that practitioner are sorted first,
    followed by other available slots in chronological order.
    
    Args:
        items: List of available slot objects
        preferred_practitioner_ref: Reference ID of the patient's preferred practitioner
        
    Returns:
        Reordered list with preferred practitioner slots first
    """
    if not items or not preferred_practitioner_ref:
        return items

    def sort_key(item: Any) -> tuple[int, str]:
        slot = _slot_to_mapping(item)
        practitioner_ref = str(_pick(slot, "practitionerRef", "practitioner_ref") or "")
        start_utc = str(_pick(slot, "startUtc", "start_utc") or "")
        preferred_rank = 0 if practitioner_ref == preferred_practitioner_ref else 1
        return (preferred_rank, start_utc)

    return sorted(items, key=sort_key)


def _load_supported_specialties() -> dict[str, list[dict]]:
    """Load the static specialty catalog used for manual selection flows.
    
    Reads the providers_static.json file containing all available medical specialties.
    This catalog is used when:
    - The NLP model is unavailable
    - The user initiates a direct scheduling flow
    - Manual specialty selection is needed as a fallback
    
    Returns:
        Dictionary mapping specialty IDs to their metadata
    """
    with PROVIDERS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


SUPPORTED_SPECIALTIES = _load_supported_specialties()


# ==============================================================================
# OBJECT CONVERSION & FIELD EXTRACTION
# ==============================================================================
# Utilities to normalize heterogeneous objects (dicts, Pydantic models, dataclasses)
# into consistent formats, and to flexibly extract values from objects with
# multiple naming conventions (camelCase vs snake_case).

def _ensure_client_session_matches_header(*, header_session_id: str, client_session_id: str) -> None:
    """Reject requests where the header session and body session differ.
    
    Security check: Ensures that the session ID in the HTTP headers matches
    the session ID in the request body. Prevents session fixation attacks.
    
    Args:
        header_session_id: Session ID from request headers
        client_session_id: Session ID from request body
        
    Raises:
        ChatOrchestrationError: If IDs don't match
    """
    if header_session_id.strip() != client_session_id.strip():
        raise ChatOrchestrationError(
            reason_code="INVALID_REQUEST",
            user_message="Client session and request session must match.",
            status_code=400,
        )


def _selection_item(
    *,
    item_id: str,
    label: str,
    description: str | None = None,
    confidence: float | None = None,
    meta: dict | None = None,
) -> dict:
    """Create a normalized selection item for the chat UI.
    
    Builds a consistent item structure for selection lists. Confidence scores
    are included for NLP-predicted specialties. Metadata can carry extra context
    like time formatting, provider info, or availability flags.
    
    Args:
        item_id: Unique identifier for the item (specialty ID, slot ID, etc.)
        label: Display text shown to the user
        description: Optional longer description or explanation
        confidence: Optional confidence score (for NLP predictions)
        meta: Optional dictionary of extra data for the UI
        
    Returns:
        Normalized dictionary for selection list display
    """
    payload: dict[str, Any] = {
        "id": item_id,
        "label": label,
    }
    if description:
        payload["description"] = description
    if confidence is not None:
        payload["confidence"] = confidence
    if meta:
        payload["meta"] = meta
    return payload


def _specialty_selection_list(*, candidates: list[dict] | None = None) -> list[dict]:
    """Build the specialty selection list shown to the patient.
    
    Creates a selection list of medical specialties. If NLP candidates are provided,
    they're ranked by confidence. Otherwise, all supported specialties are shown
    in alphabetical order as a fallback for manual selection.
    
    Args:
        candidates: Optional list of NLP-predicted specialties with confidence scores
        
    Returns:
        List wrapped in selection format for chat UI specialty selection
    """
    specialty_items: list[dict] = []
    if candidates:
        for candidate in candidates:
            specialty_id = candidate["id"]
            specialty_items.append(
                _selection_item(
                    item_id=specialty_id,
                    label=_humanize_specialty(specialty_id),
                    description="Suggested by symptom interpretation.",
                    confidence=candidate.get("confidence"),
                )
            )
    else:
        for specialty_id in sorted(SUPPORTED_SPECIALTIES.keys()):
            specialty_items.append(
                _selection_item(
                    item_id=specialty_id,
                    label=_humanize_specialty(specialty_id),
                    description="Available for scheduling.",
                )
            )
    return [{"type": "specialty", "items": specialty_items}]


def _renewal_items_selection_list(items: list[Any]) -> list[dict]:
    """Build the medication selection list for renewal flows.
    
    Transforms medication request objects into UI-ready selection items.
    Includes medication dosage, refill status, repeat counts, and validity
    periods in the item descriptions.
    
    Args:
        items: List of medication request objects from FHIR gateway
        
    Returns:
        List wrapped in selection format for chat UI medication selection
    """
    selection_items: list[dict] = []

    for item in items:
        description_parts: list[str] = []

        if getattr(item, "dosageText", None):
            description_parts.append(item.dosageText)

        refill_message = getattr(item, "refillStatusMessage", None)
        if refill_message:
            description_parts.append(refill_message)

        repeats = getattr(item, "numberOfRepeatsAllowed", None)
        if repeats is not None:
            description_parts.append(f"Repeats allowed in source request: {repeats}")

        validity_end = getattr(item, "validityPeriodEnd", None)
        if validity_end:
            description_parts.append(f"Validity end: {validity_end}")

        selection_items.append(
            _selection_item(
                item_id=item.medicationRequestRef,
                label=item.medicationDisplay,
                description=" | ".join(description_parts)
                or "Available for refill request intake.",
            )
        )

    return [{"type": "medication", "items": selection_items}]


def _find_selected_renewal_item(
    items: list[Any],
    medication_request_ref: str,
) -> Any | None:
    """Locate the renewal item chosen by the patient.
    
    Searches the list of available renewal items to find the one with
    matching medication request reference ID.
    
    Args:
        items: List of available medication requests
        medication_request_ref: Reference ID user selected
        
    Returns:
        Matching medication request object, or None if not found
    """
    target = (medication_request_ref or "").strip()
    if not target:
        return None

    for item in items:
        if getattr(item, "medicationRequestRef", None) == target:
            return item

    return None

def _slot_to_mapping(slot: Any) -> dict[str, Any]:
    """
    Normalize a slot-like object into a plain dictionary.
    
    Handles multiple object representations that might come from different
    service layers, ensuring consistent dictionary format for downstream processing.

    Supports:
    - dict payloads (returns as-is)
    - Pydantic models with model_dump() (v2 API)
    - Pydantic models with dict() (v1 API)
    - dataclass instances (uses asdict)
    - plain Python objects with expected attributes (extracts attributes)
    
    Args:
        slot: Slot object in any of the supported formats
        
    Returns:
        Dictionary with normalized field names (camelCase keys)
    """
    if slot is None:
        return {}

    if isinstance(slot, Mapping):
        return dict(slot)

    if hasattr(slot, "model_dump"):
        return dict(slot.model_dump())

    if hasattr(slot, "dict"):
        return dict(slot.dict())

    if is_dataclass(slot):
        return asdict(slot)

    return {
        "slotId": getattr(slot, "slotId", getattr(slot, "slot_id", None)),
        "slotRef": getattr(slot, "slotRef", getattr(slot, "slot_ref", None)),
        "scheduleRef": getattr(slot, "scheduleRef", getattr(slot, "schedule_ref", None)),
        "practitionerRef": getattr(slot, "practitionerRef", getattr(slot, "practitioner_ref", None)),
        "practitionerDisplay": getattr(
            slot,
            "practitionerDisplay",
            getattr(slot, "practitioner_display", None),
        ),
        "specialty": getattr(slot, "specialty", None),
        "startUtc": getattr(slot, "startUtc", getattr(slot, "start_utc", None)),
        "endUtc": getattr(slot, "endUtc", getattr(slot, "end_utc", None)),
        "status": getattr(slot, "status", None),
    }


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    """Return the first non-null value for any of the provided field names.
    
    Utility to handle inconsistent field naming conventions across different
    upstream services. Supports both camelCase and snake_case field names,
    allowing flexible integration with multiple APIs and data sources.
    
    Args:
        mapping: Dictionary-like object to search
        *keys: Field names to check in order (tries camelCase, then snake_case)
        
    Returns:
        First non-null value found, or None if all keys are missing/null
    """
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None

def _parse_utc_datetime(value: str | None) -> datetime | None:
    """Parse an ISO timestamp and normalize it to UTC when possible.
    
    Handles various ISO 8601 timestamp formats including those with 'Z' suffix.
    Safely returns None for invalid or missing timestamps rather than raising.
    
    Args:
        value: ISO 8601 timestamp string (with or without timezone info)
        
    Returns:
        Parsed datetime object in UTC timezone, or None if parsing fails
    """
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


# ==============================================================================
# DATETIME FORMATTING FOR UI DISPLAY
# ==============================================================================
# Convert UTC timestamps into human-readable labels for the chat interface.

def _format_slot_start_label(value: str | None) -> str:
    """Format a slot start time for display in the chat UI.
    
    Converts ISO timestamp to readable format: "YYYY-MM-DD HH:MM:SS UTC"
    Falls back to raw value if parsing fails.
    
    Args:
        value: ISO 8601 timestamp string
        
    Returns:
        Formatted display string
    """
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return str(value or "Unknown start time")
    return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_slot_end_label(value: str | None) -> str | None:
    """Format a slot end time for display when available.
    
    Converts ISO timestamp to readable time format: "HH:MM:SS UTC"
    Used alongside the date from start label to show appointment duration.
    
    Args:
        value: ISO 8601 timestamp string
        
    Returns:
        Formatted time string, or None if parsing fails
    """
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return str(value).replace("Z", " UTC") if value else None
    return parsed.strftime("%H:%M:%S UTC")


def _format_display_date(value: str | None) -> str | None:
    """Format a UTC timestamp into a human-readable date label.
    
    Converts ISO timestamp to readable date format: "Mon DD Mon YYYY"
    Example: "Wed 15 May 2024"
    
    Args:
        value: ISO 8601 timestamp string
        
    Returns:
        Formatted date string, or None if parsing fails
    """
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return value[:10] if value else None
    return parsed.strftime("%a %d %b %Y")


def _format_display_time(value: str | None) -> str | None:
    """Format a UTC timestamp into a human-readable time label.
    
    Converts ISO timestamp to readable time format: "H:MM AM/PM"
    Leading zero is stripped (e.g., "9:30 AM" not "09:30 AM")
    
    Args:
        value: ISO 8601 timestamp string
        
    Returns:
        Formatted time string, or None if parsing fails
    """
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return None
    return parsed.strftime("%I:%M %p").lstrip("0")


def _date_key_from_iso(value: str | None) -> str | None:
    """Extract a stable date key from an ISO timestamp.
    
    Generates a sortable date key in format "YYYY-MM-DD" for grouping
    slots by date. Useful for UI organization of availability.
    
    Args:
        value: ISO 8601 timestamp string
        
    Returns:
        Date key string ("YYYY-MM-DD"), or None if parsing fails
    """
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return value[:10] if value else None
    return parsed.strftime("%Y-%m-%d")


def _preferred_practitioner_has_availability(
    *,
    items: list[Any],
    preferred_practitioner_ref: str | None,
) -> bool | None:
    """Detect whether any returned slot matches the preferred practitioner.
    
    Scans the available slots to determine if the patient's preferred practitioner
    has at least one available slot. Used for continuity-of-care feature to signal
    to the UI whether continuity is possible in the current results.
    
    Args:
        items: List of available appointment slots
        preferred_practitioner_ref: Patient's preferred practitioner ID
        
    Returns:
        True if preferred practitioner has availability, False if not,
        None if no preferred practitioner is set
    """
    if not preferred_practitioner_ref:
        return None

    for raw_slot in items:
        slot = _slot_to_mapping(raw_slot)
        practitioner_ref = str(_pick(slot, "practitionerRef", "practitioner_ref") or "")
        if practitioner_ref == preferred_practitioner_ref:
            return True

    return False


# ==============================================================================
# CONTINUITY OF CARE & SLOT SELECTION
# ==============================================================================
# Continuity of care allows patients to request appointment with their existing
# provider when possible. These functions build the UI responses and metadata
# for continuity preferences and slot selection.

def _build_continuity_payload(
    *,
    session: AssistantSession,
    preferred_practitioner_has_availability: bool | None,
    message: str | None,
) -> dict | None:
    """Build the continuity-of-care payload exposed to the UI.
    
    Packages continuity-of-care information for display on the client.
    Only returns data if continuity has been checked; returns None otherwise.
    The UI uses this to show whether the patient's preferred practitioner
    has availability and whether continuity of care is possible.
    
    Args:
        session: Patient session with continuity state
        preferred_practitioner_has_availability: Whether preferred provider has slots
        message: Optional custom message about continuity status
        
    Returns:
        Continuity payload dict, or None if continuity not checked
    """
    if not session.continuity_checked:
        return None

    return {
        "matched": bool(session.continuity_is_returning),
        "preferredPractitionerRef": session.continuity_preferred_practitioner_ref,
        "preferredPractitionerDisplay": session.continuity_preferred_practitioner_display,
        "preferredPractitionerHasAvailability": preferred_practitioner_has_availability,
        "message": message,
    }

def _slot_selection_list(
    *,
    items: list[Any],
    preferred_practitioner_ref: str | None = None,
) -> list[dict]:
    """Build the slot selection list shown after availability lookup.
    
    Converts raw slot objects from the scheduling service into UI-ready
    selection items with formatted times, provider information, and metadata.
    Marks slots from the preferred practitioner if continuity is active.
    
    Args:
        items: Raw slot objects from scheduling service
        preferred_practitioner_ref: Optional preferred provider ID for continuity
        
    Returns:
        List wrapped in selection format for chat UI
    """
    slot_items: list[dict] = []

    for raw_slot in items:
        slot = _slot_to_mapping(raw_slot)

        slot_id = _pick(slot, "slotId", "slot_id", "id")
        slot_ref = _pick(slot, "slotRef", "slot_ref")
        practitioner_ref = _pick(slot, "practitionerRef", "practitioner_ref")
        practitioner_display = _pick(slot, "practitionerDisplay", "practitioner_display")
        specialty = _pick(slot, "specialty")
        iso_start = _pick(slot, "startUtc", "start_utc")
        iso_end = _pick(slot, "endUtc", "end_utc")

        specialty_id = str(specialty) if specialty else None
        specialty_display = _humanize_specialty(specialty_id or "") if specialty_id else None
        date_key = _date_key_from_iso(str(iso_start) if iso_start else None)
        display_date = _format_display_date(str(iso_start) if iso_start else None)
        display_time = _format_display_time(str(iso_start) if iso_start else None)
        start_label = _format_slot_start_label(str(iso_start) if iso_start else None)
        end_label = _format_slot_end_label(str(iso_end) if iso_end else None)
        is_preferred = bool(
            preferred_practitioner_ref
            and practitioner_ref
            and str(practitioner_ref) == preferred_practitioner_ref
        )

        label = f"{practitioner_display or 'Available doctor'} • {start_label}"

        slot_items.append(
            _selection_item(
                item_id=str(slot_id or slot_ref or ""),
                label=label,
                description=f"{specialty_display or 'Specialist'} appointment slot.",
                meta={
                    "isoDate": str(iso_start) if iso_start else None,
                    "startTime": start_label,
                    "endTime": end_label,
                    "timezone": "UTC",
                    "practitionerRef": str(practitioner_ref) if practitioner_ref else None,
                    "practitionerDisplay": str(practitioner_display) if practitioner_display else None,
                    "specialtyId": specialty_id,
                    "specialtyDisplay": specialty_display,
                    "dateKey": date_key,
                    "displayDate": display_date,
                    "displayTime": display_time,
                    "isPreferredPractitioner": is_preferred,
                },
            )
        )

    return [{"type": "slot", "items": slot_items}]


# ==============================================================================
# SESSION MANAGEMENT
# ==============================================================================
# Session objects store conversation state, appointment flow progress, and
# continuity preferences. These functions create, save, and manage session state.

def _get_or_create_session(
    *,
    db: Session,
    tenant_id: str,
    client_session_id: str,
) -> tuple[AssistantSession, bool]:
    """Load the session row or create a new one for the current client session.
    
    Retrieves an existing assistant session from the database, or creates a fresh
    one if none exists. Always ensures a session object is available for the
    conversation flow.
    
    Args:
        db: Database session
        tenant_id: Tenant (hospital/organization) identifier
        client_session_id: Client-side session ID (unique per browser/device)
        
    Returns:
        Tuple of (AssistantSession object, was_created boolean)
    """
    session = (
        db.query(AssistantSession)
        .filter(
            AssistantSession.tenant_id == tenant_id,
            AssistantSession.client_session_id == client_session_id,
        )
        .first()
    )
    created = False

    if session is None:
        created = True
        now = _utcnow()
        session = AssistantSession(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            client_session_id=client_session_id,
            current_state=NEW,
            created_at_utc=now,
            updated_at_utc=now,
        )
        db.add(session)
        emit_event(
            db=db,
            tenant_id=tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="SESSION_STARTED",
            outcome="INFO",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": "Assistant session created.",
            },
        )
    return session, created


def _save_session(db: Session, session: AssistantSession) -> None:
    """Persist the session and refresh it from the database.
    
    Commits all pending changes to the session object, then refreshes it
    from the database to ensure state consistency and capture any server-side
    defaults or automatic field updates.
    
    Args:
        db: Database session
        session: AssistantSession object with pending changes
    """
    session.updated_at_utc = _utcnow()
    db.add(session)
    db.commit()
    db.refresh(session)

def _clear_session_flow_state(session: AssistantSession) -> None:
    """Clear all flow-specific fields so the session returns to the main menu.
    
    Resets the session to the NEW state by clearing appointment booking state,
    specialty selection, slot selection, renewal state, and continuity context.
    Called when user clicks "back" or starts a new flow.
    
    Args:
        session: AssistantSession to reset
    """
    session.current_state = reset_to_new_or_raise(current_state=session.current_state)
    session.flow_mode = None

    session.selected_specialty_id = None
    session.selected_doctor_id = None
    session.selected_slot_id = None
    session.selected_slot_label = None
    session.selected_slot_start_utc = None
    session.selected_date = None
    session.last_input_summary = None

    session.renewal_item_id = None
    session.renewal_item_label = None
    session.renewal_patient_key_hash = None
    session.renewal_patient_ref = None

    _reset_continuity_context(session)
    _clear_clarification_context(session)


def _session_has_active_flow(session: AssistantSession) -> bool:
    """Detect whether the session still contains active flow state.
    
    Checks if any flow-specific state markers are set. Used to determine if
    the session should be considered 'in progress' (e.g., for dropout tracking
    or to show continuation options).
    
    Args:
        session: AssistantSession to check
        
    Returns:
        True if session has active flow state, False if in NEW/menu state
    """
    return any(
        [
            bool(session.flow_mode),
            bool(session.selected_specialty_id),
            bool(session.selected_doctor_id),
            bool(session.selected_slot_id),
            bool(session.selected_date),
            bool(session.renewal_item_id),
            bool(session.renewal_patient_ref),
            bool(session.continuity_checked),
            (session.current_state or NEW) != NEW,
        ]
    )

def _reset_continuity_context(session: AssistantSession) -> None:
    """Clear continuity-of-care state without touching the rest of the flow.
    
    Resets only the continuity-specific fields while preserving other flow state.
    Used when starting a new appointment flow or when continuity lookup fails.
    
    Args:
        session: AssistantSession to update
    """
    session.continuity_checked = False
    session.continuity_patient_ref = None
    session.continuity_preferred_practitioner_ref = None
    session.continuity_preferred_practitioner_display = None
    session.continuity_is_returning = False


def _slot_failure_message(*, reason_code: str, specialty_id: str | None) -> str:
    """Translate slot lookup failures into user-facing messages.
    
    Maps technical failure codes from the scheduling service into readable
    messages that explain why no appointments are available.
    
    Args:
        reason_code: Technical failure code (e.g., NO_PROVIDERS_AVAILABLE)
        specialty_id: Specialty for which slots were requested
        
    Returns:
        Human-friendly error message for the patient
    """
    specialty_label = _humanize_specialty(specialty_id or "selected")

    if reason_code == NO_PROVIDERS_AVAILABLE:
        return f"No providers are currently configured for {specialty_label}."

    if reason_code == NO_SLOTS_AVAILABLE:
        return f"No available {specialty_label} slots were found right now."

    return "Unable to retrieve available slots right now."


async def _load_slots_for_session(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    session: AssistantSession,
) -> dict:
    """Fetch available slots and apply continuity-aware ordering when needed.
    
    Calls the scheduling service to retrieve available slots for the patient's
    selected specialty. If the patient has an existing relationship with a
    preferred practitioner (continuity-of-care), those slots are prioritized.
    
    Args:
        db: Database session
        header_tenant_id: Tenant ID from request headers (for access control)
        header_session_id: Session ID from request headers (for logging)
        body_tenant_id: Tenant ID from request body (validated against header)
        session: Patient's assistant session with selected specialty
        
    Returns:
        Slot lookup result dict with 'items', 'reasonCode', and optional 'message'
    """
    slot_result = await list_available_slots(
        db=db,
        header_tenant_id=header_tenant_id,
        session_id=header_session_id,
        body_tenant_id=body_tenant_id,
        specialty=session.selected_specialty_id or "",
    )

    if slot_result.get("items") and session.continuity_preferred_practitioner_ref:
        slot_result["items"] = _sort_slots_for_preferred_practitioner(
            slot_result["items"],
            session.continuity_preferred_practitioner_ref,
        )

    return slot_result


def _response(
    *,
    user_message: str,
    quick_replies: list[dict] | None = None,
    selection_lists: list[dict] | None = None,
    needs_clarification: bool | None = None,
    is_chronic_continuity: bool | None = None,
    continuity: dict | None = None,
    show_consent_notice: bool | None = None,
    requires_continuity_identity: bool | None = None,
    booking_reference_id: str | None = None,
    confirmation_type: str | None = None,
    confirmation_summary: dict | None = None,
    errors: list[dict] | None = None,
) -> dict:
    """Construct the standard chat API response payload.
    
    Builds the complete response object sent to the client, including the
    user-facing message, interactive UI elements (selections, quick replies),
    conversation state flags, and error information.
    
    Optional fields are only included in the response if explicitly provided,
    keeping the payload lean and predictable.
    
    Args:
        user_message: Primary text message for the user
        quick_replies: Quick action buttons for common responses
        selection_lists: Lists for specialty/slot/medication selection
        needs_clarification: Whether NLP ambiguity requires user input
        is_chronic_continuity: Whether this is a continuity of care case
        continuity: Continuity preference metadata
        show_consent_notice: Whether to show privacy/consent notice
        requires_continuity_identity: Whether identity verification needed
        booking_reference_id: Confirmation ID for successful bookings
        confirmation_type: Type of confirmation (appointment/renewal)
        confirmation_summary: Details of confirmed appointment/renewal
        errors: List of errors that occurred during processing
        
    Returns:
        Complete response dictionary ready to serialize to JSON
    """
    payload: dict[str, Any] = {
        "userMessage": user_message,
        "correlationId": get_correlation_id(),
    }
    if quick_replies is not None:
        payload["quickReplies"] = quick_replies
    if selection_lists is not None:
        payload["selectionLists"] = selection_lists
    if needs_clarification is not None:
        payload["needsClarification"] = needs_clarification
    if is_chronic_continuity is not None:
        payload["isChronicContinuity"] = is_chronic_continuity
    if continuity is not None:
        payload["continuity"] = continuity
    if show_consent_notice is not None:
        payload["showConsentNotice"] = show_consent_notice
    if requires_continuity_identity is not None:
        payload["requiresContinuityIdentity"] = requires_continuity_identity
    if booking_reference_id is not None:
        payload["bookingReferenceId"] = booking_reference_id
    if confirmation_type is not None:
        payload["confirmationType"] = confirmation_type
    if confirmation_summary is not None:
        payload["confirmationSummary"] = confirmation_summary
    if errors:
        payload["errors"] = errors
    return payload


def _build_slot_response(
    *,
    slot_result: dict,
    session: AssistantSession,
    user_message: str | None = None,
    continuity_message: str | None = None,
) -> dict:
    """Wrap slot lookup results into the common response shape.
    
    Converts raw slot lookup results (success or failure) into the standard
    chat API response format. Always includes continuity metadata so the UI
    can display the preferred practitioner state and availability.
    
    Args:
        slot_result: Result dict from scheduling service with items and reasonCode
        session: Patient session containing continuity preferences
        user_message: Optional custom message (uses default if omitted)
        continuity_message: Optional message about continuity preferences
        
    Returns:
        Standard response dict ready to send to client
    """
    preferred_has_availability = _preferred_practitioner_has_availability(
        items=slot_result.get("items", []),
        preferred_practitioner_ref=session.continuity_preferred_practitioner_ref,
    )
    continuity_payload = _build_continuity_payload(
        session=session,
        preferred_practitioner_has_availability=preferred_has_availability,
        message=continuity_message,
    )

    if slot_result["reasonCode"] != OK:
        message = slot_result.get("message") or _slot_failure_message(
            reason_code=slot_result["reasonCode"],
            specialty_id=session.selected_specialty_id,
        )
        return _response(
            user_message=message,
            is_chronic_continuity=session.continuity_is_returning,
            continuity=continuity_payload,
            errors=[
                {
                    "reasonCode": slot_result["reasonCode"],
                    "userMessage": message,
                }
            ],
        )

    default_message = (
        f"Choose one of the available {_humanize_specialty(session.selected_specialty_id or '')} slots."
    )
    return _response(
        user_message=user_message or default_message,
        selection_lists=_slot_selection_list(
            items=slot_result.get("items", []),
            preferred_practitioner_ref=session.continuity_preferred_practitioner_ref,
        ),
        is_chronic_continuity=session.continuity_is_returning,
        continuity=continuity_payload,
    )


def _transition_session(session: AssistantSession, target_state: str) -> None:
    """Advance the conversation state machine or raise a chat error.
    
    Updates the session's state by invoking the state machine transition logic.
    Catches state transition errors and converts them into user-facing
    ChatOrchestrationError exceptions with appropriate HTTP status codes.
    
    Args:
        session: Patient session to update
        target_state: Desired next state from the state machine
        
    Raises:
        ChatOrchestrationError: If the transition is not allowed
    """
    try:
        session.current_state = transition_or_raise(
            current_state=session.current_state,
            target_state=target_state,
        )
    except StateTransitionError as exc:
        raise ChatOrchestrationError(
            reason_code="INVALID_STATE_TRANSITION",
            user_message="This action is not allowed in the current conversation step.",
            status_code=409,
            details=str(exc),
        ) from exc


# ==============================================================================
# MAIN ORCHESTRATION ENDPOINTS
# ==============================================================================
# These are the primary entry points for the orchestration service. Each process_*
# function handles a specific conversation flow or action:
# - process_chat_message: NLP-driven appointment booking
# - process_direct_start: Manual specialty selection
# - process_renewal_request: Medication renewal flow
# - process_reset: Return to main menu
# - process_renewal_identity, process_continuity_identity: Identity verification
# - process_selection: Handle user selections (specialty, slot, medication)
# - process_confirm: Finalize appointment or renewal booking

async def process_chat_message(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
    message_text: str,
    nlp_service: NlpService | None,
) -> dict:
    """Classify a symptom complaint and route the patient into scheduling."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    clean_message_text = _normalize_message_text(message_text)

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )

    is_clarification_followup = bool(
        session.clarification_pending and session.original_complaint_text
    )

    session.flow_mode = "complaint"
    session.selected_slot_id = None
    _reset_continuity_context(session)

    if is_clarification_followup:
        # CLARIFICATION FLOW: Accumulate follow-up details and rerun NLP classification
        # with merged context (original complaint + new clarification details).
        # This helps the classifier make a more confident decision with additional info.
        session.clarification_detail_text = _append_clarification_detail(
            existing_detail_text=session.clarification_detail_text,
            new_detail_text=clean_message_text,
        )

        session.merged_classification_text = _merge_clarification_text(
            original_complaint=session.original_complaint_text or "",
            clarification_detail=session.clarification_detail_text or "",
        )

        classification_input = session.merged_classification_text
        session.last_input_summary = _safe_input_summary(classification_input)

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="CLARIFICATION_PROVIDED",
            outcome="INFO",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": _safe_text_summary(clean_message_text),
                "clarificationKey": session.clarification_key,
                "originalComplaintSummary": _safe_text_summary(
                    session.original_complaint_text or ""
                ),
                "clarificationDetailSummary": _safe_text_summary(
                    session.clarification_detail_text or ""
                ),
                "mergedInputSummary": _safe_text_summary(classification_input),
                "clarificationTurns": len(
                    [
                        line
                        for line in (session.clarification_detail_text or "").splitlines()
                        if line.strip()
                    ]
                ),
            },
        )
    else:
        session.original_complaint_text = clean_message_text
        session.clarification_detail_text = None
        session.merged_classification_text = clean_message_text
        session.last_input_summary = _safe_input_summary(clean_message_text)
        _clear_clarification_context(session)
        session.original_complaint_text = clean_message_text
        session.merged_classification_text = clean_message_text
        classification_input = clean_message_text

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="COMPLAINT_RECEIVED",
            outcome="INFO",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": session.last_input_summary,
            },
        )

    if nlp_service is None:
        # FALLBACK: NLP service unavailable - present all specialties for manual selection
        _transition_session(session, AWAITING_SPECIALTY_SELECTION)
        _save_session(db, session)
        return _response(
            user_message="The specialty model is not available right now. Please choose a specialty to continue.",
            selection_lists=_specialty_selection_list(),
            show_consent_notice=True,
            errors=[
                {
                    "reasonCode": "NLP_PROCESSING_FAILED",
                    "userMessage": "Manual specialty selection was enabled because the NLP model is unavailable.",
                }
            ],
        )

    prediction = nlp_service.classify(classification_input)

    candidates = _candidate_payload_from_prediction(prediction)

    nlp_preprocessed_payload = _build_nlp_preprocessed_payload(
        prediction=prediction,
        session=session,
        classification_input=classification_input,
        used_merged_clarification_input=is_clarification_followup,
    )

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=client_session_id,
        actor_type="system",
        event_type="NLP_PREPROCESSED",
        outcome="INFO",
        reason_code=OK,
        payload={
            **nlp_preprocessed_payload,
            "safeSummary": "Prepared complaint text for specialty classification.",
        },
    )

    nlp_classified_payload = _build_nlp_classified_payload(
        prediction=prediction,
        candidates=candidates,
        min_confidence=nlp_service.min_confidence,
        ambiguity_delta=nlp_service.ambiguity_delta,
    )

    ambiguity_decision = nlp_classified_payload["ambiguityDecision"]

    # Prepare summary for event logging based on whether clarification is needed
    if prediction.needs_clarification:
        # Classifier is uncertain - extract top candidates for user-friendly message
        top_labels = [item["id"] for item in candidates[:2]]
        if len(top_labels) == 2:
            safe_summary = (
                f"Ambiguous specialty prediction between "
                f"{_humanize_specialty(top_labels[0])} and {_humanize_specialty(top_labels[1])}."
            )
        else:
            safe_summary = "Ambiguous specialty prediction."
    else:
        # Classifier made a confident prediction
        safe_summary = (
            f"Predicted specialty {_humanize_specialty(prediction.primary_specialty_id or 'general_practice')}."
        )

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=client_session_id,
        actor_type="system",
        event_type="NLP_CLASSIFIED",
        outcome="SUCCESS",
        reason_code=prediction.reason_code,
        payload={
            **nlp_classified_payload,
            "safeSummary": safe_summary,
        },
    )


    if prediction.primary_specialty_id:
        session.selected_specialty_id = prediction.primary_specialty_id

    _transition_session(session, AWAITING_SPECIALTY_SELECTION)

    if prediction.needs_clarification:
        # AMBIGUITY HANDLING: Classifier uncertainty detected
        # Keep session in complaint flow and ask user for clarification details.
        # This allows the classifier to make a more confident decision with more context.
        if not session.original_complaint_text:
            session.original_complaint_text = clean_message_text

        session.clarification_pending = True
        session.clarification_key = prediction.clarification_key

        if ambiguity_decision == "below_min_confidence":
            clarification_summary = (
                "Clarification requested because specialty confidence remained below threshold."
            )
        elif ambiguity_decision == "gap_too_small":
            clarification_summary = (
                "Clarification requested because the top two specialties were too close."
            )
        elif ambiguity_decision == "both":
            clarification_summary = (
                "Clarification requested because confidence remained below threshold and the top two specialties were too close."
            )
        else:
            clarification_summary = (
                "Clarification requested before specialty confirmation."
            )

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="system",
            event_type="CLARIFICATION_REQUESTED",
            outcome="INFO",
            reason_code=prediction.reason_code,
            payload={
                "component": "assistant-api",
                "safeSummary": clarification_summary,
                "clarificationKey": prediction.clarification_key,
                "ambiguityDecision": ambiguity_decision,
                "topCandidates": candidates[:3],
            },
        )

        _save_session(db, session)

        quick_replies = [
            {
                "label": reply.label,
                "value": reply.value,
                "action": reply.action,
            }
            for reply in prediction.clarification_quick_replies
        ]

        return _response(
            user_message=prediction.clarifier_question
            or "I am not fully confident yet. Add more detail if you want, or choose one of the suggested specialties to continue.",
            quick_replies=quick_replies or None,
            selection_lists=_specialty_selection_list(candidates=candidates or None),
            needs_clarification=True,
            show_consent_notice=True,
        )

    session.clarification_pending = False
    session.clarification_key = None

    _save_session(db, session)

    specialty_label = _humanize_specialty(prediction.primary_specialty_id or "general_practice")
    return _response(
        user_message=f"I recommend {specialty_label}. Please confirm the specialty to continue.",
        selection_lists=_specialty_selection_list(candidates=candidates or None),
        show_consent_notice=True,
    )


async def process_direct_start(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
) -> dict:
    """Start a direct scheduling flow without NLP classification."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )
    session.flow_mode = "direct"
    session.selected_specialty_id = None
    session.selected_slot_id = None
    session.renewal_item_id = None
    _reset_continuity_context(session)

    _transition_session(session, AWAITING_SPECIALTY_SELECTION)
    _save_session(db, session)

    return _response(
        user_message="Choose the specialty you want to schedule.",
        selection_lists=_specialty_selection_list(),
        show_consent_notice=True,
    )


async def process_renewal_request(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
) -> dict:
    """Start the medication renewal flow."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )

    session.flow_mode = "renewal"
    session.renewal_item_id = None
    session.renewal_item_label = None
    session.renewal_patient_key_hash = None
    session.renewal_patient_ref = None

    _transition_session(session, AWAITING_RENEWAL_IDENTITY)

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=client_session_id,
        actor_type="patient",
        event_type="RENEWAL_REQUESTED",
        outcome="INFO",
        reason_code=OK,
        payload={
            "component": "assistant-api",
            "safeSummary": "Medication renewal flow started.",
        },
    )

    _save_session(db, session)

    return _response(
        user_message="Enter your National ID to retrieve your active medications eligible for renewal.",
        show_consent_notice=True,
    )

async def process_reset(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
) -> dict:
    """Return the session to the main menu and clear active flow state."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )

    previous_state = session.current_state or NEW
    previous_flow_mode = session.flow_mode
    had_active_flow = _session_has_active_flow(session)

    if had_active_flow:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="SESSION_DROPPED",
            outcome="INFO",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": "User returned to the main menu and reset the active flow.",
                "previousState": previous_state,
                "previousFlowMode": previous_flow_mode,
            },
        )

    _clear_session_flow_state(session)
    _save_session(db, session)

    return _response(
        user_message="Returned to the main menu. Choose how you would like to continue.",
    )

async def process_renewal_identity(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
    national_id: str,
) -> dict:
    """Verify the renewal identity and fetch eligible medication requests."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )

    try:
        normalized_identity_number, identity_type = validate_national_id_and_infer_type(
            national_id
        )
    except IdentityValidationError as exc:
        raise ChatOrchestrationError(
            reason_code="INVALID_IDENTITY_NUMBER",
            user_message="National ID, iqama, or Border ID is invalid.",
            status_code=422,
            details=exc.message,
        ) from exc

    patient_key_hash = build_patient_key_hash(
        tenant_id=body_tenant_id,
        identity_type=identity_type,
        normalized_identity_number=normalized_identity_number,
    )

    fhir_client = FhirClient()
    renewal_signals = await fhir_client.get_medication_renewal_signals(
        patient_key_hash=patient_key_hash
    )

    session.renewal_patient_key_hash = patient_key_hash
    session.renewal_patient_ref = renewal_signals.patientRef

    if not renewal_signals.patientFound:
        # Keep the session context intact so the patient can correct the ID without restarting.
        _save_session(db, session)
        return _response(
            user_message="No patient record was found for that ID. Please check the ID and try again.",
            errors=[
                {
                    "reasonCode": "PATIENT_NOT_FOUND",
                    "userMessage": "No patient record was found for that ID.",
                }
            ],
        )

    if not renewal_signals.eligible or not renewal_signals.items:
        # A found patient may still have no eligible refills, so surface that separately.
        _save_session(db, session)
        return _response(
            user_message="No active medication requests eligible for renewal were found.",
            errors=[
                {
                    "reasonCode": "NO_RENEWAL_ITEMS_AVAILABLE",
                    "userMessage": "No active medication requests eligible for renewal were found.",
                }
            ],
        )

    _transition_session(session, AWAITING_RENEWAL_SELECTION)

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=client_session_id,
        actor_type="system",
        event_type="RENEWAL_SIGNALS_RETRIEVED",
        outcome="SUCCESS",
        reason_code=OK,
        payload={
            "component": "assistant-api",
            "safeSummary": f"Retrieved {len(renewal_signals.items)} renewal candidates.",
        },
    )

    _save_session(db, session)

    return _response(
        user_message="Choose the medication you want to renew.",
        selection_lists=_renewal_items_selection_list(renewal_signals.items),
        show_consent_notice=True,
    )


async def process_continuity_identity(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
    national_id: str,
) -> dict:
    """Verify continuity-of-care identity and load prioritized slots."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )

    if not session.selected_specialty_id:
        raise ChatOrchestrationError(
            reason_code="INVALID_REQUEST",
            user_message="A specialty must be selected before continuity lookup.",
            status_code=422,
        )

    try:
        normalized_identity_number, identity_type = validate_national_id_and_infer_type(
            national_id
        )
    except IdentityValidationError as exc:
        raise ChatOrchestrationError(
            reason_code="INVALID_IDENTITY_NUMBER",
            user_message="National ID, iqama, or Border ID is invalid.",
            status_code=422,
            details=exc.message,
        ) from exc

    patient_key_hash = build_patient_key_hash(
        tenant_id=body_tenant_id,
        identity_type=identity_type,
        normalized_identity_number=normalized_identity_number,
    )

    fhir_client = FhirClient()

    continuity_patient_ref: str | None = None
    preferred_practitioner_ref: str | None = None
    preferred_practitioner_display: str | None = None

    try:
        patient = await fhir_client.get_patient_or_raise(
            tenant_id=body_tenant_id,
            patient_key_hash=patient_key_hash,
        )
        continuity_patient_ref = patient.patientRef

        continuity = await fhir_client.get_continuity_signals(
            patient_ref=patient.patientRef,
            specialty=session.selected_specialty_id,
        )

        if continuity and continuity.hasPriorAppointments and continuity.lastPractitionerRef:
            preferred_practitioner_ref = continuity.lastPractitionerRef
            preferred_practitioner_display = continuity.lastPractitionerDisplay

    except Exception:
        # If continuity lookup fails, fall back to the standard slot flow instead of blocking scheduling.
        continuity_patient_ref = None
        preferred_practitioner_ref = None
        preferred_practitioner_display = None

    session.continuity_checked = True
    session.continuity_patient_ref = continuity_patient_ref
    session.continuity_preferred_practitioner_ref = preferred_practitioner_ref
    session.continuity_preferred_practitioner_display = preferred_practitioner_display
    session.continuity_is_returning = bool(preferred_practitioner_ref)

    if session.continuity_is_returning:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="system",
            event_type="CONTINUITY_DETECTED",
            outcome="SUCCESS",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": (
                    f"Continuity of care matched previous physician: "
                    f"{preferred_practitioner_display or preferred_practitioner_ref}"
                ),
            },
        )
    else:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="system",
            event_type="CONTINUITY_NOT_FOUND",
            outcome="INFO",
            reason_code="NO_CONTINUITY_MATCH",
            payload={
                "component": "assistant-api",
                "safeSummary": "No same-specialty continuity-of-care match found.",
            },
        )

    _transition_session(session, AWAITING_SLOT_SELECTION)
    _save_session(db, session)

    slot_result = await _load_slots_for_session(
        db=db,
        header_tenant_id=header_tenant_id,
        header_session_id=header_session_id,
        body_tenant_id=body_tenant_id,
        session=session,
    )

    if session.continuity_is_returning:
        label = preferred_practitioner_display or "your previous physician"
        message = f"Continuity of care found. {label} has been prioritized when available."
        return _build_slot_response(
            slot_result=slot_result,
            session=session,
            user_message=message,
            continuity_message=message,
        )

    message = (
        f"No matching continuity-of-care record was found. "
        f"Showing available {_humanize_specialty(session.selected_specialty_id)} slots."
    )
    return _build_slot_response(
        slot_result=slot_result,
        session=session,
        user_message=message,
        continuity_message=message,
    )

async def process_selection(
    *,
    db: Session,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
    selection_type: str,
    selection_id: str | None,
    selection_value: str | None,
    action: str,
) -> dict:
    """Handle specialty, slot, medication, and continuity selection events."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )

    normalized_selection_type = selection_type.strip().lower()
    normalized_action = action.strip().upper()
    resolved_selection_id = (selection_id or "").strip()
    resolved_selection_value = (selection_value or "").strip() or None

    if normalized_selection_type == "specialty":
        # Specialty selection may lead into continuity screening before slot retrieval.
        if not resolved_selection_id:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="A specialty must be selected.",
                status_code=422,
            )

        new_specialty_id = resolved_selection_id.lower()

        if session.selected_specialty_id != new_specialty_id:
            session.selected_slot_id = None
            _reset_continuity_context(session)

        session.selected_specialty_id = new_specialty_id

        if session.flow_mode == "direct":
            selection_source = "direct_specialty_selection"
        elif session.clarification_pending:
            selection_source = "post_clarification_suggestion_list"
        else:
            selection_source = "specialty_suggestion_list"

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="SPECIALTY_SELECTED",
            outcome="INFO",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": (
                    f"User selected {_humanize_specialty(new_specialty_id)} from the specialty list."
                ),
                "selectedSpecialty": new_specialty_id,
                "selectionSource": selection_source,
            },
        )

        session.clarification_pending = False
        session.clarification_key = None

        if session.flow_mode in {"complaint", "direct"} and not session.continuity_checked:
            _transition_session(session, AWAITING_CONTINUITY_IDENTITY)

            emit_event(
                db=db,
                tenant_id=body_tenant_id,
                session_id=client_session_id,
                actor_type="system",
                event_type="CONTINUITY_CHECK_REQUESTED",
                outcome="INFO",
                reason_code=OK,
                payload={
                    "component": "assistant-api",
                    "safeSummary": (
                        f"Continuity-of-care identity step requested for "
                        f"{session.selected_specialty_id}."
                    ),
                },
            )

            _save_session(db, session)

            return _response(
                user_message=(
                    "To prioritize continuity of care, enter your National ID / Iqama / Border ID. "
                    "You can also skip this step and see all available slots."
                ),
                requires_continuity_identity=True,
            )

        _transition_session(session, AWAITING_SLOT_SELECTION)
        _save_session(db, session)

        slot_result = await _load_slots_for_session(
            db=db,
            header_tenant_id=header_tenant_id,
            header_session_id=header_session_id,
            body_tenant_id=body_tenant_id,
            session=session,
        )

        return _build_slot_response(slot_result=slot_result, session=session)

    if normalized_selection_type == "slot":
        if not resolved_selection_id:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="A slot must be selected.",
                status_code=422,
            )

        session.selected_slot_id = resolved_selection_id
        _transition_session(session, AWAITING_CONFIRMATION)
        _save_session(db, session)

        return _response(
            user_message="Slot captured. Continue to identity verification to receive your OTP code.",
        )

    if normalized_selection_type == "medication":
        if not resolved_selection_id:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="A medication must be selected.",
                status_code=422,
            )

        session.renewal_item_id = resolved_selection_id
        session.renewal_item_label = resolved_selection_value or resolved_selection_id

        _transition_session(session, AWAITING_CONFIRMATION)

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="RENEWAL_ITEM_SELECTED",
            outcome="SUCCESS",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": f"Renewal item selected: {session.renewal_item_label}",
            },
        )

        _save_session(db, session)

        return _response(
            user_message="Medication captured. Continue to identity verification to receive your OTP code.",
        )

    if normalized_selection_type == "continuity":
        # Skipping continuity still advances the conversation to normal slot selection.
        if normalized_action != "SKIP_CONTINUITY_CHECK":
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="Unsupported continuity action.",
                status_code=422,
            )

        if not session.selected_specialty_id:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="Select a specialty before skipping continuity.",
                status_code=422,
            )

        session.continuity_checked = True
        session.continuity_is_returning = False
        session.continuity_patient_ref = None
        session.continuity_preferred_practitioner_ref = None
        session.continuity_preferred_practitioner_display = None

        _transition_session(session, AWAITING_SLOT_SELECTION)

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="patient",
            event_type="CONTINUITY_SKIPPED",
            outcome="INFO",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": "Patient skipped continuity identity step.",
            },
        )

        _save_session(db, session)

        slot_result = await _load_slots_for_session(
            db=db,
            header_tenant_id=header_tenant_id,
            header_session_id=header_session_id,
            body_tenant_id=body_tenant_id,
            session=session,
        )

        return _build_slot_response(
            slot_result=slot_result,
            session=session,
            user_message=f"Showing all available {_humanize_specialty(session.selected_specialty_id)} slots.",
        )

    raise ChatOrchestrationError(
        reason_code="INVALID_REQUEST",
        user_message="Unsupported selection type.",
        status_code=422,
    )


async def process_confirm(
    *,
    db: Session,
    background_tasks: BackgroundTasks | None,
    header_tenant_id: str,
    header_session_id: str,
    body_tenant_id: str,
    client_session_id: str,
    action: str,
    specialty_id: str | None,
    slot_id: str | None,
    national_id: str | None,
    email: str | None,
    renewal_item_id: str | None,
    idempotency_key: str | None,
) -> dict:
    """Finalize an appointment or renewal after identity verification."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(
        header_session_id=header_session_id,
        client_session_id=client_session_id,
    )

    session, _ = _get_or_create_session(
        db=db,
        tenant_id=body_tenant_id,
        client_session_id=client_session_id,
    )
    normalized_action = action.strip().upper()

    if normalized_action == "CONFIRM_APPOINTMENT":
        # Appointment confirmation validates identity and books the selected slot atomically.
        resolved_specialty_id = (specialty_id or session.selected_specialty_id or "").strip().lower()
        resolved_slot_id = (slot_id or session.selected_slot_id or "").strip()

        if not resolved_specialty_id or not resolved_slot_id:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="Specialty and slot must be selected before confirmation.",
                status_code=422,
            )

        if not national_id or not national_id.strip() or not email or not email.strip():
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="National ID and email are required before booking confirmation.",
                status_code=422,
            )

        try:
            booking_result = await book_appointment(
                db=db,
                header_tenant_id=header_tenant_id,
                session_id=header_session_id,
                body_tenant_id=body_tenant_id,
                national_id=national_id,
                email=email,
                specialty=resolved_specialty_id,
                slot_id=resolved_slot_id,
                idempotency_key=idempotency_key,
            )
        except SchedulingError as exc:
            raise ChatOrchestrationError(
                reason_code=exc.reason_code,
                user_message=exc.user_message,
                status_code=exc.status_code,
                details=exc.details,
            ) from exc

        if booking_result["reasonCode"] != OK:
            # A failed booking may still leave the original slot choices available, so refresh them.
            refreshed_slots = await _load_slots_for_session(
                db=db,
                header_tenant_id=header_tenant_id,
                header_session_id=header_session_id,
                body_tenant_id=body_tenant_id,
                session=session,
            )

            message = booking_result["message"]
            return _response(
                user_message=message,
                selection_lists=(
                    _slot_selection_list(items=refreshed_slots.get("items", []))
                    if refreshed_slots.get("items")
                    else None
                ),
                is_chronic_continuity=session.continuity_is_returning,
                errors=[
                    {
                        "reasonCode": booking_result["reasonCode"],
                        "userMessage": message,
                    }
                ],
            )

        slot = booking_result["slot"]
        summary = ConfirmationSummary(
            bookingReferenceId=booking_result["appointmentRef"],
            correlationId=get_correlation_id(),
            doctorLabel=slot.get("practitionerDisplay"),
            specialtyLabel=_humanize_specialty(booking_result["specialty"]),
            date=slot.get("startUtc"),
            slotLabel=slot.get("slotRef"),
        )

        _transition_session(session, COMPLETED)

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="system",
            event_type="SESSION_COMPLETED",
            outcome="SUCCESS",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": "Complaint-based scheduling flow completed successfully.",
            },
        )

        _save_session(db, session)

        queue_appointment_confirmation_email(
            background_tasks=background_tasks,
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            correlation_id=get_correlation_id(),
            to_email=normalize_email(email),
            booking_reference_id=booking_result["appointmentRef"],
            doctor_label=slot.get("practitionerDisplay"),
            specialty_label=_humanize_specialty(booking_result["specialty"]),
            date_utc=slot.get("startUtc"),
            slot_label=slot.get("slotRef"),
        )

        return _response(
            user_message=booking_result["message"],
            booking_reference_id=booking_result["appointmentRef"],
            confirmation_type="appointment",
            confirmation_summary=summary.model_dump(exclude_none=True),
        )

    if normalized_action == "CONFIRM_RENEWAL":
        # Renewal confirmation rechecks the verified identity against the stored renewal context.
        resolved_renewal_item_id = (renewal_item_id or session.renewal_item_id or "").strip()
        resolved_renewal_item_label = (
            (session.renewal_item_label or "").strip() or resolved_renewal_item_id
        )

        if not resolved_renewal_item_id:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="A medication must be selected before renewal confirmation.",
                status_code=422,
            )

        if not national_id or not national_id.strip() or not email or not email.strip():
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="National ID and email are required before renewal confirmation.",
                status_code=422,
            )

        normalized_email_value = normalize_email(email)

        try:
            normalized_identity_number, identity_type = validate_national_id_and_infer_type(
                national_id
            )
        except IdentityValidationError as exc:
            raise ChatOrchestrationError(
                reason_code="INVALID_IDENTITY_NUMBER",
                user_message="National ID, iqama, or Border ID is invalid.",
                status_code=422,
                details=exc.message,
            ) from exc

        patient_key_hash = build_patient_key_hash(
            tenant_id=body_tenant_id,
            identity_type=identity_type,
            normalized_identity_number=normalized_identity_number,
        )

        try:
            ensure_verified_otp_or_raise(
                db=db,
                tenant_id=body_tenant_id,
                session_id=header_session_id,
                patient_key_hash=patient_key_hash,
                email=normalized_email_value,
            )
        except SchedulingError as exc:
            raise ChatOrchestrationError(
                reason_code=exc.reason_code,
                user_message=exc.user_message,
                status_code=exc.status_code,
                details=exc.details,
            ) from exc

        if session.renewal_patient_key_hash and session.renewal_patient_key_hash != patient_key_hash:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="The verified identity does not match the renewal request identity.",
                status_code=409,
            )

        if not session.renewal_patient_ref:
            raise ChatOrchestrationError(
                reason_code="PATIENT_NOT_FOUND",
                user_message="Patient record is required before submitting a refill request.",
                status_code=409,
            )

        fhir_client = FhirClient()

        try:
            renewal_signals = await fhir_client.get_medication_renewal_signals(
                patient_key_hash=patient_key_hash,
            )
        except FhirGatewayError as exc:
            raise ChatOrchestrationError(
                reason_code=exc.reason_code,
                user_message="Medication refill candidates could not be revalidated.",
                status_code=exc.status_code,
                details=exc.details,
            ) from exc

        selected_renewal_item = _find_selected_renewal_item(
            renewal_signals.items,
            resolved_renewal_item_id,
        )

        if selected_renewal_item is None:
            raise ChatOrchestrationError(
                reason_code="INVALID_REQUEST",
                user_message="Selected medication is no longer available for refill request submission.",
                status_code=409,
            )

        try:
            refill_task = await fhir_client.create_medication_refill_task(
                patient_ref=session.renewal_patient_ref,
                medication_request_ref=resolved_renewal_item_id,
                medication_label=resolved_renewal_item_label,
                refill_status=getattr(selected_renewal_item, "refillStatus", None),
                refill_status_message=getattr(selected_renewal_item, "refillStatusMessage", None),
                correlation_id=get_correlation_id(),
            )
        except FhirGatewayError as exc:
            # Emit a failure event before surfacing the error so downstream observability keeps the attempt.
            emit_event(
                db=db,
                tenant_id=body_tenant_id,
                session_id=client_session_id,
                actor_type="system",
                event_type="SESSION_DROPPED",
                outcome="FAILURE",
                reason_code=exc.reason_code,
                payload={
                    "component": "assistant-api",
                    "safeSummary": "Medication refill request could not be submitted to FHIR.",
                },
            )
            db.commit()
            raise ChatOrchestrationError(
                reason_code=exc.reason_code,
                user_message="Medication refill request could not be submitted. Please try again later.",
                status_code=exc.status_code,
                details=exc.details,
            ) from exc

        _transition_session(session, COMPLETED)

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            actor_type="system",
            event_type="SESSION_COMPLETED",
            outcome="SUCCESS",
            reason_code=OK,
            payload={
                "component": "assistant-api",
                "safeSummary": "Medication refill request submitted for clinical/pharmacy fulfillment.",
                "renewalItemLabel": resolved_renewal_item_label,
                "renewalItemId": resolved_renewal_item_id,
                "refillTaskRef": refill_task.taskRef,
            },
        )

        _save_session(db, session)

        summary = ConfirmationSummary(
            correlationId=get_correlation_id(),
            renewalItemLabel=resolved_renewal_item_label,
            refillTaskRef=refill_task.taskRef,
        )

        queue_renewal_confirmation_email(
            background_tasks=background_tasks,
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            correlation_id=get_correlation_id(),
            to_email=normalize_email(email),
            renewal_item_label=resolved_renewal_item_label,
            refill_task_ref=refill_task.taskRef,
        )

        return _response(
            user_message=(
                "Medication refill request submitted successfully and is pending "
                "clinical/pharmacy fulfillment."
            ),
            confirmation_type="renewal",
            confirmation_summary=summary.model_dump(exclude_none=True),
        )

    raise ChatOrchestrationError(
        reason_code="INVALID_REQUEST",
        user_message="Unsupported confirmation action.",
        status_code=422,
    )