"""Query Service Module for Hospital Assistant Observability.

This module provides database query functions for observability, analytics, and audit trails
of the hospital assistant system. It includes functions to retrieve session data, NLP events,
booking information, and detailed traces for system monitoring and compliance.

Key responsibilities:
- Querying and filtering observability events
- Generating analytics summaries and reports
- Building trace details for debugging and auditing
- Managing tenant-scoped data access
"""
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

# Regex pattern to extract FHIR Appointment references from event payloads
APPOINTMENT_REF_RE = re.compile(r"(Appointment/[A-Za-z0-9._-]+)")


def _utc_iso(value: datetime | None) -> str:
    """Convert datetime to ISO 8601 string with UTC timezone.
    
    Handles None values and ensures all datetimes are converted to UTC before
    formatting. Uses 'Z' suffix for Zulu/UTC time per ISO 8601 standard.
    
    Args:
        value: Datetime object to convert, or None.
    
    Returns:
        ISO 8601 formatted string with 'Z' suffix, or empty string if value is None.
    """
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _range_bounds(from_date: str, to_date: str) -> tuple[datetime, datetime]:
    """Parse date strings and return normalized UTC datetime bounds.
    
    Converts ISO date strings to datetime objects representing the full day range.
    The start time is set to 00:00:00 UTC and end time to 23:59:59 UTC. Automatically
    handles reversed date order by swapping them.
    
    Args:
        from_date: Start date as ISO format string (YYYY-MM-DD).
        to_date: End date as ISO format string (YYYY-MM-DD).
    
    Returns:
        Tuple of (start_datetime, end_datetime) both in UTC timezone.
    """
    start_date = date.fromisoformat(from_date)
    end_date = date.fromisoformat(to_date)

    # Automatically swap if dates are reversed
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def _humanize_specialty(value: str | None) -> str:
    """Convert specialty identifier to human-readable format.
    
    Transforms snake_case specialty IDs into title-cased display text.
    For example: 'general_medicine' becomes 'General Medicine'.
    
    Args:
        value: Specialty identifier string or None.
    
    Returns:
        Human-readable specialty name, or 'Unknown' if value is None or empty.
    """
    if not value:
        return "Unknown"
    return value.replace("_", " ").strip().title()


def _payload_dict(raw: str | None) -> dict[str, Any]:
    """Safely parse JSON payload string to dictionary.
    
    Handles None values, invalid JSON, and non-dict JSON structures gracefully.
    Used throughout to extract nested data from event payloads.
    
    Args:
        raw: JSON string to parse, or None.
    
    Returns:
        Parsed dictionary, or empty dict if parsing fails or input is None.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_summary(event: Event) -> str:
    """Extract or generate a safe summary for an event.
    
    Retrieves the safeSummary from the event payload if available and non-empty.
    Falls back to a humanized version of the event type for display purposes.
    
    Args:
        event: Event object to extract summary from.
    
    Returns:
        Summary text, either from payload or derived from event type.
    """
    payload = _payload_dict(event.payload_json)
    summary = payload.get("safeSummary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return event.event_type.replace("_", " ").title()


def _component_name(event: Event) -> str:
    """Extract component name from event payload or actor type.
    
    Attempts to get the component name from the event payload first.
    Falls back to the actor_type if not available.
    
    Args:
        event: Event object to extract component from.
    
    Returns:
        Component name string.
    """
    payload = _payload_dict(event.payload_json)
    component = payload.get("component")
    if isinstance(component, str) and component.strip():
        return component.strip()
    return event.actor_type


def _stringify_trace_value(value: Any) -> str | None:
    """Convert various value types to human-readable string for trace display.
    
    Handles type-specific formatting:
    - Booleans: converted to 'Yes'/'No'
    - Numbers: converted to strings
    - Strings: trimmed and returned if non-empty
    - Other types: return None
    
    Args:
        value: Value of any type to convert.
    
    Returns:
        String representation or None if value is None or empty.
    """
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
    """Format list of top specialty candidates into readable string.
    
    Converts a list of candidate objects (containing 'id' and 'confidence' fields)
    into a semicolon-separated string of humanized specialty names with confidence scores.
    
    Args:
        value: List of candidate dictionaries with 'id' and optional 'confidence' keys.
    
    Returns:
        Formatted string like 'Specialty1 (0.95); Specialty2 (0.80)', or None if empty.
    """
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
    """Extract detailed trace information from NLP event payload.
    
    Builds a dictionary of human-readable trace details by extracting and formatting
    various fields from the event payload. Includes:
    - NLP model information (version, confidence scores)
    - Specialty selection details (predicted, selected, confidence)
    - Ambiguity analysis and thresholds
    - Preprocessing actions applied
    - Top candidate specialties
    - Notification and booking details
    
    Args:
        event: Event object containing NLP trace data in payload_json.
    
    Returns:
        Dictionary mapping display labels to formatted values, or None if empty.
    """
    payload = _payload_dict(event.payload_json)
    details: dict[str, str] = {}

    # Mapping of display labels to payload field keys
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

    # Extract and format scalar fields
    for label, key in scalar_fields:
        rendered = _stringify_trace_value(payload.get(key))
        if rendered:
            details[label] = rendered

    # Format preprocessing actions as comma-separated list
    preprocessing_actions = payload.get("preprocessingActions")
    if isinstance(preprocessing_actions, list) and preprocessing_actions:
        rendered_actions = ", ".join(
            str(item).strip() for item in preprocessing_actions if str(item).strip()
        )
        if rendered_actions:
            details["Preprocessing actions"] = rendered_actions

    # Format top candidates with confidence scores
    top_candidates = _format_top_candidates(payload.get("topCandidates"))
    if top_candidates:
        details["Top candidates"] = top_candidates

    return details or None

def _tenant_created_at(*, db: Session, tenant_id: str) -> str:
    """Retrieve the earliest timestamp when a tenant's activity began.
    
    Queries both AssistantSession and Event tables to find the earliest record
    associated with the tenant. Returns the minimum of the two timestamps.
    
    Args:
        db: SQLAlchemy session for database queries.
        tenant_id: The tenant's unique identifier.
    
    Returns:
        ISO 8601 formatted UTC datetime string, or empty string if no data exists.
    """
    # Find the earliest session creation timestamp for this tenant
    first_session = (
        db.query(func.min(AssistantSession.created_at_utc))
        .filter(AssistantSession.tenant_id == tenant_id)
        .scalar()
    )
    # Find the earliest event timestamp for this tenant
    first_event = (
        db.query(func.min(Event.ts_utc))
        .filter(Event.tenant_id == tenant_id)
        .scalar()
    )

    # Take the earliest of the two timestamps
    candidates = [value for value in [first_session, first_event] if value is not None]
    if not candidates:
        return ""

    return _utc_iso(min(candidates))


def _build_audit_row(event: Event) -> dict[str, Any]:
    """Build an audit row dictionary from an event for audit trail display.
    
    Transforms a database Event into a structured dictionary suitable for
    audit trail reporting. Filters out 'OK' reason codes and empty idempotency keys.
    
    Args:
        event: Event object from the database.
    
    Returns:
        Dictionary with keys: timestamp, eventType, outcome, reasonCode,
        idempotencyKey, correlationId, safeSummary.
    """
    payload = _payload_dict(event.payload_json)

    # Extract and validate idempotency key from payload
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
    """Find the latest NLP preprocessing event before a classification event.
    
    Locates the most recent NLP_PREPROCESSED event in the same session and correlation
    chain, occurring before or at the same time as the given classified_event.
    Useful for enriching classification results with preprocessing context.
    
    Args:
        db: SQLAlchemy session for database queries.
        classified_event: The NLP_CLASSIFIED event to find preprocessing for.
    
    Returns:
        Dictionary from the preprocessing event's payload, or empty dict if not found.
    """
    # Query for the most recent preprocessing event in the same context
    preprocessed_event = (
        db.query(Event)
        .filter(
            Event.tenant_id == classified_event.tenant_id,
            Event.session_id == classified_event.session_id,
            Event.correlation_id == classified_event.correlation_id,
            Event.event_type == "NLP_PREPROCESSED",
            Event.ts_utc <= classified_event.ts_utc,  # Must occur before or at classification
        )
        .order_by(Event.ts_utc.desc())
        .first()
    )

    if preprocessed_event is None:
        return {}

    return _payload_dict(preprocessed_event.payload_json)


def _build_nlp_recent_row(*, db: Session, event: Event) -> dict[str, Any]:
    """Build a recent NLP classification row for analytics display.
    
    Transforms a NLP_CLASSIFIED event into a summary row containing the input text,
    predicted specialty, confidence score, and ambiguity flag. Enriches with preprocessing
    context and applies fallback logic for missing values.
    
    Args:
        db: SQLAlchemy session for database queries.
        event: NLP_CLASSIFIED event to build row from.
    
    Returns:
        Dictionary with keys: timestamp, inputSummary, predictedLabel, confidence, ambiguity.
    """
    payload = _payload_dict(event.payload_json)
    # Fetch related preprocessing data to get the original input summary
    preprocessed_payload = _find_latest_nlp_preprocessed_payload(db=db, classified_event=event)

    # Extract top candidates and get the first one if available
    top_candidates = payload.get("topCandidates")
    first_candidate = (
        top_candidates[0]
        if isinstance(top_candidates, list) and top_candidates and isinstance(top_candidates[0], dict)
        else {}
    )

    # Determine predicted specialty with fallback logic
    predicted_specialty = payload.get("predictedSpecialty")
    if not isinstance(predicted_specialty, str) or not predicted_specialty.strip():
        predicted_specialty = first_candidate.get("id") or "unknown"

    # Extract confidence score with fallback to topConfidence and default
    confidence = first_candidate.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = payload.get("topConfidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.0

    # Determine if result is ambiguous (ambiguity decision != "accepted")
    ambiguity_decision = payload.get("ambiguityDecision")
    ambiguity = ambiguity_decision != "accepted"

    # Extract input summary with priority order: normalized > classifier > original
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
    """Determine which tenant IDs the current user can access.
    
    Implements role-based access control:
    - Company admins can access specific tenant or all tenants (None means all)
    - Regular users can only access their own tenant
    
    Args:
        current_user: Authenticated user with role and tenant information.
        requested_tenant_id: Specific tenant to check access for, optional.
    
    Returns:
        List of allowed tenant IDs, or None if user is admin with no specific request
        (meaning they can access all tenants).
    """
    if current_user.is_company_admin():
        if requested_tenant_id and requested_tenant_id.strip():
            return [requested_tenant_id.strip()]
        return None  # Admin can access all tenants
    return [current_user.tenantId]  # Regular user limited to their tenant


def _apply_event_scope(query, tenant_ids: list[str] | None):
    """Filter event query by allowed tenant IDs for access control.
    
    Applies WHERE clause to restrict results to specified tenants.
    If tenant_ids is None (admin with all-tenant access), returns query unmodified.
    
    Args:
        query: SQLAlchemy Event query to filter.
        tenant_ids: List of allowed tenant IDs, or None for no filtering.
    
    Returns:
        Modified query with tenant filter applied, or original query if no filtering needed.
    """
    if tenant_ids is None:
        return query
    return query.filter(Event.tenant_id.in_(tenant_ids))


def _apply_session_scope(query, tenant_ids: list[str] | None):
    """Filter AssistantSession query by allowed tenant IDs for access control.
    
    Applies WHERE clause to restrict results to specified tenants.
    If tenant_ids is None (admin with all-tenant access), returns query unmodified.
    
    Args:
        query: SQLAlchemy AssistantSession query to filter.
        tenant_ids: List of allowed tenant IDs, or None for no filtering.
    
    Returns:
        Modified query with tenant filter applied, or original query if no filtering needed.
    """
    if tenant_ids is None:
        return query
    return query.filter(AssistantSession.tenant_id.in_(tenant_ids))


def get_tenants(
    *,
    db: Session,
    current_user: AuthenticatedPortalUser,
) -> list[dict[str, Any]]:
    """Retrieve all tenants accessible to the current user.
    
    Lists all tenants the user has access to with their metadata including
    creation timestamp. Company admins see all tenants; regular users see only their own.
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
    
    Returns:
        List of tenant dictionaries with keys: tenantId, name, status, createdAt.
    """
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
    """Retrieve detailed configuration and status for a specific tenant.
    
    Provides comprehensive tenant information including feature flags, FHIR and SMTP
    configuration status, and allowed origin URLs. Returns None if tenant not found
    or user lacks access.
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        tenant_id: ID of the tenant to retrieve.
    
    Returns:
        Tenant detail dictionary with configuration, or None if not found or unauthorized.
    """
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
    """Retrieve paginated audit trail of system events.
    
    Returns a filterable page of events for audit and compliance purposes.
    Supports filtering by date range, event type, outcome, reason code, correlation ID,
    session ID, and tenant ID. Results are ordered by timestamp (newest first).
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
        event_type: Filter by event type (e.g., 'NLP_CLASSIFIED'), optional.
        outcome: Filter by outcome ('SUCCESS' or 'FAILURE'), optional.
        reason_code: Filter by reason code, optional.
        correlation_id: Filter by correlation ID, optional.
        session_id: Filter by session ID, optional.
        tenant_id: Filter by tenant ID, optional.
        page: Page number (1-indexed), default 1.
        page_size: Items per page, default 20.
    
    Returns:
        Dictionary with keys: items (list of audit rows), total, page, pageSize.
    """
    start_dt, end_dt = _range_bounds(from_date, to_date)
    tenant_ids = _tenant_scope(current_user, tenant_id)

    query = _apply_event_scope(db.query(Event), tenant_ids).filter(
        Event.ts_utc >= start_dt,
        Event.ts_utc <= end_dt,
    )

    # Apply optional filters
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

    # Apply pagination
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
    """Retrieve current NLP model statistics and configuration.
    
    Gets information about the loaded NLP model including the number of labels,
    confidence thresholds, model name and version, and last load timestamp.
    Tries nlp_service first, falls back to nlp_status dict if service unavailable.
    
    Args:
        nlp_service: NLP service instance with status() method, or None.
        nlp_status: Pre-fetched status dictionary, or None.
    
    Returns:
        Dictionary with keys: loadedLabels, thresholds, modelName, modelVersion,
        lastModelLoadTime.
    """
    if nlp_service is not None:
        status = nlp_service.status()
        return {
            "loadedLabels": int(status.get("labelsCount", 0)),
            "thresholds": status.get("thresholds", {}),
            "modelName": status.get("modelName"),
            "modelVersion": status.get("modelVersion"),
            "lastModelLoadTime": status.get("loadedAt"),
        }

    # Fallback to provided status dict
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
    """Retrieve recent NLP classification results.
    
    Returns the most recent NLP_CLASSIFIED events, limited by the specified count.
    Includes input summaries, predicted specialties, confidence scores, and ambiguity flags.
    Results are ordered by timestamp (newest first).
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        limit: Maximum number of recent results to return, default 20.
    
    Returns:
        List of NLP classification summary dictionaries.
    """
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
    """Parse ISO datetime string into separate date and time components.
    
    Splits an ISO 8601 datetime (e.g., '2024-05-15T14:30:00Z') into date
    and time parts for separate display. Handles invalid formats gracefully.
    
    Args:
        value: ISO format datetime string, or None.
    
    Returns:
        Tuple of (date_string, time_string) in formats YYYY-MM-DD and HH:MM,
        or (original_string[:10], original_string[11:16]) on parse error,
        or ('', '') if value is None.
    """
    if not value:
        return ("", "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date().isoformat(), parsed.strftime("%H:%M")
    except Exception:
        # Fallback: try to extract date and time by string slicing
        return (value[:10], value[11:16] if len(value) >= 16 else "")


def _extract_booking_id(event: Event) -> str:
    """Extract or generate a booking reference ID from an event.
    
    Attempts to extract FHIR Appointment reference from the event payload
    using regex matching. Falls back to generating a synthetic booking ID from
    the event's UUID if no reference is found.
    
    Args:
        event: Event object containing booking information.
    
    Returns:
        Booking reference ID like 'Appointment/123' or 'BKG-ABCD1234'.
    """
    payload = _payload_dict(event.payload_json)
    # Try to extract Appointment reference from payload fields
    for candidate in [payload.get("appointmentRef"), payload.get("safeSummary")]:
        if isinstance(candidate, str):
            match = APPOINTMENT_REF_RE.search(candidate)
            if match:
                return match.group(1).split("/", 1)[1]
    # Generate synthetic booking ID from event UUID if no reference found
    return f"BKG-{event.id[:8].upper()}"


def _build_session_lookup(
    *,
    db: Session,
    events: list[Event],
) -> dict[tuple[str, str], AssistantSession]:
    """Build a lookup map of AssistantSession objects by tenant and session ID.
    
    Efficiently fetches all sessions referenced by a list of events and returns
    them in a keyed dictionary for O(1) lookup when enriching event data.
    
    Args:
        db: SQLAlchemy session for database queries.
        events: List of Event objects to find related sessions for.
    
    Returns:
        Dictionary mapping (tenant_id, session_id) tuples to AssistantSession objects.
    """
    if not events:
        return {}

    # Collect unique tenant and session IDs from events
    tenant_ids = sorted({event.tenant_id for event in events})
    session_ids = sorted({event.session_id for event in events})

    # Query all related sessions in one batch
    sessions = (
        db.query(AssistantSession)
        .filter(
            AssistantSession.tenant_id.in_(tenant_ids),
            AssistantSession.client_session_id.in_(session_ids),
        )
        .all()
    )

    # Build lookup map by (tenant_id, session_id) key
    return {
        (session.tenant_id, session.client_session_id): session
        for session in sessions
    }


def _build_booking_row(event: Event, session: AssistantSession | None) -> dict[str, Any]:
    """Build a booking row dictionary from an event and optional session.
    
    Transforms booking-related events and session data into a formatted row
    for display in booking lists or reports. Extracts slot date/time, specialty,
    and outcome information.
    
    Args:
        event: Booking event (BOOKING_CONFIRMED or BOOKING_FAILED).
        session: Related AssistantSession, or None if not available.
    
    Returns:
        Dictionary with keys: createdAt, bookingId, tenantId, specialty, slotDate,
        slotTime, outcome, reasonCode, correlationId.
    """
    # Parse appointment slot start time into date and time components
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
        # Determine success/failure from event type
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
    """Generate high-level analytics summary for a date range.
    
    Provides key metrics about system usage and performance:
    - Total bookings confirmed/failed
    - Session drop-off rate
    - Top failure reason codes
    - Top specialty selections
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
    
    Returns:
        Dictionary with keys: from, to, totalBookings, bookingFailures,
        droppedSessions, topReasonCodes, topSpecialties.
    """
    start_dt, end_dt = _range_bounds(from_date, to_date)
    tenant_ids = _tenant_scope(current_user)

    events_query = _apply_event_scope(db.query(Event), tenant_ids).filter(
        Event.ts_utc >= start_dt,
        Event.ts_utc <= end_dt,
    )

    # Count booking outcomes and dropped sessions
    total_bookings = events_query.filter(Event.event_type == "BOOKING_CONFIRMED").count()
    booking_failures = events_query.filter(Event.event_type == "BOOKING_FAILED").count()
    dropped_sessions = events_query.filter(Event.event_type == "SESSION_DROPPED").count()

    # Find top reason codes for failures
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

    # Find top selected specialties
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
    """Retrieve recent booking events (confirmed and failed).
    
    Returns the most recent booking-related events with appointment slot details
    and specialty information. Results are ordered by timestamp (newest first).
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        limit: Maximum number of recent bookings to return, default 10.
    
    Returns:
        List of booking row dictionaries.
    """
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
    """Retrieve paginated booking events with advanced filtering.
    
    Returns booking confirmations and failures within a date range, filtered by
    outcome status, specialty, and reason code. Supports pagination for large result sets.
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
        status: Filter by outcome ('SUCCESS' or 'FAILED'), optional.
        specialty: Filter by specialty name (case-insensitive), optional.
        reason_code: Filter by failure reason code, optional.
        page: Page number (1-indexed), default 1.
        page_size: Items per page, default 20.
    
    Returns:
        Dictionary with keys: items (list of booking rows), total, page, pageSize.
    """
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

    # Apply optional filters
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

    # Apply pagination
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
    """Derive the current status of a session from its events.
    
    Analyzes the session's events in reverse chronological order to determine:
    - Status: DROPPED, COMPLETED, FAILED, or ACTIVE
    - Final reason code if applicable
    - Latest correlation ID
    - Most recent timestamp
    
    Priority order:
    1. SESSION_DROPPED event -> DROPPED status
    2. SESSION_COMPLETED event -> COMPLETED status
    3. Latest event with FAILURE outcome -> FAILED status
    4. Default -> ACTIVE status
    
    Args:
        session: AssistantSession to derive status for.
        events: Ordered list of Event objects for this session.
    
    Returns:
        Tuple of (status_str, reason_code, correlation_id, latest_timestamp).
    """
    latest_event = events[-1] if events else None
    latest_timestamp = latest_event.ts_utc if latest_event else session.updated_at_utc

    # Check for terminal events in reverse order
    for event in reversed(events):
        if event.event_type == "SESSION_DROPPED":
            return ("DROPPED", event.reason_code, event.correlation_id, latest_timestamp)
        if event.event_type == "SESSION_COMPLETED":
            return ("COMPLETED", event.reason_code, event.correlation_id, latest_timestamp)

    # Check if the latest event indicates failure
    if latest_event and latest_event.outcome == "FAILURE":
        return ("FAILED", latest_event.reason_code, latest_event.correlation_id, latest_timestamp)

    # Default to active if no terminal events found
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
    """Retrieve paginated user sessions with status filtering.
    
    Lists all user sessions created within a date range, with their derived status
    (ACTIVE, COMPLETED, FAILED, DROPPED). Includes the latest timestamp and reason
    codes for failed sessions. Supports pagination.
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
        status: Filter by session status (e.g., 'ACTIVE', 'COMPLETED'), optional.
        tenant_id: Filter by tenant ID, optional.
        page: Page number (1-indexed), default 1.
        page_size: Items per page, default 20.
    
    Returns:
        Dictionary with keys: items (list of session rows), total, page, pageSize.
    """
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

    # Fetch all events for these sessions in one query
    event_rows = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.session_id.in_([session.client_session_id for session in sessions]))
        .order_by(Event.ts_utc.asc())
        .all()
    )

    # Group events by (tenant_id, session_id) key
    events_by_key: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in event_rows:
        events_by_key[(event.tenant_id, event.session_id)].append(event)

    # Build rows with derived status for each session
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

    # Apply optional status filter
    if status:
        wanted = status.strip().upper()
        rows = [row for row in rows if row["status"] == wanted]

    # Apply pagination
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
    """Build a trace row dictionary from a single event.
    
    Transforms an event into a formatted row for trace display, extracting
    the component name, outcome, reason, and detailed trace information.
    
    Args:
        event: Event object to build trace from.
    
    Returns:
        Dictionary with keys: timestamp, eventType, component, outcome, reasonCode,
        safeSummary, details.
    """
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
    """Retrieve all events for a given correlation ID (complete trace).
    
    Returns the full trace of events associated with a correlation ID, showing
    the complete request flow across all components. Events are ordered by timestamp
    (chronological order) to show the sequence of operations.
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        correlation_id: The correlation ID to trace.
    
    Returns:
        List of trace row dictionaries ordered by timestamp.
    """
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
    """Retrieve all events for a given session ID (complete session trace).
    
    Returns the full history of events for a user session, showing all interactions
    and system responses throughout the session. Events are ordered by timestamp
    (chronological order) to show the sequence of the user's journey.
    
    Args:
        db: SQLAlchemy session for database queries.
        current_user: Authenticated user for access control.
        session_id: The session ID to trace.
    
    Returns:
        List of trace row dictionaries ordered by timestamp.
    """
    tenant_ids = _tenant_scope(current_user)

    events = (
        _apply_event_scope(db.query(Event), tenant_ids)
        .filter(Event.session_id == session_id.strip())
        .order_by(Event.ts_utc.asc())
        .all()
    )

    return [_build_trace_row(event) for event in events]