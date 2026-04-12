from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.api.schemas.chat import ConfirmationSummary
from app.core.correlation import get_correlation_id
from app.db.models import AssistantSession
from app.modules.fhir_gateway.client import FhirClient
from app.modules.nlp.inference import NlpService, _safe_input_summary
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
from app.modules.scheduling.reason_codes import OK, SchedulingError
from app.modules.scheduling.service import (
    book_appointment,
    ensure_verified_otp_or_raise,
    list_available_slots,
)
from app.modules.orchestration.state_machine import (
    AWAITING_CONFIRMATION,
    AWAITING_RENEWAL_IDENTITY,
    AWAITING_RENEWAL_SELECTION,
    AWAITING_SLOT_SELECTION,
    AWAITING_SPECIALTY_SELECTION,
    COMPLETED,
    NEW,
    StateTransitionError,
    transition_or_raise,
)

PROVIDERS_PATH = Path(__file__).resolve().parents[1] / "scheduling" / "providers_static.json"

def _renewal_items_selection_list(items: list) -> list[dict]:
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
    payload: dict = {
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


from dataclasses import asdict, is_dataclass
from typing import Any, Mapping


def _slot_to_mapping(slot: Any) -> dict[str, Any]:
    """
    Normalize a slot-like object into a plain dictionary.

    This supports:
    - dict payloads
    - Pydantic models with model_dump()
    - older Pydantic models with dict()
    - dataclass instances
    - plain Python objects with expected attributes

    Why this exists:
    The scheduling layer returns normalized SlotDTO objects.
    The orchestration layer should not assume those items are always dicts.
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
    """
    Return the first non-None value found under the candidate keys.
    """
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _slot_selection_list(*, items: list[Any]) -> list[dict]:
    """
    Convert scheduling results into the UI-safe slot selection list contract.

    This now accepts SlotDTO objects as well as dicts.
    """
    slot_items: list[dict] = []

    for raw_slot in items:
        slot = _slot_to_mapping(raw_slot)

        slot_id = _pick(slot, "slotId", "slot_id", "id")
        slot_ref = _pick(slot, "slotRef", "slot_ref")
        practitioner_display = _pick(
            slot,
            "practitionerDisplay",
            "practitioner_display",
        )
        specialty = _pick(slot, "specialty")
        iso_start = _pick(slot, "startUtc", "start_utc")
        iso_end = _pick(slot, "endUtc", "end_utc")

        start_label = (
            str(iso_start).replace("T", " ").replace("Z", " UTC")
            if iso_start
            else "Unknown start time"
        )

        end_label = (
            str(iso_end).split("T", 1)[1].replace("Z", " UTC")
            if iso_end and "T" in str(iso_end)
            else (str(iso_end).replace("Z", " UTC") if iso_end else None)
        )

        label = f"{practitioner_display or 'Available doctor'} • {start_label}"

        slot_items.append(
            _selection_item(
                item_id=str(slot_id or slot_ref or ""),
                label=label,
                description=f"{_humanize_specialty(str(specialty or ''))} appointment slot.",
                meta={
                    "isoDate": str(iso_start) if iso_start else None,
                    "startTime": start_label,
                    "endTime": end_label,
                    "timezone": "UTC",
                },
            )
        )

    return [{"type": "slot", "items": slot_items}]





def _get_or_create_session(*, db: Session, tenant_id: str, client_session_id: str) -> tuple[AssistantSession, bool]:
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


def _response(
    *,
    user_message: str,
    selection_lists: list[dict] | None = None,
    needs_clarification: bool | None = None,
    show_consent_notice: bool | None = None,
    booking_reference_id: str | None = None,
    confirmation_type: str | None = None,
    confirmation_summary: dict | None = None,
    errors: list[dict] | None = None,
) -> dict:
    payload: dict = {
        "userMessage": user_message,
        "correlationId": get_correlation_id(),
    }
    if selection_lists is not None:
        payload["selectionLists"] = selection_lists
    if needs_clarification is not None:
        payload["needsClarification"] = needs_clarification
    if show_consent_notice is not None:
        payload["showConsentNotice"] = show_consent_notice
    if booking_reference_id is not None:
        payload["bookingReferenceId"] = booking_reference_id
    if confirmation_type is not None:
        payload["confirmationType"] = confirmation_type
    if confirmation_summary is not None:
        payload["confirmationSummary"] = confirmation_summary
    if errors:
        payload["errors"] = errors
    return payload


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
    ensure_tenant_header_matches_body(header_tenant_id=header_tenant_id, body_tenant_id=body_tenant_id)
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(header_session_id=header_session_id, client_session_id=client_session_id)

    session, _ = _get_or_create_session(db=db, tenant_id=body_tenant_id, client_session_id=client_session_id)
    session.flow_mode = "complaint"
    session.last_input_summary = _safe_input_summary(message_text)

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

    prediction = nlp_service.classify(message_text)
    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=client_session_id,
        actor_type="system",
        event_type="NLP_CLASSIFIED",
        outcome="SUCCESS",
        reason_code=prediction.reason_code,
        payload={
            "component": "nlp",
            "safeSummary": f"Predicted {prediction.primary_specialty_id or 'manual selection'}.",
            "modelVersion": prediction.model_version,
        },
    )

    candidates = [
        {"id": candidate.specialty_id, "confidence": round(candidate.confidence, 4)}
        for candidate in prediction.top_candidates
    ]
    if prediction.primary_specialty_id:
        session.selected_specialty_id = prediction.primary_specialty_id
    _transition_session(session, AWAITING_SPECIALTY_SELECTION)
    _save_session(db, session)

    if prediction.needs_clarification:
        return _response(
            user_message=prediction.clarifier_question or "Please choose the specialty that best matches your concern.",
            selection_lists=_specialty_selection_list(candidates=candidates or None),
            needs_clarification=True,
            show_consent_notice=True,
        )

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
    ensure_tenant_header_matches_body(header_tenant_id=header_tenant_id, body_tenant_id=body_tenant_id)
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(header_session_id=header_session_id, client_session_id=client_session_id)

    session, _ = _get_or_create_session(db=db, tenant_id=body_tenant_id, client_session_id=client_session_id)
    session.flow_mode = "direct"
    session.selected_specialty_id = None
    session.selected_slot_id = None
    session.renewal_item_id = None
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

        session.selected_specialty_id = resolved_selection_id.lower()

        slot_result = await list_available_slots(
            db=db,
            header_tenant_id=header_tenant_id,
            session_id=header_session_id,
            body_tenant_id=body_tenant_id,
            specialty=session.selected_specialty_id,
        )

        if slot_result["reasonCode"] != OK:
            return _response(
                user_message=slot_result["message"],
                errors=[
                    {
                        "reasonCode": slot_result["reasonCode"],
                        "userMessage": slot_result["message"],
                    }
                ],
            )

        _transition_session(session, AWAITING_SLOT_SELECTION)
        _save_session(db, session)

        return _response(
            user_message=f"Choose one of the available {_humanize_specialty(session.selected_specialty_id)} slots.",
            selection_lists=_slot_selection_list(items=slot_result.get("items", [])),
        )

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

    raise ChatOrchestrationError(
        reason_code="INVALID_REQUEST",
        user_message="Unsupported selection type.",
        status_code=422,
    )


async def process_confirm(
    *,
    db: Session,
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
    ensure_tenant_header_matches_body(header_tenant_id=header_tenant_id, body_tenant_id=body_tenant_id)
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)
    _ensure_client_session_matches_header(header_session_id=header_session_id, client_session_id=client_session_id)

    session, _ = _get_or_create_session(db=db, tenant_id=body_tenant_id, client_session_id=client_session_id)
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
            refreshed_slots = await list_available_slots(
                db=db,
                header_tenant_id=header_tenant_id,
                session_id=header_session_id,
                body_tenant_id=body_tenant_id,
                specialty=resolved_specialty_id,
            )
            return _response(
                user_message=booking_result["message"],
                selection_lists=_slot_selection_list(items=refreshed_slots.get("items", [])) if refreshed_slots.get("items") else None,
                errors=[
                    {
                        "reasonCode": booking_result["reasonCode"],
                        "userMessage": booking_result["message"],
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
                "safeSummary": "Complaint or direct scheduling flow completed.",
            },
        )
        _save_session(db, session)
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

        normalized_email = normalize_email(email)

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
                email=normalized_email,
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
                "safeSummary": "Medication renewal flow completed.",
            },
        )

        _save_session(db, session)

        summary = ConfirmationSummary(
            correlationId=get_correlation_id(),
            renewalItemLabel=resolved_renewal_item_label,
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