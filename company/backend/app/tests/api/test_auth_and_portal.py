from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.models import Event

def test_login_with_tenant_and_email_success(client) -> None:
    response = client.post(
        "/auth/login",
        json={
            "tenantId": "demo",
            "email": "admin@mvp.local",
            "password": "Admin123!",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert "accessToken" in body
    assert body["tenantId"] == "demo"
    assert body["user"]["email"] == "admin@mvp.local"
    assert body["user"]["role"] == "tenant_admin"


def test_login_invalid_password_returns_401(client) -> None:
    response = client.post(
        "/auth/login",
        json={
            "tenantId": "demo",
            "email": "admin@mvp.local",
            "password": "WrongPassword",
        },
    )

    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Invalid credentials."
    assert body["reasonCode"] == "INVALID_CREDENTIALS"


def test_login_inactive_user_returns_403(client) -> None:
    response = client.post(
        "/auth/login",
        json={
            "tenantId": "demo",
            "email": "inactive@mvp.local",
            "password": "Admin123!",
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["reasonCode"] == "INACTIVE_USER"


def test_portal_me_requires_token(client) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 401
    body = response.json()
    assert body["reasonCode"] == "MISSING_TOKEN"


def test_portal_me_success_for_tenant_admin(client, tenant_admin_token) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenantId"] == "demo"
    assert body["role"] == "tenant_admin"


def test_tenant_admin_cannot_cross_tenant_scope(client, tenant_admin_token) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "platform",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["reasonCode"] == "TENANT_SCOPE_VIOLATION"


def test_company_admin_can_use_different_request_tenant(client, company_admin_token) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "Authorization": f"Bearer {company_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenantId"] == "platform"
    assert body["role"] == "company_admin"
    
def test_portal_trace_returns_nlp_preprocessing_details(client, tenant_admin_token) -> None:
    class FakeCandidate:
        def __init__(self, specialty_id: str, confidence: float) -> None:
            self.specialty_id = specialty_id
            self.confidence = confidence

    class FakeQuickReply:
        def __init__(self, label: str, value: str, action: str | None = None) -> None:
            self.label = label
            self.value = value
            self.action = action

    class FakeAmbiguousPrediction:
        def __init__(self) -> None:
            self.primary_specialty_id = None
            self.top_candidates = [
                FakeCandidate("gastroenterology", 0.32),
                FakeCandidate("general_practice", 0.16),
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
        min_confidence = 0.70
        ambiguity_delta = 0.10

        def classify(self, message_text: str):
            return FakeAmbiguousPrediction()

    client.app.state.nlp_service = FakeAmbiguousNlpService()

    chat_response = client.post(
        "/chat/message",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "patient-session-001",
            "X-Correlation-Id": "corr-chat-001",
        },
        json={
            "tenantId": "demo",
            "clientSessionId": "patient-session-001",
            "messageText": "I have a stomach ache",
        },
    )
    assert chat_response.status_code == 200

    trace_response = client.get(
        "/portal/traces/by-session/patient-session-001",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert trace_response.status_code == 200

    rows = trace_response.json()

    preprocessed_row = next(item for item in rows if item["eventType"] == "NLP_PREPROCESSED")
    classified_row = next(item for item in rows if item["eventType"] == "NLP_CLASSIFIED")
    clarification_row = next(item for item in rows if item["eventType"] == "CLARIFICATION_REQUESTED")

    assert preprocessed_row["details"]["Classifier input summary"] == "I have a stomach ache"
    assert preprocessed_row["details"]["Cleaned input summary"] == "i have a stomach ache"
    assert preprocessed_row["details"]["Normalized input summary"] == "i have a stomach ache"
    assert preprocessed_row["details"]["Used merged clarification input"] == "No"
    assert preprocessed_row["details"]["Model version"] == "test-1.0"
    assert preprocessed_row["details"]["Preprocessing actions"] == "basic_cleanup"

    assert classified_row["safeSummary"].startswith("Ambiguous specialty prediction")
    assert classified_row["details"]["Top confidence"] == "0.32"
    assert classified_row["details"]["Second confidence"] == "0.16"
    assert classified_row["details"]["Confidence gap"] == "0.16"
    assert classified_row["details"]["Threshold min confidence"] == "0.7"
    assert classified_row["details"]["Threshold ambiguity delta"] == "0.1"
    assert classified_row["details"]["Ambiguity decision"] == "below_min_confidence"

    assert clarification_row["details"]["Clarification key"] == "free-text-clarification-only"
    assert clarification_row["details"]["Ambiguity decision"] == "below_min_confidence"
    
    
def test_portal_tenants_list_and_detail_for_company_admin(client, company_admin_token) -> None:
    tenants_response = client.get(
        "/portal/tenants",
        headers={
            "Authorization": f"Bearer {company_admin_token}",
            "X-Tenant-Id": "platform",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert tenants_response.status_code == 200
    tenants = tenants_response.json()
    tenant_ids = {item["tenantId"] for item in tenants}
    assert "platform" in tenant_ids
    assert "demo" in tenant_ids

    detail_response = client.get(
        "/portal/tenants/demo",
        headers={
            "Authorization": f"Bearer {company_admin_token}",
            "X-Tenant-Id": "platform",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["tenantId"] == "demo"
    assert body["name"] == "Demo Hospital Tenant"
    assert "allowedOrigins" in body
    assert "featureFlags" in body
    assert body["featureFlags"]["nlpEnabled"] is True


def test_portal_tenants_are_scoped_for_tenant_admin(client, tenant_admin_token) -> None:
    response = client.get(
        "/portal/tenants",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["tenantId"] == "demo"


def test_portal_audit_returns_scoped_event_rows(client, tenant_admin_token, db_session) -> None:
    db_session.add_all(
        [
            Event(
                id="evt-audit-1",
                tenant_id="demo",
                session_id="patient-session-001",
                correlation_id="corr-audit-1",
                actor_type="system",
                event_type="BOOKING_CONFIRMED",
                outcome="SUCCESS",
                reason_code="OK",
                payload_json=json.dumps(
                    {
                        "component": "scheduling",
                        "safeSummary": "Appointment confirmed successfully.",
                    }
                ),
                ts_utc=datetime(2026, 4, 22, 10, 0, 0, tzinfo=timezone.utc),
            ),
            Event(
                id="evt-audit-2",
                tenant_id="platform",
                session_id="portal-session-001",
                correlation_id="corr-audit-2",
                actor_type="system",
                event_type="SESSION_DROPPED",
                outcome="INFO",
                reason_code="OK",
                payload_json=json.dumps(
                    {
                        "component": "assistant-api",
                        "safeSummary": "User dropped the session.",
                    }
                ),
                ts_utc=datetime(2026, 4, 22, 10, 5, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/portal/audit?from=2026-04-22&to=2026-04-22",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 1
    assert body["items"][0]["eventType"] == "BOOKING_CONFIRMED"
    assert body["items"][0]["safeSummary"] == "Appointment confirmed successfully."
    assert body["items"][0]["correlationId"] == "corr-audit-1"


def test_portal_nlp_stats_returns_live_status(client, tenant_admin_token) -> None:
    client.app.state.nlp_service = None
    client.app.state.nlp_status = {
        "available": True,
        "modelName": "distilbert-specialty",
        "modelVersion": "1.0.0",
        "labelsCount": 9,
        "thresholds": {
            "minConfidence": 0.7,
            "ambiguityDelta": 0.1,
        },
        "loadedAt": "2026-04-22T00:00:00Z",
    }

    response = client.get(
        "/portal/nlp/stats",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["loadedLabels"] == 9
    assert body["modelName"] == "distilbert-specialty"
    assert body["modelVersion"] == "1.0.0"
    assert body["thresholds"]["minConfidence"] == 0.7
    assert body["thresholds"]["ambiguityDelta"] == 0.1


def test_portal_nlp_recent_returns_recent_classifications(client, tenant_admin_token, db_session) -> None:
    db_session.add_all(
        [
            Event(
                id="evt-nlp-pre-1",
                tenant_id="demo",
                session_id="patient-session-001",
                correlation_id="corr-nlp-1",
                actor_type="system",
                event_type="NLP_PREPROCESSED",
                outcome="INFO",
                reason_code="OK",
                payload_json=json.dumps(
                    {
                        "component": "nlp",
                        "normalizedInputSummary": "i have a stomach ache",
                        "safeSummary": "Prepared complaint text for specialty classification.",
                    }
                ),
                ts_utc=datetime(2026, 4, 22, 11, 0, 0, tzinfo=timezone.utc),
            ),
            Event(
                id="evt-nlp-class-1",
                tenant_id="demo",
                session_id="patient-session-001",
                correlation_id="corr-nlp-1",
                actor_type="system",
                event_type="NLP_CLASSIFIED",
                outcome="SUCCESS",
                reason_code="NEEDS_CLARIFICATION",
                payload_json=json.dumps(
                    {
                        "component": "nlp",
                        "safeSummary": "Ambiguous specialty prediction between Gastroenterology and General Practice.",
                        "topCandidates": [
                            {"id": "gastroenterology", "confidence": 0.3205},
                            {"id": "general_practice", "confidence": 0.1626},
                        ],
                        "ambiguityDecision": "below_min_confidence",
                    }
                ),
                ts_utc=datetime(2026, 4, 22, 11, 0, 1, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/portal/nlp/recent?limit=5",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body) >= 1
    assert body[0]["predictedLabel"] == "Gastroenterology"
    assert body[0]["confidence"] == 0.3205
    assert body[0]["ambiguity"] is True
    assert body[0]["inputSummary"] == "i have a stomach ache"