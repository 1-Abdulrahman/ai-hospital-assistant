from __future__ import annotations


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

    assert preprocessed_row["details"]["Classifier input"] == "I have a stomach ache"
    assert preprocessed_row["details"]["Cleaned input"] == "i have a stomach ache"
    assert preprocessed_row["details"]["Normalized input"] == "i have a stomach ache"
    assert preprocessed_row["details"]["Used merged clarification input"] == "No"