from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from fastapi import BackgroundTasks

from sqlalchemy.orm import Session

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


@dataclass(frozen=True)
class ChatOrchestrationError(Exception):
    reason_code: str
    user_message: str
    status_code: int = 400
    details: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _humanize_specialty(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _normalize_specialty_token(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().replace("_", " ").lower()


def _find_latest_matching_appointment(appointments: list[Any], specialty_id: str | None) -> Any | None:
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
    return (value or "").strip()


def _merge_clarification_text(*, original_complaint: str, clarification_detail: str) -> str:
    original = _normalize_message_text(original_complaint)
    detail = _normalize_message_text(clarification_detail)

    if not original:
        return detail
    if not detail:
        return original

    return (
        f"Original complaint: {original}\n"
        f"Clarification detail: {detail}"
    )


def _clear_clarification_context(session: AssistantSession) -> None:
    session.clarification_pending = False
    session.clarification_key = None
    session.original_complaint_text = None
    session.clarification_detail_text = None
    session.merged_classification_text = None

def _candidate_payload_from_prediction(prediction: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": candidate.specialty_id,
            "confidence": round(candidate.confidence, 4),
        }
        for candidate in prediction.top_candidates
    ]


def _classification_diagnostics(
    prediction: Any,
    *,
    min_confidence: float,
    ambiguity_delta: float,
) -> dict[str, Any]:
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
    with PROVIDERS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


SUPPORTED_SPECIALTIES = _load_supported_specialties()


def _ensure_client_session_matches_header(*, header_session_id: str, client_session_id: str) -> None:
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
    return [
        {
            "type": "medication",
            "items": [
                _selection_item(
                    item_id=item.medicationRequestRef,
                    label=item.medicationDisplay,
                    description=item.dosageText or "Eligible for renewal request.",
                )
                for item in items
            ],
        }
    ]


def _slot_to_mapping(slot: Any) -> dict[str, Any]:
    """
    Normalize a slot-like object into a plain dictionary.

    This supports:
    - dict payloads
    - Pydantic models with model_dump()
    - older Pydantic models with dict()
    - dataclass instances
    - plain Python objects with expected attributes
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
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None

def _parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _format_slot_start_label(value: str | None) -> str:
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return str(value or "Unknown start time")
    return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_slot_end_label(value: str | None) -> str | None:
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return str(value).replace("Z", " UTC") if value else None
    return parsed.strftime("%H:%M:%S UTC")


def _format_display_date(value: str | None) -> str | None:
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return value[:10] if value else None
    return parsed.strftime("%a %d %b %Y")


def _format_display_time(value: str | None) -> str | None:
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return None
    return parsed.strftime("%I:%M %p").lstrip("0")


def _date_key_from_iso(value: str | None) -> str | None:
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return value[:10] if value else None
    return parsed.strftime("%Y-%m-%d")


def _preferred_practitioner_has_availability(
    *,
    items: list[Any],
    preferred_practitioner_ref: str | None,
) -> bool | None:
    if not preferred_practitioner_ref:
        return None

    for raw_slot in items:
        slot = _slot_to_mapping(raw_slot)
        practitioner_ref = str(_pick(slot, "practitionerRef", "practitioner_ref") or "")
        if practitioner_ref == preferred_practitioner_ref:
            return True

    return False


def _build_continuity_payload(
    *,
    session: AssistantSession,
    preferred_practitioner_has_availability: bool | None,
    message: str | None,
) -> dict | None:
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


def _get_or_create_session(
    *,
    db: Session,
    tenant_id: str,
    client_session_id: str,
) -> tuple[AssistantSession, bool]:
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
    session.updated_at_utc = _utcnow()
    db.add(session)
    db.commit()
    db.refresh(session)

def _clear_session_flow_state(session: AssistantSession) -> None:
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
    session.continuity_checked = False
    session.continuity_patient_ref = None
    session.continuity_preferred_practitioner_ref = None
    session.continuity_preferred_practitioner_display = None
    session.continuity_is_returning = False


def _slot_failure_message(*, reason_code: str, specialty_id: str | None) -> str:
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

    if prediction.needs_clarification:
        top_labels = [item["id"] for item in candidates[:2]]
        if len(top_labels) == 2:
            safe_summary = (
                f"Ambiguous specialty prediction between "
                f"{_humanize_specialty(top_labels[0])} and {_humanize_specialty(top_labels[1])}."
            )
        else:
            safe_summary = "Ambiguous specialty prediction."
    else:
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
                "safeSummary": "Medication renewal flow completed successfully.",
            },
        )

        _save_session(db, session)

        summary = ConfirmationSummary(
            correlationId=get_correlation_id(),
            renewalItemLabel=resolved_renewal_item_label,
        )

        queue_renewal_confirmation_email(
            background_tasks=background_tasks,
            db=db,
            tenant_id=body_tenant_id,
            session_id=client_session_id,
            correlation_id=get_correlation_id(),
            to_email=normalize_email(email),
            renewal_item_label=resolved_renewal_item_label,
        )

        return _response(
            user_message="Medication renewal request recorded successfully.",
            confirmation_type="renewal",
            confirmation_summary=summary.model_dump(exclude_none=True),
        )

    raise ChatOrchestrationError(
        reason_code="INVALID_REQUEST",
        user_message="Unsupported confirmation action.",
        status_code=422,
    )