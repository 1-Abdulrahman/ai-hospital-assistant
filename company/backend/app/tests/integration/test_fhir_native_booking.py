from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.db.models import OtpRecord
from app.modules.otp.service import build_patient_key_hash
from app.modules.scheduling.service import book_appointment, list_available_slots


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
            id=uuid.uuid4().hex,
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
async def test_booking_creates_appointment_and_marks_slot_busy(db_session, live_fhir_client) -> None:
    session_id = f"patient-session-{uuid.uuid4().hex[:8]}"
    email = "patient@example.com"
    national_id = "2123456788"

    add_verified_otp(
        db_session,
        session_id=session_id,
        email=email,
        national_id=national_id,
    )

    slots_result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id=session_id,
        body_tenant_id="demo",
        specialty="cardiology",
        fhir_client=live_fhir_client,
    )

    assert slots_result["items"], "Expected at least one free cardiology slot in seeded HAPI data."

    chosen_slot = slots_result["items"][0]

    result = await book_appointment(
        db=db_session,
        header_tenant_id="demo",
        session_id=session_id,
        body_tenant_id="demo",
        national_id=national_id,
        email=email,
        specialty="cardiology",
        slot_id=chosen_slot.slotId,
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        fhir_client=live_fhir_client,
    )

    assert result["reasonCode"] == "OK"
    assert result["appointmentId"]
    assert result["appointmentRef"]

    live_slot = await live_fhir_client.get_slot_or_raise(chosen_slot.slotId)
    assert live_slot.status == "busy"

    appointments = await live_fhir_client.search_appointments(
        practitioner_ref=chosen_slot.practitionerRef,
        start_utc=chosen_slot.startUtc,
        end_utc=chosen_slot.endUtc,
        status="booked",
    )

    assert any(item.appointmentRef == result["appointmentRef"] for item in appointments)
    assert any(chosen_slot.slotRef in item.slotRefs for item in appointments)