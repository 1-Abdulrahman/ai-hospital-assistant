from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import OtpRecord
from app.modules.fhir_gateway.client import FhirClient
from app.modules.fhir_gateway.reason_codes import FhirGatewayError
from app.modules.fhir_gateway.schemas import AppointmentDTO, ScheduleDTO, SlotDTO
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
    return datetime.now(UTC)


def to_utc_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise SchedulingError(
            reason_code=INVALID_REQUEST,
            user_message="Datetime must be timezone-aware UTC.",
        )
    return parsed.astimezone(UTC)


def is_overlap(
    *,
    new_start: datetime,
    new_end: datetime,
    existing_start: datetime,
    existing_end: datetime,
) -> bool:
    return new_start < existing_end and new_end > existing_start


def ensure_verified_otp_or_raise(
    *,
    db: Session,
    tenant_id: str,
    session_id: str,
    patient_key_hash: str,
    email: str,
) -> None:
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
        raise SchedulingError(reason_code=OTP_NOT_VERIFIED)


def map_fhir_error(exc: FhirGatewayError) -> SchedulingError:
    if exc.reason_code in {"FHIR_UNAVAILABLE", "FHIR_TIMEOUT"}:
        return SchedulingError(
            reason_code=FHIR_UNAVAILABLE,
            user_message="Scheduling is temporarily unavailable because the FHIR service cannot be reached.",
            status_code=503,
            details=exc.details,
        )

    if exc.reason_code in {"APPOINTMENT_CONFLICT", "SLOT_NO_LONGER_AVAILABLE"}:
        return SchedulingError(
            reason_code=SLOT_TAKEN,
            status_code=409,
            details=exc.details,
        )

    if exc.reason_code == "APPOINTMENT_CREATE_FAILED":
        return SchedulingError(
            reason_code=APPOINTMENT_CREATE_FAILED,
            status_code=503,
            details=exc.details,
        )

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
    if not slots or not appointments:
        return slots

    occupied_slot_refs = {ref for appt in appointments for ref in appt.slotRefs}
    filtered: list[SlotDTO] = []

    for slot in slots:
        if slot.slotRef in occupied_slot_refs:
            continue

        slot_start = parse_utc(slot.startUtc)
        slot_end = parse_utc(slot.endUtc)

        conflict = False
        for appointment in appointments:
            if not appointment.startUtc or not appointment.endUtc:
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
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)

    specialty_normalized = specialty.strip().lower()
    now_value = now_utc or utc_now()
    now_iso = to_utc_z(now_value)
    client = fhir_client or FhirClient()

    try:
        schedules = await client.search_schedules(
            tenant_id=body_tenant_id,
            specialty=specialty_normalized,
            active=True,
        )
    except FhirGatewayError as exc:
        raise map_fhir_error(exc) from exc

    if not schedules:
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
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)

    if idempotency_key is None or not idempotency_key.strip():
        raise SchedulingError(reason_code=IDEMPOTENCY_KEY_REQUIRED)

    normalized_email = normalize_email(email)
    specialty_normalized = specialty.strip().lower()
    client = fhir_client or FhirClient()

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

    patient_key_hash = build_patient_key_hash(
        tenant_id=body_tenant_id,
        identity_type=identity_type,
        normalized_identity_number=normalized_identity_number,
    )

    ensure_verified_otp_or_raise(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        patient_key_hash=patient_key_hash,
        email=normalized_email,
    )

    try:
        slot = await client.get_slot_or_raise(slot_id)
    except FhirGatewayError as exc:
        raise map_fhir_error(exc) from exc

    if slot.status != "free":
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

    if slot.specialty and slot.specialty.strip().lower() != specialty_normalized:
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

    if schedule.specialty and schedule.specialty.strip().lower() != specialty_normalized:
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

    replayed = get_replayed_result_or_raise(
        db=db,
        idempotency_key=idempotency_key.strip(),
        tenant_id=body_tenant_id,
        session_id=session_id,
        request_hash=request_hash,
    )
    if replayed is not None:
        return replayed

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
        patient = await client.ensure_patient(
            tenant_id=body_tenant_id,
            patient_key_hash=patient_key_hash,
        )

        existing_for_patient = await client.search_appointments(
            patient_ref=patient.patientRef,
            start_utc=slot.startUtc,
            end_utc=slot.endUtc,
            status="booked",
        )

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

        created = await client.create_appointment(
            tenant_id=body_tenant_id,
            patient_ref=patient.patientRef,
            practitioner_ref=schedule.practitionerRef,
            specialty_code=specialty_normalized,
            specialty_display=schedule.specialty or specialty_normalized.replace("_", " ").title(),
            start_utc=slot.startUtc,
            end_utc=slot.endUtc,
            slot_ref=slot.slotRef,
            description=f"Scheduled via offline MVP for {specialty_normalized}",
        )

    except FhirGatewayError as exc:
        mapped = map_fhir_error(exc)

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
        raise mapped from exc

    try:
        await client.update_slot_status(
            slot_id=slot.slotId,
            new_status="busy",
            comment=f"Booked via {created.appointmentRef}",
        )
    except FhirGatewayError:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="SLOT_STATUS_SYNC_FAILED",
            outcome="FAILURE",
            reason_code="FHIR_SLOT_SYNC_FAILED",
            payload={
                "component": "scheduling",
                "safeSummary": "Appointment was created but slot busy sync failed.",
            },
        )
        db.commit()

    result = to_jsonable_dict(
        {
            "ok": True,
            "reasonCode": OK,
            "appointmentId": created.appointmentId,
            "appointmentRef": created.appointmentRef,
            "specialty": specialty_normalized,
            "slot": {**slot.model_dump(), "status": "busy"},
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
            "safeSummary": f"Appointment booked successfully for slot {slot.slotRef}.",
        },
    )
    db.commit()

    return result