from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.schemas.auth import AuthenticatedPortalUser
from app.core.config import settings
from app.db.models import AssistantSession, Event, Tenant
APPOINTMENT_REF_RE = re.compile(r"(Appointment/[A-Za-z0-9._-]+)")


def _utc_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _range_bounds(from_date: str, to_date: str) -> tuple[datetime, datetime]:
    start_date = date.fromisoformat(from_date)
    end_date = date.fromisoformat(to_date)

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def _humanize_specialty(value: str | None) -> str:
    if not value:
        return "Unknown"
    return value.replace("_", " ").strip().title()


def _payload_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_summary(event: Event) -> str:
    payload = _payload_dict(event.payload_json)
    summary = payload.get("safeSummary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return event.event_type.replace("_", " ").title()


def _component_name(event: Event) -> str:
    payload = _payload_dict(event.payload_json)
    component = payload.get("component")
    if isinstance(component, str) and component.strip():
        return component.strip()
    return event.actor_type


def _stringify_trace_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _format_top_candidates(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None

    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        specialty_id = str(item.get("id") or "").strip()
        confidence = item.get("confidence")
        if not specialty_id:
            continue

        label = _humanize_specialty(specialty_id)
        if confidence is None:
            parts.append(label)
        else:
            parts.append(f"{label} ({confidence})")

    return "; ".join(parts) if parts else None


def _trace_details(event: Event) -> dict[str, str] | None:
    payload = _payload_dict(event.payload_json)
    details: dict[str, str] = {}

    scalar_fields = [
        ("Initial complaint summary", "originalComplaintSummary"),
        ("Classifier input summary", "classifierInputSummary"),
        ("Cleaned input summary", "cleanedInputSummary"),
        ("Normalized input summary", "normalizedInputSummary"),
        ("Clarification detail", "clarificationDetailSummary"),
        ("Merged input summary", "mergedInputSummary"),
        ("Clarification key", "clarificationKey"),
        ("Used merged clarification input", "usedMergedClarificationInput"),
        ("Clarification turns", "clarificationTurns"),
        ("Model version", "modelVersion"),
        ("Top confidence", "topConfidence"),
        ("Second confidence", "secondConfidence"),
        ("Confidence gap", "confidenceGap"),
        ("Threshold min confidence", "thresholdMinConfidence"),
        ("Threshold ambiguity delta", "thresholdAmbiguityDelta"),
        ("Ambiguity decision", "ambiguityDecision"),
        ("Predicted specialty", "predictedSpecialty"),
        ("Selected specialty", "selectedSpecialty"),
        ("Selection source", "selectionSource"),
        ("Notification type", "notificationType"),
        ("Channel", "channel"),
        ("Recipient email", "recipientEmailMasked"),
        ("Booking reference", "bookingReferenceId"),
        ("Renewal item label", "renewalItemLabel"),
    ]

    for label, key in scalar_fields:
        rendered = _stringify_trace_value(payload.get(key))
        if rendered:
            details[label] = rendered

    preprocessing_actions = payload.get("preprocessingActions")
    if isinstance(preprocessing_actions, list) and preprocessing_actions:
        rendered_actions = ", ".join(
            str(item).strip() for item in preprocessing_actions if str(item).strip()
        )
        if rendered_actions:
            details["Preprocessing actions"] = rendered_actions

    top_candidates = _format_top_candidates(payload.get("topCandidates"))
    if top_candidates:
        details["Top candidates"] = top_candidates

    return details or None

def _tenant_created_at(*, db: Session, tenant_id: str) -> str:
    first_session = (
        db.query(func.min(AssistantSession.created_at_utc))
        .filter(AssistantSession.tenant_id == tenant_id)
        .scalar()
    )
    first_event = (
        db.query(func.min(Event.ts_utc))
        .filter(Event.tenant_id == tenant_id)
        .scalar()
    )

    candidates = [value for value in [first_session, first_event] if value is not None]
    if not candidates:
        return ""

    return _utc_iso(min(candidates))


def _build_audit_row(event: Event) -> dict[str, Any]:
    payload = _payload_dict(event.payload_json)

    idempotency_key = payload.get("idempotencyKey")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        idempotency_key = None

    return {
        "timestamp": _utc_iso(event.ts_utc),
        "eventType": event.event_type,
        "outcome": event.outcome,
        "reasonCode": None if event.reason_code in {None, "OK"} else event.reason_code,
        "idempotencyKey": idempotency_key,
        "correlationId": event.correlation_id,
        "safeSummary": _safe_summary(event),
    }


def _find_latest_nlp_preprocessed_payload(*, db: Session, classified_event: Event) -> dict[str, Any]:
    preprocessed_event = (
        db.query(Event)
        .filter(
            Event.tenant_id == classified_event.tenant_id,
            Event.session_id == classified_event.session_id,
            Event.correlation_id == classified_event.correlation_id,
            Event.event_type == "NLP_PREPROCESSED",
            Event.ts_utc <= classified_event.ts_utc,
        )
        .order_by(Event.ts_utc.desc())
        .first()
    )

    if preprocessed_event is None:
        return {}

    return _payload_dict(preprocessed_event.payload_json)


def _build_nlp_recent_row(*, db: Session, event: Event) -> dict[str, Any]:
    payload = _payload_dict(event.payload_json)
    preprocessed_payload = _find_latest_nlp_preprocessed_payload(db=db, classified_event=event)

    top_candidates = payload.get("topCandidates")
    first_candidate = (
        top_candidates[0]
        if isinstance(top_candidates, list) and top_candidates and isinstance(top_candidates[0], dict)
        else {}
    )

    predicted_specialty = payload.get("predictedSpecialty")
    if not isinstance(predicted_specialty, str) or not predicted_specialty.strip():
        predicted_specialty = first_candidate.get("id") or "unknown"

    confidence = first_candidate.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = payload.get("topConfidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.0

    ambiguity_decision = payload.get("ambiguityDecision")
    ambiguity = ambiguity_decision != "accepted"

    input_summary = (
        preprocessed_payload.get("normalizedInputSummary")
        or preprocessed_payload.get("classifierInputSummary")
        or preprocessed_payload.get("originalComplaintSummary")
    )
    if not isinstance(input_summary, str) or not input_summary.strip():
        input_summary = None

    return {
        "timestamp": _utc_iso(event.ts_utc),
        "inputSummary": input_summary,
        "predictedLabel": _humanize_specialty(str(predicted_specialty)),
        "confidence": round(float(confidence), 4),
        "ambiguity": ambiguity,
    }


def _tenant_scope(
    current_user: AuthenticatedPortalUser,
    requested_tenant_id: str | None = None,
) -> list[str] | None:
    if current_user.is_company_admin():
        if requested_tenant_id and requested_tenant_id.strip():
            return [requested_tenant_id.strip()]
        return None
    return [current_user.tenantId]


def _apply_event_scope(query, tenant_ids: list[str] | None):
    if tenant_ids is None:
        return query
    return query.filter(Event.tenant_id.in_(tenant_ids))


def _apply_session_scope(query, tenant_ids: list[str] | None):
    if tenant_ids is None:
        return query
    return query.filter(AssistantSession.tenant_id.in_(tenant_ids))


def get_tenants(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
) -> list[dict[str, Any]]:
    tenant_ids = _tenant_scope(current_user)

    query = db.query(Tenant)
    if tenant_ids is not None:
        query = query.filter(Tenant.id.in_(tenant_ids))

    tenants = query.order_by(Tenant.id.asc()).all()

    return [
        {
            "tenantId": tenant.id,
            "name": tenant.name,
            "status": "ACTIVE",
            "createdAt": _tenant_created_at(db=db, tenant_id=tenant.id),
        }
        for tenant in tenants
    ]


def get_tenant_detail(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    tenant_id: str,
) -> dict[str, Any] | None:
    scoped_tenant_ids = _tenant_scope(current_user, tenant_id)

    query = db.query(Tenant).filter(Tenant.id == tenant_id.strip())
    if scoped_tenant_ids is not None:
        query = query.filter(Tenant.id.in_(scoped_tenant_ids))

    tenant = query.first()
    if tenant is None:
        return None

    return {
        "tenantId": tenant.id,
        "name": tenant.name,
        "status": "ACTIVE",
        "createdAt": _tenant_created_at(db=db, tenant_id=tenant.id),
        "allowedOrigins": [settings.hospital_origin, settings.portal_origin],
        "featureFlags": {
            "nlpEnabled": True,
            "continuityEnabled": True,
            "renewalEnabled": True,
            "otpEmailEnabled": True,
            "appointmentConfirmationEmailEnabled": True,
            "renewalConfirmationEmailEnabled": True,
            "portalTraceabilityEnabled": True,
        },
        "fhirStatus": "CONFIGURED" if settings.fhir_base_url else "UNKNOWN",
        "smtpStatus": "CONFIGURED" if settings.smtp_host else "UNKNOWN",
    }


def get_audit_page(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    from_date: str,
    to_date: str,
    event_type: str | None = None,
    outcome: str | None = None,
    reason_code: str | None = None,
    correlation_id: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    start_dt, end_dt = _range_bounds(from_date, to_date)
    tenant_ids = _tenant_scope(current_user, tenant_id)

    query = _apply_event_scope(db.query(Event), tenant_ids).filter(
        Event.ts_utc >= start_dt,
        Event.ts_utc <= end_dt,
    )

    if event_type:
        query = query.filter(Event.event_type == event_type.strip().upper())

    if outcome:
        query = query.filter(Event.outcome == outcome.strip().upper())

    if reason_code:
        query = query.filter(Event.reason_code == reason_code.strip().upper())

    if correlation_id:
        query = query.filter(Event.correlation_id == correlation_id.strip())

    if session_id:
        query = query.filter(Event.session_id == session_id.strip())

    rows = query.order_by(Event.ts_utc.desc()).all()
    items = [_build_audit_row(event) for event in rows]

    total = len(items)
    safe_page = max(page, 1)
    safe_page_size = max(page_size, 1)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size

    return {
        "items": items[start_index:end_index],
        "total": total,
        "page": safe_page,
        "pageSize": safe_page_size,
    }


def get_nlp_stats(
    *,
    nlp_service: Any | None,
    nlp_status: dict[str, Any] | None,
) -> dict[str, Any]:
    if nlp_service is not None:
        status = nlp_service.status()
        return {
            "loadedLabels": int(status.get("labelsCount", 0)),
            "thresholds": status.get("thresholds", {}),
            "modelName": status.get("modelName"),
            "modelVersion": status.get("modelVersion"),
            "lastModelLoadTime": status.get("loadedAt"),
        }

    status = nlp_status or {}
    return {
        "loadedLabels": int(status.get("labelsCount", 0) or 0),
        "thresholds": status.get("thresholds", {}),
        "modelName": status.get("modelName"),
        "modelVersion": status.get("modelVersion"),
        "lastModelLoadTime": status.get("loadedAt"),
    }


def get_nlp_recent(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    limit: int = 20,
) -> list[dict[str, Any]]:
    tenant_ids = _tenant_scope(current_user)

    events = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.event_type == "NLP_CLASSIFIED")
        .order_by(Event.ts_utc.desc())
        .limit(limit)
        .all()
    )

    return [_build_nlp_recent_row(db=db, event=event) for event in events]

def _split_slot_start(value: str | None) -> tuple[str, str]:
    if not value:
        return ("", "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date().isoformat(), parsed.strftime("%H:%M")
    except Exception:
        return (value[:10], value[11:16] if len(value) >= 16 else "")


def _extract_booking_id(event: Event) -> str:
    payload = _payload_dict(event.payload_json)
    for candidate in [payload.get("appointmentRef"), payload.get("safeSummary")]:
        if isinstance(candidate, str):
            match = APPOINTMENT_REF_RE.search(candidate)
            if match:
                return match.group(1).split("/", 1)[1]
    return f"BKG-{event.id[:8].upper()}"


def _build_session_lookup(
    *,
    db: Session,
    events: list[Event],
) -> dict[tuple[str, str], AssistantSession]:
    if not events:
        return {}

    tenant_ids = sorted({event.tenant_id for event in events})
    session_ids = sorted({event.session_id for event in events})

    sessions = (
        db.query(AssistantSession)
        .filter(
            AssistantSession.tenant_id.in_(tenant_ids),
            AssistantSession.client_session_id.in_(session_ids),
        )
        .all()
    )

    return {
        (session.tenant_id, session.client_session_id): session
        for session in sessions
    }


def _build_booking_row(event: Event, session: AssistantSession | None) -> dict[str, Any]:
    slot_date, slot_time = _split_slot_start(
        session.selected_slot_start_utc if session else None
    )

    return {
        "createdAt": _utc_iso(event.ts_utc),
        "bookingId": _extract_booking_id(event),
        "tenantId": event.tenant_id,
        "specialty": _humanize_specialty(
            session.selected_specialty_id if session else None
        ),
        "slotDate": slot_date,
        "slotTime": slot_time,
        "outcome": "SUCCESS" if event.event_type == "BOOKING_CONFIRMED" else "FAILED",
        "reasonCode": None if event.reason_code in {None, "OK"} else event.reason_code,
        "correlationId": event.correlation_id,
    }


def get_analytics_summary(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    start_dt, end_dt = _range_bounds(from_date, to_date)
    tenant_ids = _tenant_scope(current_user)

    events_query = _apply_event_scope(db.query(Event), tenant_ids).filter(
        Event.ts_utc >= start_dt,
        Event.ts_utc <= end_dt,
    )

    total_bookings = events_query.filter(Event.event_type == "BOOKING_CONFIRMED").count()
    booking_failures = events_query.filter(Event.event_type == "BOOKING_FAILED").count()
    dropped_sessions = events_query.filter(Event.event_type == "SESSION_DROPPED").count()

    top_reason_rows = (
        events_query.filter(
            Event.reason_code.isnot(None),
            Event.reason_code != "OK",
        )
        .with_entities(Event.reason_code, func.count(Event.id))
        .group_by(Event.reason_code)
        .order_by(desc(func.count(Event.id)))
        .limit(5)
        .all()
    )

    sessions_query = _apply_session_scope(db.query(AssistantSession), tenant_ids).filter(
        AssistantSession.updated_at_utc >= start_dt,
        AssistantSession.updated_at_utc <= end_dt,
        AssistantSession.selected_specialty_id.isnot(None),
    )

    top_specialty_rows = (
        sessions_query.with_entities(
            AssistantSession.selected_specialty_id,
            func.count(AssistantSession.id),
        )
        .group_by(AssistantSession.selected_specialty_id)
        .order_by(desc(func.count(AssistantSession.id)))
        .limit(5)
        .all()
    )

    return {
        "from": from_date,
        "to": to_date,
        "totalBookings": total_bookings,
        "bookingFailures": booking_failures,
        "droppedSessions": dropped_sessions,
        "topReasonCodes": [
            {"code": row[0], "count": row[1]}
            for row in top_reason_rows
            if row[0]
        ],
        "topSpecialties": [
            {"specialty": _humanize_specialty(row[0]), "count": row[1]}
            for row in top_specialty_rows
            if row[0]
        ],
    }


def get_recent_bookings(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    limit: int = 10,
) -> list[dict[str, Any]]:
    tenant_ids = _tenant_scope(current_user)

    events = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.event_type.in_(["BOOKING_CONFIRMED", "BOOKING_FAILED"]))
        .order_by(Event.ts_utc.desc())
        .limit(limit)
        .all()
    )

    session_lookup = _build_session_lookup(db=db, events=events)

    return [
        _build_booking_row(
            event,
            session_lookup.get((event.tenant_id, event.session_id)),
        )
        for event in events
    ]


def get_bookings_page(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    from_date: str,
    to_date: str,
    status: str | None = None,
    specialty: str | None = None,
    reason_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    start_dt, end_dt = _range_bounds(from_date, to_date)
    tenant_ids = _tenant_scope(current_user)

    events = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(
            Event.ts_utc >= start_dt,
            Event.ts_utc <= end_dt,
            Event.event_type.in_(["BOOKING_CONFIRMED", "BOOKING_FAILED"]),
        )
        .order_by(Event.ts_utc.desc())
        .all()
    )

    session_lookup = _build_session_lookup(db=db, events=events)

    rows = [
        _build_booking_row(
            event,
            session_lookup.get((event.tenant_id, event.session_id)),
        )
        for event in events
    ]

    if status:
        wanted = status.strip().upper()
        rows = [row for row in rows if row["outcome"] == wanted]

    if specialty:
        wanted_specialty = specialty.strip().lower()
        rows = [
            row
            for row in rows
            if (row.get("specialty") or "").strip().lower() == wanted_specialty
        ]

    if reason_code:
        wanted_reason = reason_code.strip().upper()
        rows = [
            row
            for row in rows
            if (row.get("reasonCode") or "").strip().upper() == wanted_reason
        ]

    total = len(rows)
    safe_page = max(page, 1)
    safe_page_size = max(page_size, 1)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size

    return {
        "items": rows[start_index:end_index],
        "total": total,
        "page": safe_page,
        "pageSize": safe_page_size,
    }


def _derive_session_status(
    session: AssistantSession,
    events: list[Event],
) -> tuple[str, str | None, str | None, datetime]:
    latest_event = events[-1] if events else None
    latest_timestamp = latest_event.ts_utc if latest_event else session.updated_at_utc

    for event in reversed(events):
        if event.event_type == "SESSION_DROPPED":
            return ("DROPPED", event.reason_code, event.correlation_id, latest_timestamp)
        if event.event_type == "SESSION_COMPLETED":
            return ("COMPLETED", event.reason_code, event.correlation_id, latest_timestamp)

    if latest_event and latest_event.outcome == "FAILURE":
        return ("FAILED", latest_event.reason_code, latest_event.correlation_id, latest_timestamp)

    return ("ACTIVE", None, latest_event.correlation_id if latest_event else None, latest_timestamp)


def get_sessions_page(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    from_date: str,
    to_date: str,
    status: str | None = None,
    tenant_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    start_dt, end_dt = _range_bounds(from_date, to_date)
    tenant_ids = _tenant_scope(current_user, tenant_id)

    sessions = (
        _apply_session_scope(db.query(AssistantSession), tenant_ids)
        .filter(
            AssistantSession.created_at_utc >= start_dt,
            AssistantSession.created_at_utc <= end_dt,
        )
        .order_by(AssistantSession.created_at_utc.desc())
        .all()
    )

    if not sessions:
        return {"items": [], "total": 0, "page": page, "pageSize": page_size}

    event_rows = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.session_id.in_([session.client_session_id for session in sessions]))
        .order_by(Event.ts_utc.asc())
        .all()
    )

    events_by_key: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in event_rows:
        events_by_key[(event.tenant_id, event.session_id)].append(event)

    rows: list[dict[str, Any]] = []
    for session in sessions:
        related_events = events_by_key.get((session.tenant_id, session.client_session_id), [])
        derived_status, final_reason, correlation_id, last_event_at = _derive_session_status(
            session,
            related_events,
        )

        rows.append(
            {
                "sessionId": session.client_session_id,
                "tenantId": session.tenant_id,
                "startedAt": _utc_iso(session.created_at_utc),
                "lastEventAt": _utc_iso(last_event_at),
                "status": derived_status,
                "finalReasonCode": None if final_reason in {None, "OK"} else final_reason,
                "correlationId": correlation_id,
            }
        )

    if status:
        wanted = status.strip().upper()
        rows = [row for row in rows if row["status"] == wanted]

    total = len(rows)
    safe_page = max(page, 1)
    safe_page_size = max(page_size, 1)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size

    return {
        "items": rows[start_index:end_index],
        "total": total,
        "page": safe_page,
        "pageSize": safe_page_size,
    }


def _build_trace_row(event: Event) -> dict[str, Any]:
    return {
        "timestamp": _utc_iso(event.ts_utc),
        "eventType": event.event_type,
        "component": _component_name(event),
        "outcome": event.outcome,
        "reasonCode": None if event.reason_code in {None, "OK"} else event.reason_code,
        "safeSummary": _safe_summary(event),
        "details": _trace_details(event),
    }


def get_traces_by_correlation_id(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    correlation_id: str,
) -> list[dict[str, Any]]:
    tenant_ids = _tenant_scope(current_user)

    events = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.correlation_id == correlation_id.strip())
        .order_by(Event.ts_utc.asc())
        .all()
    )

    return [_build_trace_row(event) for event in events]


def get_traces_by_session_id(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
    session_id: str,
) -> list[dict[str, Any]]:
    tenant_ids = _tenant_scope(current_user)

    events = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.session_id == session_id.strip())
        .order_by(Event.ts_utc.asc())
        .all()
    )

    return [_build_trace_row(event) for event in events]