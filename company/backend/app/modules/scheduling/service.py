from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import OtpRecord
from app.modules.fhir_gateway.client import FhirClient
from app.modules.fhir_gateway.reason_codes import FhirGatewayError
from app.modules.fhir_gateway.schemas import AppointmentDTO, SlotDTO
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
from app.modules.scheduling.idempotency import (
    get_replayed_result_or_raise,
    save_terminal_result,
    stable_request_hash,
    to_jsonable_dict,
)
from app.modules.scheduling.reason_codes import (
    APPOINTMENT_CREATE_FAILED,
    DUPLICATE_APPOINTMENT_BLOCKED,
    FHIR_UNAVAILABLE,
    IDEMPOTENCY_KEY_REQUIRED,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    NO_PROVIDERS_AVAILABLE,
    NO_SLOTS_AVAILABLE,
    OK,
    OTP_NOT_VERIFIED,
    SLOT_TAKEN,
    SchedulingError,
)


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    Uses the UTC tzinfo imported from datetime. This helper centralizes
    creation of timezone-aware datetimes so tests can mock or replace it
    if needed.
    """
    return datetime.now(UTC)


def to_utc_z(value: datetime) -> str:
    """Convert a timezone-aware datetime to an ISO8601 UTC string.

    The returned string uses the trailing 'Z' instead of '+00:00' and
    has microseconds removed for consistent formatting when persisted
    or compared with FHIR timestamps.
    """
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    """Parse an ISO8601 datetime string into a timezone-aware UTC datetime.

    Accepts strings that end with 'Z' or an explicit offset. If the
    parsed value is naive (no timezone) a SchedulingError is raised
    because all scheduling datetimes must be timezone-aware UTC values.
    """
    # Normalize the common 'Z' suffix so fromisoformat can parse it.
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)

    # Enforce timezone-awareness: scheduling comparisons depend on an
    # explicit offset so we never mix naive and aware values.
    if parsed.tzinfo is None:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Datetime must be timezone-aware UTC.",
        )

    # Return as UTC tz-aware datetime for consistent comparisons.
    return parsed.astimezone(UTC)


def normalize_specialty_token(value: str | None) -> str:
    """Normalize a specialty token into a canonical lowercase form.

    Converts spaces and dashes to underscores and trims surrounding
    whitespace. Empty or None values become an empty string.
    """
    if not value:
        return ""
    return value.strip().replace("-", "_").replace(" ", "_").lower()


def is_overlap(
    *,
    new_start: datetime,
    new_end: datetime,
    existing_start: datetime,
    existing_end: datetime,
) -> bool:
    """Return True if two time intervals overlap.

    Intervals are treated as half-open (start inclusive, end exclusive).
    This function returns True if the [new_start, new_end) interval
    intersects the [existing_start, existing_end) interval.
    """
    return new_start < existing_end and new_end > existing_start


def ensure_verified_otp_or_raise(
    *,
    db: Session,
    tenant_id: str,
    session_id: str,
    patient_key_hash: str,
    email: str,
) -> None:
    """Ensure that a verified OTP record exists for the given identifiers.

    If no verified OTP is found a `SchedulingError` with reason code
    `OTP_NOT_VERIFIED` is raised. The query orders by expiry so the most
    recent verification is returned when present.
    """
    verified_record = (
        db.query(OtpRecord)
        .filter(
            OtpRecord.tenant_id == tenant_id,
            OtpRecord.session_id == session_id,
            OtpRecord.patient_key_hash == patient_key_hash,
            OtpRecord.email == email,
            OtpRecord.verified.is_(True),
        )
        .order_by(OtpRecord.expires_at.desc())
        .first()
    )

    if verified_record is None:
        # No verified OTP found for this patient/session/email.
        raise SchedulingError(reason_code=OTP_NOT_VERIFIED)


def map_fhir_error(exc: FhirGatewayError) -> SchedulingError:
    """Map a low-level FHIR gateway error to a SchedulingError.

    Mapping rules translate FHIR-specific reason codes into the
    scheduling domain so callers can return user-friendly messages
    and appropriate HTTP status codes.
    """
    # Service-level outages and timeouts are surfaced as a temporary
    # unavailability in the scheduling domain.
    if exc.reason_code in {"FHIR_UNAVAILABLE", "FHIR_TIMEOUT"}:
        return SchedulingError(
            reason_code=FHIR_UNAVAILABLE,
            user_message="Scheduling is temporarily unavailable because the FHIR service cannot be reached.",
            status_code=503,
            details=exc.details,
        )

    # Appointment conflicts or slots that were just taken map to a
    # user-facing 'slot taken' outcome with a 409 conflict status.
    if exc.reason_code in {"APPOINTMENT_CONFLICT", "SLOT_NO_LONGER_AVAILABLE"}:
        return SchedulingError(
            reason_code=SLOT_TAKEN,
            status_code=409,
            details=exc.details,
        )

    # Creation failures in the FHIR layer are surfaced as a service
    # failure to create the appointment.
    if exc.reason_code == "APPOINTMENT_CREATE_FAILED":
        return SchedulingError(
            reason_code=APPOINTMENT_CREATE_FAILED,
            status_code=503,
            details=exc.details,
        )

    # Default mapping: client errors become INVALID_REQUEST, server
    # errors become INTERNAL_ERROR.
    return SchedulingError(
        reason_code=INVALID_REQUEST if exc.status_code < 500 else INTERNAL_ERROR,
        user_message=exc.user_message,
        status_code=exc.status_code,
        details=exc.details,
    )


def _filter_slots_against_booked_appointments(
    *,
    slots: list[SlotDTO],
    appointments: list[AppointmentDTO],
) -> list[SlotDTO]:
    """Remove slots that conflict with already booked appointments.

    Two levels of filtering are applied:
    - If a booked appointment directly references a slot (slotRef), the
      slot is considered occupied.
    - If the appointment time interval overlaps the slot interval the
      slot is also considered conflicting and removed.
    """
    if not slots or not appointments:
        return slots

    # Fast-path: collect slotRefs that are explicitly occupied by booked
    # appointments and skip any matching slots immediately.
    occupied_slot_refs = {ref for appt in appointments for ref in appt.slotRefs}
    filtered: list[SlotDTO] = []

    for slot in slots:
        if slot.slotRef in occupied_slot_refs:
            # This slot is explicitly referenced by a booked appointment.
            continue

        slot_start = parse_utc(slot.startUtc)
        slot_end = parse_utc(slot.endUtc)

        # Check for time overlap with each booked appointment. If any
        # appointment intersects the slot interval, the slot is removed
        # even if it was not linked through slotRefs.
        conflict = False
        for appointment in appointments:
            if not appointment.startUtc or not appointment.endUtc:
                # Skip appointments missing time bounds (defensive).
                continue

            if is_overlap(
                new_start=slot_start,
                new_end=slot_end,
                existing_start=parse_utc(appointment.startUtc),
                existing_end=parse_utc(appointment.endUtc),
            ):
                conflict = True
                break

        if not conflict:
            filtered.append(slot)

    return filtered


async def list_available_slots(
    *,
    db: Session,
    header_tenant_id: str,
    session_id: str,
    body_tenant_id: str,
    specialty: str,
    now_utc: datetime | None = None,
    fhir_client: FhirClient | None = None,
) -> dict:
    """Return available FHIR-backed slots for a specialty and tenant.

    This coordinates tenant validation, queries FHIR schedules and
    slots, filters out any slots that conflict with booked
    appointments, and emits an availability event for observability.
    """
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)

    specialty_normalized = normalize_specialty_token(specialty)
    now_value = now_utc or utc_now()
    now_iso = to_utc_z(now_value)
    client = fhir_client or FhirClient()

    # Fetch all schedules for the tenant/specialty. Map FHIR errors to
    # scheduling domain errors to provide consistent responses.
    try:
        schedules = await client.search_schedules(
            tenant_id=body_tenant_id,
            specialty=specialty_normalized,
            active=True,
        )
    except FhirGatewayError as exc:
        raise map_fhir_error(exc) from exc

    if not schedules:
        # No providers are configured for this specialty, so emit a
        # domain event and return an empty result set instead of erroring.
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="AVAILABILITY_REQUESTED",
            outcome="FAILURE",
            reason_code=NO_PROVIDERS_AVAILABLE,
            payload={
                "component": "scheduling",
                "safeSummary": f"No schedules configured in FHIR for specialty {specialty_normalized}.",
            },
        )
        db.commit()
        return {
            "ok": True,
            "specialty": specialty_normalized,
            "reasonCode": NO_PROVIDERS_AVAILABLE,
            "items": [],
        }

    all_slots: list[SlotDTO] = []

    # For each schedule, retrieve free slots and existing booked
    # appointments then filter out conflicting slots.
    for schedule in schedules:
        try:
            free_slots = await client.search_slots(
                schedule_ref=schedule.scheduleRef,
                status="free",
                start_from_utc=now_iso,
            )
            appointments = await client.search_appointments(
                practitioner_ref=schedule.practitionerRef,
                start_utc=now_iso,
                status="booked",
            )
        except FhirGatewayError as exc:
            raise map_fhir_error(exc) from exc

        clean_slots = _filter_slots_against_booked_appointments(
            slots=free_slots,
            appointments=appointments,
        )
        all_slots.extend(clean_slots)

    # Sort slots by start time, then practitioner for deterministic
    # ordering in responses.
    all_slots.sort(key=lambda item: (item.startUtc, item.practitionerRef or ""))

    reason_code = OK if all_slots else NO_SLOTS_AVAILABLE

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        actor_type="system",
        event_type="AVAILABILITY_REQUESTED",
        outcome="SUCCESS",
        reason_code=reason_code,
        payload={
            "component": "scheduling",
            "safeSummary": f"Returned {len(all_slots)} FHIR-backed slots for {specialty_normalized}.",
        },
    )
    db.commit()

    return {
        "ok": True,
        "specialty": specialty_normalized,
        "reasonCode": reason_code,
        "items": all_slots,
    }


async def book_appointment(
    *,
    db: Session,
    header_tenant_id: str,
    session_id: str,
    body_tenant_id: str,
    national_id: str,
    email: str,
    specialty: str,
    slot_id: str,
    idempotency_key: str | None,
    fhir_client: FhirClient | None = None,
) -> dict:
    """Book an appointment for a given slot and patient identity.

    This function performs tenant validation, idempotency checks,
    OTP verification, FHIR validations (slot/schedule ownership), and
    creates the appointment in FHIR while attempting to synchronize the
    slot status. It returns a JSON-serializable dictionary describing
    the booking result and records terminal idempotent results.
    """
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)

    # Idempotency key is required to protect against duplicate
    # booking attempts from the client side.
    if idempotency_key is None or not idempotency_key.strip():
        raise SchedulingError(reason_code=IDEMPOTENCY_KEY_REQUIRED)

    normalized_email = normalize_email(email)
    specialty_normalized = normalize_specialty_token(specialty)
    client = fhir_client or FhirClient()

    # Validate and normalize the provided national identity.
    try:
        normalized_identity_number, identity_type = validate_national_id_and_infer_type(
            national_id
        )
    except IdentityValidationError as exc:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="National ID, iqama, or Border ID is invalid.",
            status_code=422,
            details=exc.message,
        ) from exc

    # Build the hashed patient key used for OTP verification and patient
    # lookup/creation in the FHIR system.
    patient_key_hash = build_patient_key_hash(
        tenant_id=body_tenant_id,
        identity_type=identity_type,
        normalized_identity_number=normalized_identity_number,
    )

    # Ensure the patient completed OTP verification before proceeding.
    ensure_verified_otp_or_raise(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        patient_key_hash=patient_key_hash,
        email=normalized_email,
    )

    # Retrieve slot details from FHIR and validate it's still free.
    try:
        slot = await client.get_slot_or_raise(slot_id)
    except FhirGatewayError as exc:
        raise map_fhir_error(exc) from exc

    if slot.status != "free":
        # Respond with a friendly message: the slot is not free anymore.
        result = to_jsonable_dict(
            {
                "ok": True,
                "reasonCode": SLOT_TAKEN,
                "appointmentId": "",
                "appointmentRef": "",
                "specialty": specialty_normalized,
                "slot": {**slot.model_dump(), "status": "busy"},
                "message": "Selected slot is no longer available.",
            }
        )
        return result

    # Validate slot/schedule ownership and specialty consistency.
    if slot.specialty and normalize_specialty_token(slot.specialty) != specialty_normalized:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Selected slot does not belong to the requested specialty.",
            status_code=400,
        )

    if not slot.scheduleRef:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Selected slot is missing a schedule reference.",
            status_code=400,
        )

    try:
        schedule = await client.get_schedule_or_raise(slot.scheduleRef)
    except FhirGatewayError as exc:
        raise map_fhir_error(exc) from exc

    if schedule.tenantId and schedule.tenantId != body_tenant_id:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Selected slot does not belong to the requested tenant.",
            status_code=400,
        )

    if schedule.specialty and normalize_specialty_token(schedule.specialty) != specialty_normalized:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Selected slot does not belong to the requested specialty.",
            status_code=400,
        )

    if not schedule.practitionerRef:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Selected slot schedule is missing a practitioner reference.",
            status_code=400,
        )

    # Compute a stable fingerprint for the booking attempt. It includes
    # the patient, session, specialty, and slot identity so retries can
    # be matched even if the client resubmits the same request payload.
    request_hash = stable_request_hash(
        {
            "tenantId": body_tenant_id,
            "sessionId": session_id,
            "patientKeyHash": patient_key_hash,
            "email": normalized_email,
            "specialty": specialty_normalized,
            "slotId": slot.slotId,
            "slotRef": slot.slotRef,
        }
    )

    # If this idempotency key + request hash was already executed, return
    # the previously stored terminal result instead of executing again.
    replayed = get_replayed_result_or_raise(
        db=db,
        idempotency_key=idempotency_key.strip(),
        tenant_id=body_tenant_id,
        session_id=session_id,
        request_hash=request_hash,
    )
    if replayed is not None:
        return replayed

    # Emit an event indicating the booking attempt started.
    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        actor_type="patient",
        event_type="BOOKING_REQUESTED",
        outcome="INFO",
        reason_code=OK,
        payload={
            "component": "scheduling",
            "safeSummary": f"Booking requested for slot {slot.slotRef}.",
        },
    )
    db.commit()

    slot_start = parse_utc(slot.startUtc)
    slot_end = parse_utc(slot.endUtc)

    try:
        # Ensure the patient exists (or create) in FHIR and look for any
        # existing overlapping appointments for patient or practitioner.
        patient = await client.ensure_patient(
            tenant_id=body_tenant_id,
            patient_key_hash=patient_key_hash,
            email=normalized_email,
        )

        existing_for_patient = await client.search_appointments(
            patient_ref=patient.patientRef,
            start_utc=slot.startUtc,
            end_utc=slot.endUtc,
            status="booked",
        )

        # Block duplicate patient appointments that overlap the requested slot.
        for appointment in existing_for_patient:
            if not appointment.startUtc or not appointment.endUtc:
                continue

            if is_overlap(
                new_start=slot_start,
                new_end=slot_end,
                existing_start=parse_utc(appointment.startUtc),
                existing_end=parse_utc(appointment.endUtc),
            ):
                result = to_jsonable_dict(
                    {
                        "ok": True,
                        "reasonCode": DUPLICATE_APPOINTMENT_BLOCKED,
                        "appointmentId": appointment.appointmentId,
                        "appointmentRef": appointment.appointmentRef,
                        "specialty": specialty_normalized,
                        "slot": {**slot.model_dump(), "status": "busy"},
                        "message": "Duplicate appointment blocked.",
                    }
                )

                save_terminal_result(
                    db=db,
                    idempotency_key=idempotency_key.strip(),
                    tenant_id=body_tenant_id,
                    session_id=session_id,
                    request_hash=request_hash,
                    result=result,
                )
                emit_event(
                    db=db,
                    tenant_id=body_tenant_id,
                    session_id=session_id,
                    actor_type="system",
                    event_type="BOOKING_FAILED",
                    outcome="FAILURE",
                    reason_code=DUPLICATE_APPOINTMENT_BLOCKED,
                    payload={
                        "component": "scheduling",
                        "safeSummary": "Blocked duplicate patient booking.",
                    },
                )
                db.commit()
                return result

        existing_for_practitioner = await client.search_appointments(
            practitioner_ref=schedule.practitionerRef,
            start_utc=slot.startUtc,
            end_utc=slot.endUtc,
            status="booked",
        )

        # If a practitioner already has a booked appointment that includes
        # this slot reference, we treat the slot as taken.
        for appointment in existing_for_practitioner:
            if slot.slotRef in appointment.slotRefs:
                result = to_jsonable_dict(
                    {
                        "ok": True,
                        "reasonCode": SLOT_TAKEN,
                        "appointmentId": appointment.appointmentId,
                        "appointmentRef": appointment.appointmentRef,
                        "specialty": specialty_normalized,
                        "slot": {**slot.model_dump(), "status": "busy"},
                        "message": "Selected slot is no longer available.",
                    }
                )

                save_terminal_result(
                    db=db,
                    idempotency_key=idempotency_key.strip(),
                    tenant_id=body_tenant_id,
                    session_id=session_id,
                    request_hash=request_hash,
                    result=result,
                )
                emit_event(
                    db=db,
                    tenant_id=body_tenant_id,
                    session_id=session_id,
                    actor_type="system",
                    event_type="BOOKING_FAILED",
                    outcome="FAILURE",
                    reason_code=SLOT_TAKEN,
                    payload={
                        "component": "scheduling",
                        "safeSummary": "Blocked booking because slot was already reserved.",
                    },
                )
                db.commit()
                return result

        # Create the appointment in FHIR for this slot. This is the
        # authoritative booking step; later slot-status synchronization
        # is best-effort and should not undo a confirmed appointment.
        appointment = await client.create_appointment_for_slot(
            tenant_id=body_tenant_id,
            patient_ref=patient.patientRef,
            schedule=schedule,
            slot=slot,
            specialty=specialty_normalized,
        )

        slot_status_sync: dict[str, object] = {
            "attempted": True,
            "synced": False,
            "reasonCode": None,
        }

        booked_slot_payload = {**slot.model_dump(), "status": "busy"}

        # Attempt to update the slot status in FHIR so state stays
        # aligned across systems. Failures here are recorded but do not
        # rollback the created appointment.
        try:
            synced_slot = await client.update_slot_status(
                slot_id=slot.slotId,
                new_status="busy",
                comment=f"Booked via {appointment.appointmentRef}",
            )
            booked_slot_payload = synced_slot.model_dump()
            slot_status_sync["synced"] = True
        except FhirGatewayError as slot_sync_exc:
            slot_status_sync["reasonCode"] = slot_sync_exc.reason_code

    except FhirGatewayError as exc:
        # Map FHIR errors into scheduling-domain responses and persist
        # terminal results for retry-safe behavior when appropriate.
        mapped = map_fhir_error(exc)

        result = to_jsonable_dict(
            {
                "ok": True,
                "reasonCode": mapped.reason_code,
                "appointmentId": "",
                "appointmentRef": "",
                "specialty": specialty_normalized,
                "slot": {**slot.model_dump(), "status": "busy"},
                "message": mapped.user_message,
            }
        )

        if mapped.reason_code in {SLOT_TAKEN, APPOINTMENT_CREATE_FAILED}:
            save_terminal_result(
                db=db,
                idempotency_key=idempotency_key.strip(),
                tenant_id=body_tenant_id,
                session_id=session_id,
                request_hash=request_hash,
                result=result,
            )

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="BOOKING_FAILED",
            outcome="FAILURE",
            reason_code=mapped.reason_code,
            payload={
                "component": "scheduling",
                "safeSummary": mapped.user_message,
            },
        )
        db.commit()
        return result

    # Success: build and save the terminal result for idempotency and
    # emit a confirmation event for observability.
    result = to_jsonable_dict(
        {
            "ok": True,
            "reasonCode": OK,
            "appointmentId": appointment.appointmentId,
            "appointmentRef": appointment.appointmentRef,
            "specialty": specialty_normalized,
            "slot": booked_slot_payload,
            "slotStatusSync": slot_status_sync,
            "message": "Appointment booked successfully.",
        }
    )

    save_terminal_result(
        db=db,
        idempotency_key=idempotency_key.strip(),
        tenant_id=body_tenant_id,
        session_id=session_id,
        request_hash=request_hash,
        result=result,
    )

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        actor_type="system",
        event_type="BOOKING_CONFIRMED",
        outcome="SUCCESS",
        reason_code=OK,
        payload={
            "component": "scheduling",
            "safeSummary": f"Appointment confirmed as {appointment.appointmentRef}.",
            "slotRef": slot.slotRef,
            "slotStatusSync": slot_status_sync,
        },
    )
    db.commit()

    return result