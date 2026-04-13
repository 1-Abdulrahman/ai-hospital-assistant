from __future__ import annotations

from app.modules.scheduling.reason_codes import (
    IDEMPOTENCY_KEY_REQUIRED,
    SLOT_TAKEN,
    SchedulingError,
)


def hospital_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": "demo",
        "X-Session-Id": "patient-session-001",
        "X-Correlation-Id": "corr-test-001",
    }


def slot_payload(status: str = "free") -> dict:
    return {
        "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        "slotRef": "Slot/slot-sched-cardiology-prac-card-1-20260408T0900",
        "scheduleRef": "Schedule/sched-cardiology-prac-card-1",
        "practitionerRef": "Practitioner/prac-card-1",
        "practitionerDisplay": "Dr. Lina Alharbi",
        "specialty": "cardiology",
        "startUtc": "2026-04-08T09:00:00Z",
        "endUtc": "2026-04-08T09:30:00Z",
        "status": status,
    }


def test_scheduling_slots_returns_fhir_native_slots(client, monkeypatch) -> None:
    async def fake_list_available_slots(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        specialty,
        fhir_client=None,
    ):
        return {
            "ok": True,
            "specialty": "cardiology",
            "reasonCode": "OK",
            "items": [slot_payload()],
        }

    monkeypatch.setattr("app.api.routes.scheduling.list_available_slots", fake_list_available_slots)

    response = client.post(
        "/scheduling/slots",
        headers=hospital_headers(),
        json={"tenantId": "demo", "specialty": "cardiology"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["ok"] is True
    assert body["reasonCode"] == "OK"
    assert body["items"][0]["slotId"] == "slot-sched-cardiology-prac-card-1-20260408T0900"
    assert body["items"][0]["slotRef"] == "Slot/slot-sched-cardiology-prac-card-1-20260408T0900"


def test_scheduling_slots_returns_no_providers_when_no_schedule_exists(client, monkeypatch) -> None:
    async def fake_list_available_slots(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        specialty,
        fhir_client=None,
    ):
        return {
            "ok": True,
            "specialty": "cardiology",
            "reasonCode": "NO_PROVIDERS_AVAILABLE",
            "items": [],
        }

    monkeypatch.setattr("app.api.routes.scheduling.list_available_slots", fake_list_available_slots)

    response = client.post(
        "/scheduling/slots",
        headers=hospital_headers(),
        json={"tenantId": "demo", "specialty": "cardiology"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reasonCode"] == "NO_PROVIDERS_AVAILABLE"
    assert body["items"] == []


def test_scheduling_book_requires_idempotency_key(client, monkeypatch) -> None:
    async def fake_book_appointment(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        national_id,
        email,
        specialty,
        slot_id,
        idempotency_key,
        fhir_client=None,
    ):
        if idempotency_key is None:
            raise SchedulingError(reason_code=IDEMPOTENCY_KEY_REQUIRED)
        return {
            "ok": True,
            "reasonCode": "OK",
            "appointmentId": "appt-1",
            "appointmentRef": "Appointment/appt-1",
            "specialty": "cardiology",
            "slot": slot_payload(status="busy"),
            "message": "Appointment booked successfully.",
        }

    monkeypatch.setattr("app.api.routes.scheduling.book_appointment", fake_book_appointment)

    response = client.post(
        "/scheduling/book",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
            "specialty": "cardiology",
            "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["reasonCode"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert "correlationId" in body


def test_scheduling_book_returns_slot_taken_for_busy_slot(client, monkeypatch) -> None:
    async def fake_book_appointment(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        national_id,
        email,
        specialty,
        slot_id,
        idempotency_key,
        fhir_client=None,
    ):
        return {
            "ok": True,
            "reasonCode": SLOT_TAKEN,
            "appointmentId": "",
            "appointmentRef": "",
            "specialty": "cardiology",
            "slot": slot_payload(status="busy"),
            "message": "Selected slot is no longer available.",
        }

    monkeypatch.setattr("app.api.routes.scheduling.book_appointment", fake_book_appointment)

    response = client.post(
        "/scheduling/book",
        headers={**hospital_headers(), "Idempotency-Key": "idem-1"},
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
            "specialty": "cardiology",
            "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reasonCode"] == "SLOT_TAKEN"
    assert body["slot"]["status"] == "busy"


def test_scheduling_book_success_returns_safe_payload(client, monkeypatch) -> None:
    async def fake_book_appointment(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        national_id,
        email,
        specialty,
        slot_id,
        idempotency_key,
        fhir_client=None,
    ):
        return {
            "ok": True,
            "reasonCode": "OK",
            "appointmentId": "appt-1",
            "appointmentRef": "Appointment/appt-1",
            "specialty": "cardiology",
            "slot": slot_payload(status="busy"),
            "message": "Appointment booked successfully.",
        }

    monkeypatch.setattr("app.api.routes.scheduling.book_appointment", fake_book_appointment)

    response = client.post(
        "/scheduling/book",
        headers={**hospital_headers(), "Idempotency-Key": "idem-1"},
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
            "specialty": "cardiology",
            "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["ok"] is True
    assert body["reasonCode"] == "OK"
    assert body["appointmentId"] == "appt-1"
    assert body["appointmentRef"] == "Appointment/appt-1"
    assert "entry" not in body
    assert "resourceType" not in body
    assert body["slot"]["slotRef"] == "Slot/slot-sched-cardiology-prac-card-1-20260408T0900"