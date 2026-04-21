from __future__ import annotations

from dataclasses import dataclass

import json

from app.db.models import AssistantSession, Event

def hospital_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": "demo",
        "X-Session-Id": "patient-session-001",
        "X-Correlation-Id": "corr-chat-001",
    }
    
    
def make_prediction(
    *,
    primary_specialty_id: str | None = "cardiology",
    top_candidates=None,
    needs_clarification: bool = False,
    reason_code: str = "OK",
    clarifier_question: str | None = None,
    clarification_key: str | None = None,
    clarification_quick_replies=(),
    model_version: str = "test-1.0",
    input_summary: str = "safe-summary",
):
    class _Prediction:
        pass

    obj = _Prediction()
    obj.primary_specialty_id = primary_specialty_id
    obj.top_candidates = top_candidates or [
        FakeCandidate("cardiology", 0.91),
        FakeCandidate("neurology", 0.06),
    ]
    obj.needs_clarification = needs_clarification
    obj.reason_code = reason_code
    obj.clarifier_question = clarifier_question
    obj.clarification_key = clarification_key
    obj.clarification_quick_replies = clarification_quick_replies
    obj.model_version = model_version
    obj.input_summary = input_summary
    return obj


class FakeCandidate:
    def __init__(self, specialty_id: str, confidence: float) -> None:
        self.specialty_id = specialty_id
        self.confidence = confidence

class FakeQuickReply:
    def __init__(self, label: str, value: str, action: str | None = None) -> None:
        self.label = label
        self.value = value
        self.action = action

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
        self.clarification_key = None
        self.clarification_quick_replies = ()
        self.model_version = "test-1.0"
        self.input_summary = "chest pain when walking"
        self.original_input_summary = "I have chest pain when walking."
        self.cleaned_input_summary = "i have chest pain when walking"
        self.normalized_input_summary = "i have chest pain when walking"
        self.preprocessing_actions = ("basic_cleanup",)
        
class FakeAmbiguousPrediction:
    def __init__(self) -> None:
        self.primary_specialty_id = None
        self.top_candidates = [
            FakeCandidate("gastroenterology", 0.32),
            FakeCandidate("general_practice", 0.16),
            FakeCandidate("cardiology", 0.11),
        ]
        self.needs_clarification = True
        self.reason_code = "NEEDS_CLARIFICATION"
        self.clarifier_question = (
            "I am not fully confident yet. Add more detail if you want, "
            "or choose one of the suggested specialties to continue."
        )
        self.clarification_key = "free-text-clarification-only"
        self.clarification_quick_replies = (
            FakeQuickReply(
                "I will give more details",
                "I will give more details.",
                "PROMPT_FOR_TEXT",
            ),
        )
        self.model_version = "test-1.0"
        self.input_summary = "i have a stomach ache"
        self.original_input_summary = "I have a stomach ache"
        self.cleaned_input_summary = "i have a stomach ache"
        self.normalized_input_summary = "i have a stomach ache"
        self.preprocessing_actions = ("basic_cleanup",)


class FakeAmbiguousNlpService:
    def classify(self, message_text: str):
        return FakeAmbiguousPrediction()


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


def test_chat_selection_for_specialty_requests_continuity_identity(client) -> None:
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
    assert body["requiresContinuityIdentity"] is True
    assert body.get("showConsentNotice") in (None, False)
    assert "continuity of care" in body["userMessage"].lower()


def test_chat_continuity_identify_accepts_slot_dto_items(client, monkeypatch) -> None:
    class FakePatient:
        patientRef = "Patient/patient-1"

    class FakeContinuity:
        hasPriorAppointments = True
        totalAppointments = 2
        lastAppointmentStartUtc = "2026-04-10T09:00:00Z"
        lastPractitionerRef = "Practitioner/prac-1"
        lastPractitionerDisplay = "Dr. Lina Alharbi"

    class FakeFhirClient:
        async def get_patient_or_raise(self, *, tenant_id, patient_key_hash):
            return FakePatient()

        async def get_continuity_signals(self, *, patient_ref, specialty):
            return FakeContinuity()

    async def fake_list_available_slots(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        specialty,
    ):
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
        "app.modules.orchestration.service.FhirClient",
        lambda: FakeFhirClient(),
    )
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

    client.post(
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

    response = client.post(
        "/chat/continuity/identify",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "nationalId": "2123456788",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["isChronicContinuity"] is True
    assert body["continuity"]["matched"] is True
    assert body["continuity"]["preferredPractitionerRef"] == "Practitioner/prac-1"
    assert body["continuity"]["preferredPractitionerDisplay"] == "Dr. Lina Alharbi"
    assert body["continuity"]["preferredPractitionerHasAvailability"] is True
    assert "prioritized" in body["continuity"]["message"].lower()

    assert body["selectionLists"][0]["type"] == "slot"
    assert body["selectionLists"][0]["items"][0]["id"] == "slot-1"

    meta = body["selectionLists"][0]["items"][0]["meta"]
    assert meta["practitionerRef"] == "Practitioner/prac-1"
    assert meta["practitionerDisplay"] == "Dr. Lina Alharbi"
    assert meta["specialtyId"] == "cardiology"
    assert meta["specialtyDisplay"] == "Cardiology"
    assert meta["dateKey"] == "2026-04-12"
    assert meta["displayTime"] == "9:00 AM"
    assert meta["isPreferredPractitioner"] is True


def test_chat_continuity_identify_returns_prioritized_slots(client, monkeypatch) -> None:
    class FakePatient:
        patientRef = "Patient/patient-1"

    class FakeContinuity:
        hasPriorAppointments = True
        totalAppointments = 2
        lastAppointmentStartUtc = "2026-04-10T09:00:00Z"
        lastPractitionerRef = "Practitioner/prac-card-1"
        lastPractitionerDisplay = "Dr. Lina Alharbi"

    class FakeFhirClient:
        async def get_patient_or_raise(self, *, tenant_id, patient_key_hash):
            return FakePatient()

        async def get_continuity_signals(self, *, patient_ref, specialty):
            return FakeContinuity()

    async def fake_list_available_slots(
        *,
        db,
        header_tenant_id,
        session_id,
        body_tenant_id,
        specialty,
    ):
        return {
            "ok": True,
            "specialty": specialty,
            "reasonCode": "OK",
            "items": [
                {
                    "slotId": "slot-2",
                    "slotRef": "Slot/slot-2",
                    "scheduleRef": "Schedule/schedule-2",
                    "practitionerRef": "Practitioner/prac-card-2",
                    "practitionerDisplay": "Dr. Omar Saleh",
                    "specialty": specialty,
                    "startUtc": "2026-04-12T11:00:00Z",
                    "endUtc": "2026-04-12T11:30:00Z",
                    "status": "free",
                },
                {
                    "slotId": "slot-1",
                    "slotRef": "Slot/slot-1",
                    "scheduleRef": "Schedule/schedule-1",
                    "practitionerRef": "Practitioner/prac-card-1",
                    "practitionerDisplay": "Dr. Lina Alharbi",
                    "specialty": specialty,
                    "startUtc": "2026-04-12T09:00:00Z",
                    "endUtc": "2026-04-12T09:30:00Z",
                    "status": "free",
                },
            ],
        }

    monkeypatch.setattr(
        "app.modules.orchestration.service.FhirClient",
        lambda: FakeFhirClient(),
    )
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

    client.post(
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

    response = client.post(
        "/chat/continuity/identify",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "nationalId": "2123456788",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["isChronicContinuity"] is True
    assert body["continuity"]["matched"] is True
    assert body["continuity"]["preferredPractitionerRef"] == "Practitioner/prac-card-1"
    assert body["continuity"]["preferredPractitionerDisplay"] == "Dr. Lina Alharbi"
    assert body["continuity"]["preferredPractitionerHasAvailability"] is True

    assert body["selectionLists"][0]["type"] == "slot"
    assert body["selectionLists"][0]["items"][0]["label"].startswith("Dr. Lina Alharbi")

    first_meta = body["selectionLists"][0]["items"][0]["meta"]
    second_meta = body["selectionLists"][0]["items"][1]["meta"]

    assert first_meta["practitionerRef"] == "Practitioner/prac-card-1"
    assert first_meta["isPreferredPractitioner"] is True

    assert second_meta["practitionerRef"] == "Practitioner/prac-card-2"
    assert second_meta["isPreferredPractitioner"] is False


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
    
    
def test_chat_reset_clears_session_and_logs_drop_event(client, db_session) -> None:
    client.post(
        "/chat/direct/start",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "action": "START_DIRECT_SCHEDULING",
        },
    )

    client.post(
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

    response = client.post(
        "/chat/reset",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "action": "RESET_FLOW",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["userMessage"] == "Returned to the main menu. Choose how you would like to continue."
    assert body["correlationId"] == "corr-chat-001"

    session = (
        db_session.query(AssistantSession)
        .filter(
            AssistantSession.tenant_id == "demo",
            AssistantSession.client_session_id == "patient-session-001",
        )
        .first()
    )

    assert session is not None
    assert session.current_state == "NEW"
    assert session.flow_mode is None
    assert session.selected_specialty_id is None
    assert session.selected_doctor_id is None
    assert session.selected_slot_id is None
    assert session.selected_slot_label is None
    assert session.selected_slot_start_utc is None
    assert session.selected_date is None
    assert session.last_input_summary is None
    assert session.renewal_item_id is None
    assert session.renewal_item_label is None
    assert session.renewal_patient_key_hash is None
    assert session.renewal_patient_ref is None
    assert session.continuity_checked is False
    assert session.continuity_patient_ref is None
    assert session.continuity_preferred_practitioner_ref is None
    assert session.continuity_preferred_practitioner_display is None
    assert session.continuity_is_returning is False

    dropped_event = (
        db_session.query(Event)
        .filter(
            Event.tenant_id == "demo",
            Event.session_id == "patient-session-001",
            Event.event_type == "SESSION_DROPPED",
        )
        .order_by(Event.ts_utc.desc())
        .first()
    )

    assert dropped_event is not None
    assert dropped_event.reason_code == "OK"

    payload = json.loads(dropped_event.payload_json)
    assert payload["component"] == "assistant-api"
    assert "returned to the main menu" in payload["safeSummary"].lower()
    assert payload["previousState"] == "AWAITING_CONTINUITY_IDENTITY"
    assert payload["previousFlowMode"] == "direct"
    
    
    
class RecordingClarificationNlpService:
    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.call_count = 0

    def classify(self, message_text: str):
        self.inputs.append(message_text)
        self.call_count += 1

        # Keep the session in clarification mode for the first two turns:
        # 1) original ambiguous complaint
        # 2) first clarification detail still ambiguous
        # Then let the third turn resolve.
        if self.call_count in (1, 2):
            return FakeAmbiguousPrediction()

        return FakePrediction()
    

def test_chat_message_persists_nlp_preprocessed_event_with_safe_trace_fields(
    client,
    db_session,
) -> None:
    client.app.state.nlp_service = FakeAmbiguousNlpService()

    response = client.post(
        "/chat/message",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "I have a stomach ache",
        },
    )

    assert response.status_code == 200

    event = (
        db_session.query(Event)
        .filter(Event.event_type == "NLP_PREPROCESSED")
        .order_by(Event.ts_utc.desc())
        .first()
    )

    assert event is not None

    payload = json.loads(event.payload_json)
    assert payload["component"] == "nlp"
    assert payload["classifierInputSummary"] == "I have a stomach ache"
    assert payload["cleanedInputSummary"] == "i have a stomach ache"
    assert payload["normalizedInputSummary"] == "i have a stomach ache"
    assert payload["usedMergedClarificationInput"] is False
    assert "preprocessingActions" in payload

def test_chat_message_accumulates_multiple_clarification_followups(
    client,
    db_session,
) -> None:
    fake_service = RecordingClarificationNlpService()
    client.app.state.nlp_service = fake_service

    first = client.post(
        "/chat/message",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "I have a stomach ache",
        },
    )
    assert first.status_code == 200
    assert first.json()["needsClarification"] is True

    second = client.post(
        "/chat/message",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "when i eat my stomach hurts me",
        },
    )
    assert second.status_code == 200
    assert second.json()["needsClarification"] is True

    third = client.post(
        "/chat/message",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "it goes away after 5 hours",
        },
    )
    assert third.status_code == 200

    assert len(fake_service.inputs) == 3

    assert fake_service.inputs[0] == "I have a stomach ache"

    assert "Original complaint:" in fake_service.inputs[1]
    assert "Clarification details:" in fake_service.inputs[1]
    assert "I have a stomach ache" in fake_service.inputs[1]
    assert "when i eat my stomach hurts me" in fake_service.inputs[1]

    assert "Original complaint:" in fake_service.inputs[2]
    assert "Clarification details:" in fake_service.inputs[2]
    assert "I have a stomach ache" in fake_service.inputs[2]
    assert "when i eat my stomach hurts me" in fake_service.inputs[2]
    assert "it goes away after 5 hours" in fake_service.inputs[2]

    session = (
        db_session.query(AssistantSession)
        .filter(AssistantSession.client_session_id == "patient-session-001")
        .first()
    )
    assert session is not None
    assert session.original_complaint_text == "I have a stomach ache"
    assert session.clarification_detail_text is not None
    assert "when i eat my stomach hurts me" in session.clarification_detail_text
    assert "it goes away after 5 hours" in session.clarification_detail_text
    assert session.merged_classification_text is not None
    assert "Clarification details:" in session.merged_classification_text
    
def test_chat_message_returns_single_clarification_helper_and_specialty_choices(client) -> None:
    client.app.state.nlp_service = FakeAmbiguousNlpService()

    response = client.post(
        "/chat/message",
        headers=hospital_headers(),
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "I have a stomach ache",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["needsClarification"] is True
    assert body["quickReplies"] is not None
    assert len(body["quickReplies"]) == 1
    assert body["quickReplies"][0]["label"] == "I will give more details"
    assert body["quickReplies"][0]["action"] == "PROMPT_FOR_TEXT"

    assert body["selectionLists"] is not None
    assert body["selectionLists"][0]["type"] == "specialty"
    assert len(body["selectionLists"][0]["items"]) >= 1