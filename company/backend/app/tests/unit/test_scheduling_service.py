from __future__ import annotations

from datetime import datetime

import pytest

from app.db.models import Event, OtpRecord
from app.modules.fhir_gateway.reason_codes import FHIR_UNAVAILABLE, FhirGatewayError
from app.modules.fhir_gateway.schemas import (
    AppointmentDTO,
    PatientSummaryDTO,
    ScheduleDTO,
    SlotDTO,
)
from app.modules.otp.service import build_patient_key_hash
from app.modules.scheduling.reason_codes import (
    DUPLICATE_APPOINTMENT_BLOCKED,
    INVALID_REQUEST,
    NO_PROVIDERS_AVAILABLE,
    NO_SLOTS_AVAILABLE,
    OK,
    OTP_NOT_VERIFIED,
    SLOT_TAKEN,
    SchedulingError,
)
from app.modules.scheduling.service import (
    book_appointment,
    is_overlap,
    list_available_slots,
)


def make_schedule(
    *,
    schedule_id: str = "sched-cardiology-prac-card-1",
    specialty: str = "cardiology",
    tenant_id: str = "demo",
    practitioner_ref: str = "Practitioner/prac-card-1",
    practitioner_display: str = "Dr. Lina Alharbi",
) -> ScheduleDTO:
    return ScheduleDTO(
        scheduleId=schedule_id,
        scheduleRef=f"Schedule/{schedule_id}",
        practitionerRef=practitioner_ref,
        practitionerDisplay=practitioner_display,
        specialty=specialty,
        tenantId=tenant_id,
        planningHorizonStartUtc="2026-04-08T00:00:00Z",
        planningHorizonEndUtc="2026-04-21T23:59:00Z",
        active=True,
    )


def make_slot(
    *,
    slot_id: str = "slot-sched-cardiology-prac-card-1-20260408T0900",
    schedule_ref: str = "Schedule/sched-cardiology-prac-card-1",
    specialty: str = "cardiology",
    practitioner_ref: str = "Practitioner/prac-card-1",
    practitioner_display: str = "Dr. Lina Alharbi",
    status: str = "free",
    start_utc: str = "2026-04-08T09:00:00Z",
    end_utc: str = "2026-04-08T09:30:00Z",
) -> SlotDTO:
    return SlotDTO(
        slotId=slot_id,
        slotRef=f"Slot/{slot_id}",
        scheduleRef=schedule_ref,
        practitionerRef=practitioner_ref,
        practitionerDisplay=practitioner_display,
        specialty=specialty,
        startUtc=start_utc,
        endUtc=end_utc,
        status=status,
    )


def make_appointment(
    *,
    appointment_id: str = "appt-1",
    slot_ref: str | None = None,
    patient_ref: str = "Patient/patient-1",
    practitioner_ref: str = "Practitioner/prac-card-1",
    start_utc: str = "2026-04-08T09:00:00Z",
    end_utc: str = "2026-04-08T09:30:00Z",
    specialty: str = "cardiology",
) -> AppointmentDTO:
    return AppointmentDTO(
        appointmentId=appointment_id,
        appointmentRef=f"Appointment/{appointment_id}",
        status="booked",
        startUtc=start_utc,
        endUtc=end_utc,
        specialty=specialty,
        practitionerRef=practitioner_ref,
        practitionerDisplay="Dr. Lina Alharbi",
        patientRef=patient_ref,
        patientDisplay="Demo Patient",
        tenantId="demo",
        slotRefs=[slot_ref] if slot_ref else [],
    )


class FakeFhirClient:
    def __init__(
        self,
        *,
        schedules: list[ScheduleDTO] | None = None,
        slots_by_schedule: dict[str, list[SlotDTO]] | None = None,
        slots_by_id: dict[str, SlotDTO] | None = None,
        patient_appointments: list[AppointmentDTO] | None = None,
        practitioner_appointments: list[AppointmentDTO] | None = None,
        created_appointment: AppointmentDTO | None = None,
        update_slot_should_fail: bool = False,
    ) -> None:
        self.schedules = schedules or []
        self.slots_by_schedule = slots_by_schedule or {}
        self.slots_by_id = slots_by_id or {}
        self.patient_appointments = patient_appointments or []
        self.practitioner_appointments = practitioner_appointments or []
        self.created_appointment = created_appointment or make_appointment()
        self.update_slot_should_fail = update_slot_should_fail
        self.updated_slot_calls: list[tuple[str, str, str | None]] = []

    async def search_schedules(self, *, tenant_id: str, specialty: str, active: bool = True):
        return [item for item in self.schedules if item.specialty == specialty and item.tenantId == tenant_id]

    async def search_slots(
        self,
        *,
        schedule_ref: str,
        status: str = "free",
        start_from_utc: str | None = None,
    ):
        items = list(self.slots_by_schedule.get(schedule_ref, []))
        if status:
            items = [item for item in items if item.status == status]
        if start_from_utc:
            items = [item for item in items if item.startUtc >= start_from_utc]
        return items

    async def search_appointments(
        self,
        *,
        patient_ref: str | None = None,
        practitioner_ref: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
        status: str | None = None,
    ):
        if patient_ref:
            return self.patient_appointments
        if practitioner_ref:
            return self.practitioner_appointments
        return []

    async def get_slot_or_raise(self, slot_id: str):
        return self.slots_by_id[slot_id]

    async def get_schedule_or_raise(self, schedule_ref: str):
        for schedule in self.schedules:
            if schedule.scheduleRef == schedule_ref:
                return schedule
        raise AssertionError(f"Schedule not found in fake client: {schedule_ref}")

    async def ensure_patient(self, *, tenant_id: str, patient_key_hash: str, display_name=None):
        return PatientSummaryDTO(
            patientId="patient-1",
            patientRef="Patient/patient-1",
            tenantId=tenant_id,
            patientKeyHash=patient_key_hash,
            displayName=None,
        )

    async def create_appointment(self, **kwargs):
        return self.created_appointment

    async def update_slot_status(self, *, slot_id: str, new_status: str, comment: str | None = None):
        self.updated_slot_calls.append((slot_id, new_status, comment))
        if self.update_slot_should_fail:
            raise FhirGatewayError(
                reason_code=FHIR_UNAVAILABLE,
                user_message="FHIR unavailable",
                status_code=503,
            )
        slot = self.slots_by_id[slot_id]
        return SlotDTO(**{**slot.model_dump(), "status": new_status})


def add_verified_otp(
    db_session,
    *,
    session_id: str,
    email: str,
    national_id: str,
) -> None:
    patient_key_hash = build_patient_key_hash(
        tenant_id="demo",
        identity_type="iqama",
        normalized_identity_number=national_id,
    )

    db_session.add(
        OtpRecord(
            id="otp-verified",
            tenant_id="demo",
            session_id=session_id,
            patient_key_hash=patient_key_hash,
            email=email,
            otp_hash="hashed",
            expires_at=datetime(2026, 4, 8, 12, 0),
            attempts=0,
            verified=True,
        )
    )
    db_session.commit()

@pytest.mark.asyncio
async def test_list_available_slots_filters_out_past_slots(db_session) -> None:
    schedule = make_schedule()
    past_slot = make_slot(
        start_utc="2026-04-08T09:00:00Z",
        end_utc="2026-04-08T09:30:00Z",
    )

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_schedule={schedule.scheduleRef: [past_slot]},
        practitioner_appointments=[],
    )

    result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        specialty="cardiology",
        now_utc=datetime.fromisoformat("2026-04-12T08:00:00+00:00"),
        fhir_client=client,
    )

    assert result["reasonCode"] == NO_SLOTS_AVAILABLE
    assert result["items"] == []

@pytest.mark.asyncio
async def test_list_available_slots_reads_fhir_schedules_and_slots(db_session) -> None:
    schedule = make_schedule()
    slot = make_slot()

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_schedule={schedule.scheduleRef: [slot]},
        practitioner_appointments=[],
    )

    result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        specialty="cardiology",
        now_utc=datetime.fromisoformat("2026-04-08T08:00:00+00:00"),
        fhir_client=client,
    )

    assert result["reasonCode"] == OK
    assert len(result["items"]) == 1
    assert result["items"][0].slotId == "slot-sched-cardiology-prac-card-1-20260408T0900"


@pytest.mark.asyncio
async def test_list_available_slots_returns_no_providers_when_no_schedules_exist(db_session) -> None:
    client = FakeFhirClient(schedules=[])

    result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        specialty="cardiology",
        fhir_client=client,
    )

    assert result["reasonCode"] == NO_PROVIDERS_AVAILABLE
    assert result["items"] == []


@pytest.mark.asyncio
async def test_list_available_slots_returns_no_slots_when_schedules_exist_but_no_free_slots(db_session) -> None:
    schedule = make_schedule()
    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_schedule={schedule.scheduleRef: []},
    )

    result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        specialty="cardiology",
        fhir_client=client,
    )

    assert result["reasonCode"] == NO_SLOTS_AVAILABLE
    assert result["items"] == []


@pytest.mark.asyncio
async def test_list_available_slots_filters_out_slots_occupied_by_booked_appointments(db_session) -> None:
    schedule = make_schedule()
    slot = make_slot()
    appointment = make_appointment(slot_ref=slot.slotRef)

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_schedule={schedule.scheduleRef: [slot]},
        practitioner_appointments=[appointment],
    )

    result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        specialty="cardiology",
        fhir_client=client,
    )

    assert result["reasonCode"] == NO_SLOTS_AVAILABLE
    assert result["items"] == []


@pytest.mark.asyncio
async def test_book_requires_verified_otp(db_session) -> None:
    schedule = make_schedule()
    slot = make_slot()

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={slot.slotId: slot},
    )

    with pytest.raises(SchedulingError) as exc:
        await book_appointment(
            db=db_session,
            header_tenant_id="demo",
            session_id="patient-session-1",
            body_tenant_id="demo",
            national_id="2123456788",
            email="patient@example.com",
            specialty="cardiology",
            slot_id=slot.slotId,
            idempotency_key="idem-1",
            fhir_client=client,
        )

    assert exc.value.reason_code == OTP_NOT_VERIFIED


@pytest.mark.asyncio
async def test_book_rejects_slot_if_fhir_slot_status_is_busy(db_session) -> None:
    add_verified_otp(
        db_session,
        session_id="patient-session-1",
        email="patient@example.com",
        national_id="2123456788",
    )

    schedule = make_schedule()
    busy_slot = make_slot(status="busy")

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={busy_slot.slotId: busy_slot},
    )

    result = await book_appointment(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        specialty="cardiology",
        slot_id=busy_slot.slotId,
        idempotency_key="idem-1",
        fhir_client=client,
    )

    assert result["reasonCode"] == SLOT_TAKEN
    assert result["slot"]["status"] == "busy"


@pytest.mark.asyncio
async def test_book_rejects_slot_when_schedule_specialty_mismatches_request(db_session) -> None:
    add_verified_otp(
        db_session,
        session_id="patient-session-1",
        email="patient@example.com",
        national_id="2123456788",
    )

    schedule = make_schedule(specialty="dermatology")
    slot = make_slot(schedule_ref=schedule.scheduleRef, specialty="dermatology")

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={slot.slotId: slot},
    )

    with pytest.raises(SchedulingError) as exc:
        await book_appointment(
            db=db_session,
            header_tenant_id="demo",
            session_id="patient-session-1",
            body_tenant_id="demo",
            national_id="2123456788",
            email="patient@example.com",
            specialty="cardiology",
            slot_id=slot.slotId,
            idempotency_key="idem-1",
            fhir_client=client,
        )

    assert exc.value.reason_code == INVALID_REQUEST


@pytest.mark.asyncio
async def test_book_blocks_duplicate_patient_booking(db_session) -> None:
    add_verified_otp(
        db_session,
        session_id="patient-session-1",
        email="patient@example.com",
        national_id="2123456788",
    )

    schedule = make_schedule()
    slot = make_slot()
    existing = make_appointment(
        appointment_id="appt-existing",
        patient_ref="Patient/patient-1",
        practitioner_ref=schedule.practitionerRef or "",
        start_utc=slot.startUtc,
        end_utc=slot.endUtc,
        specialty="cardiology",
    )

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={slot.slotId: slot},
        patient_appointments=[existing],
    )

    result = await book_appointment(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        specialty="cardiology",
        slot_id=slot.slotId,
        idempotency_key="idem-1",
        fhir_client=client,
    )

    assert result["reasonCode"] == DUPLICATE_APPOINTMENT_BLOCKED
    assert result["appointmentId"] == "appt-existing"


@pytest.mark.asyncio
async def test_book_blocks_taken_slot_when_existing_appointment_uses_same_slot(db_session) -> None:
    add_verified_otp(
        db_session,
        session_id="patient-session-1",
        email="patient@example.com",
        national_id="2123456788",
    )

    schedule = make_schedule()
    slot = make_slot()
    existing = make_appointment(
        appointment_id="appt-existing",
        slot_ref=slot.slotRef,
        patient_ref="Patient/another-patient",
        practitioner_ref=schedule.practitionerRef or "",
        start_utc=slot.startUtc,
        end_utc=slot.endUtc,
        specialty="cardiology",
    )

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={slot.slotId: slot},
        practitioner_appointments=[existing],
    )

    result = await book_appointment(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        specialty="cardiology",
        slot_id=slot.slotId,
        idempotency_key="idem-1",
        fhir_client=client,
    )

    assert result["reasonCode"] == SLOT_TAKEN
    assert result["appointmentId"] == "appt-existing"


@pytest.mark.asyncio
async def test_book_success_creates_appointment_and_updates_slot_status(db_session) -> None:
    add_verified_otp(
        db_session,
        session_id="patient-session-1",
        email="patient@example.com",
        national_id="2123456788",
    )

    schedule = make_schedule()
    slot = make_slot()
    created = make_appointment(
        appointment_id="appt-new",
        slot_ref=slot.slotRef,
        patient_ref="Patient/patient-1",
        practitioner_ref=schedule.practitionerRef or "",
        start_utc=slot.startUtc,
        end_utc=slot.endUtc,
        specialty="cardiology",
    )

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={slot.slotId: slot},
        created_appointment=created,
    )

    result = await book_appointment(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        specialty="cardiology",
        slot_id=slot.slotId,
        idempotency_key="idem-1",
        fhir_client=client,
    )

    assert result["reasonCode"] == OK
    assert result["appointmentId"] == "appt-new"
    assert result["slot"]["status"] == "busy"
    assert client.updated_slot_calls == [
        (
            slot.slotId,
            "busy",
            f"Booked via {created.appointmentRef}",
        )
    ]


@pytest.mark.asyncio
async def test_book_success_still_returns_ok_if_slot_status_sync_fails_after_appointment_create(db_session) -> None:
    add_verified_otp(
        db_session,
        session_id="patient-session-1",
        email="patient@example.com",
        national_id="2123456788",
    )

    schedule = make_schedule()
    slot = make_slot()
    created = make_appointment(
        appointment_id="appt-new",
        slot_ref=slot.slotRef,
        patient_ref="Patient/patient-1",
        practitioner_ref=schedule.practitionerRef or "",
        start_utc=slot.startUtc,
        end_utc=slot.endUtc,
        specialty="cardiology",
    )

    client = FakeFhirClient(
        schedules=[schedule],
        slots_by_id={slot.slotId: slot},
        created_appointment=created,
        update_slot_should_fail=True,
    )

    result = await book_appointment(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        specialty="cardiology",
        slot_id=slot.slotId,
        idempotency_key="idem-1",
        fhir_client=client,
    )

    assert result["reasonCode"] == OK
    assert result["appointmentId"] == "appt-new"

    event = (
        db_session.query(Event)
        .filter(Event.event_type == "SLOT_STATUS_SYNC_FAILED")
        .first()
    )
    assert event is not None


def test_overlap_detection_matches_frozen_rule() -> None:
    assert is_overlap(
        new_start=datetime.fromisoformat("2026-04-08T09:00:00+00:00"),
        new_end=datetime.fromisoformat("2026-04-08T09:30:00+00:00"),
        existing_start=datetime.fromisoformat("2026-04-08T09:15:00+00:00"),
        existing_end=datetime.fromisoformat("2026-04-08T09:45:00+00:00"),
    ) is True