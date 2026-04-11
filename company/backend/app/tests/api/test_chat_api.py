from __future__ import annotations

from dataclasses import dataclass


def hospital_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": "demo",
        "X-Session-Id": "patient-session-001",
        "X-Correlation-Id": "corr-chat-001",
    }


class FakeCandidate:
    def __init__(self, specialty_id: str, confidence: float) -> None:
        self.specialty_id = specialty_id
        self.confidence = confidence


class FakePrediction:
    def __init__(self) -> None:
        self.primary_specialty_id = "cardiology"
        self.top_candidates = [
            FakeCandidate("cardiology", 0.91),
            FakeCandidate("neurology", 0.06),
        ]
        self.needs_clarification = False
        self.reason_code = "OK"
        self.clarifier_question = None
        self.model_version = "test-1.0"


class FakeNlpService:
    def classify(self, message_text: str):
        return FakePrediction()


@dataclass
class FakeSlotDTO:
    slot_id: str
    slot_ref: str
    practitioner_ref: str
    practitioner_display: str
    specialty: str
    start_utc: str
    end_utc: str
    status: str
    

def test_chat_selection_accepts_slot_dto_items(client, monkeypatch) -> None:
    async def fake_list_available_slots(*, db, header_tenant_id, session_id, body_tenant_id, specialty):
        return {
            "ok": True,
            "specialty": specialty,
            "reasonCode": "OK",
            "items": [
                FakeSlotDTO(
                    slot_id="slot-1",
                    slot_ref="Slot/slot-1",
                    practitioner_ref="Practitioner/prac-1",
                    practitioner_display="Dr. Lina Alharbi",
                    specialty=specialty,
                    start_utc="2026-04-12T09:00:00Z",
                    end_utc="2026-04-12T09:30:00Z",
                    status="free",
                )
            ],
        }

    monkeypatch.setattr(
        "app.modules.orchestration.service.list_available_slots",
        fake_list_available_slots,
    )

    client.post(
        "/chat/direct/start",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "patient-session-001",
            "X-Correlation-Id": "corr-chat-001",
        },
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "action": "START_DIRECT_SCHEDULING",
        },
    )

    response = client.post(
        "/chat/selection",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "patient-session-001",
            "X-Correlation-Id": "corr-chat-001",
        },
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "selectionType": "specialty",
            "selectionId": "cardiology",
            "action": "SELECT_SPECIALTY",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selectionLists"][0]["type"] == "slot"
    assert body["selectionLists"][0]["items"][0]["id"] == "slot-1"

def test_chat_message_returns_specialty_choices(client) -> None:
    client.app.state.nlp_service = FakeNlpService()

    response = client.post(
        "/chat/message",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "I have chest pain when walking.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["userMessage"].startswith("I recommend Cardiology")
    assert body["selectionLists"][0]["type"] == "specialty"
    assert body["selectionLists"][0]["items"][0]["id"] == "cardiology"
    assert body["correlationId"] == "corr-chat-001"


def test_chat_direct_start_returns_supported_specialties(client) -> None:
    response = client.post(
        "/chat/direct/start",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "action": "START_DIRECT_SCHEDULING",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selectionLists"][0]["type"] == "specialty"
    assert len(body["selectionLists"][0]["items"]) >= 3


def test_chat_selection_for_specialty_returns_slot_list(client, monkeypatch) -> None:
    async def fake_list_available_slots(*, db, header_tenant_id, session_id, body_tenant_id, specialty):
        return {
            "ok": True,
            "specialty": specialty,
            "reasonCode": "OK",
            "items": [
                {
                    "slotId": "slot-1",
                    "slotRef": "Slot/slot-1",
                    "scheduleRef": "Schedule/schedule-1",
                    "practitionerRef": "Practitioner/prac-1",
                    "practitionerDisplay": "Dr. Lina Alharbi",
                    "specialty": specialty,
                    "startUtc": "2026-04-12T09:00:00Z",
                    "endUtc": "2026-04-12T09:30:00Z",
                    "status": "free",
                }
            ],
        }

    monkeypatch.setattr(
        "app.modules.orchestration.service.list_available_slots",
        fake_list_available_slots,
    )

    client.post(
        "/chat/direct/start",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "action": "START_DIRECT_SCHEDULING",
        },
    )

    response = client.post(
        "/chat/selection",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "selectionType": "specialty",
            "selectionId": "cardiology",
            "action": "SELECT_SPECIALTY",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selectionLists"][0]["type"] == "slot"
    assert body["selectionLists"][0]["items"][0]["id"] == "slot-1"


def test_chat_confirm_appointment_returns_confirmation_summary(client, monkeypatch) -> None:
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
    ):
        return {
            "ok": True,
            "reasonCode": "OK",
            "appointmentId": "appt-1",
            "appointmentRef": "Appointment/appt-1",
            "specialty": specialty,
            "slot": {
                "slotId": slot_id,
                "slotRef": f"Slot/{slot_id}",
                "scheduleRef": "Schedule/schedule-1",
                "practitionerRef": "Practitioner/prac-1",
                "practitionerDisplay": "Dr. Lina Alharbi",
                "specialty": specialty,
                "startUtc": "2026-04-12T09:00:00Z",
                "endUtc": "2026-04-12T09:30:00Z",
                "status": "busy",
            },
            "message": "Appointment booked successfully.",
        }

    monkeypatch.setattr(
        "app.modules.orchestration.service.book_appointment",
        fake_book_appointment,
    )

    response = client.post(
        "/chat/confirm",
        headers={**hospital_headers(), "Idempotency-Key": "idem-chat-1"},
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "action": "CONFIRM_APPOINTMENT",
            "specialtyId": "cardiology",
            "slotId": "slot-1",
            "nationalId": "2123456788",
            "email": "patient@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confirmationType"] == "appointment"
    assert body["bookingReferenceId"] == "Appointment/appt-1"
    assert body["confirmationSummary"]["doctorLabel"] == "Dr. Lina Alharbi"
    
    
def test_chat_renewal_identify_returns_fhir_driven_medications(client, monkeypatch) -> None:
    class FakeItem:
        def __init__(self, ref: str, display: str, dosage: str) -> None:
            self.medicationRequestRef = ref
            self.medicationDisplay = display
            self.dosageText = dosage

    class FakeSignals:
        patientRef = "Patient/123"
        patientFound = True
        eligible = True
        items = [
            FakeItem("MedicationRequest/1", "Metformin", "500 mg twice daily"),
            FakeItem("MedicationRequest/2", "Atorvastatin", "20 mg nightly"),
        ]

    async def fake_get_medication_renewal_signals(*, patient_key_hash: str):
        return FakeSignals()

    class FakeFhirClient:
        async def get_medication_renewal_signals(self, *, patient_key_hash: str):
            return await fake_get_medication_renewal_signals(patient_key_hash=patient_key_hash)

    monkeypatch.setattr(
        "app.modules.orchestration.service.FhirClient",
        lambda: FakeFhirClient(),
    )

    client.post(
        "/chat/renewal/request",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "patient-session-renew-001",
            "X-Correlation-Id": "corr-renew-001",
        },
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-renew-001",
            "action": "REQUEST_MEDICATION_RENEWAL",
        },
    )

    response = client.post(
        "/chat/renewal/identify",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "patient-session-renew-001",
            "X-Correlation-Id": "corr-renew-001",
        },
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-renew-001",
            "nationalId": "5000000001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selectionLists"][0]["type"] == "medication"
    assert body["selectionLists"][0]["items"][0]["label"] == "Metformin"
    assert body["selectionLists"][0]["items"][1]["label"] == "Atorvastatin"