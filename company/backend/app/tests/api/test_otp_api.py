from __future__ import annotations

from app.modules.otp import service


class FakeFhirClient:
    async def find_patient_by_identifier(
        self,
        *,
        patient_key_hash: str,
        tenant_id: str | None = None,
    ):
        return None

    async def save_patient_email_if_missing(
        self,
        *,
        tenant_id: str,
        patient_key_hash: str,
        email: str,
    ):
        return None

def otp_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": "demo",
        "X-Session-Id": "patient-session-1",
    }


def test_otp_request_requires_headers(client) -> None:
    response = client.post(
        "/otp/request",
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["reasonCode"] == "INVALID_REQUEST"


def test_otp_request_success(client, monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "send_otp_email",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        service,
        "FhirClient",
        lambda: FakeFhirClient(),
    )

    response = client.post(
        "/otp/request",
        headers=otp_headers(),
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "expiresIn" in body


def test_otp_verify_success(client, monkeypatch) -> None:
    captured = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        captured["otp"] = otp

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)
    monkeypatch.setattr(
        service,
        "FhirClient",
        lambda: FakeFhirClient(),
    )

    request_response = client.post(
        "/otp/request",
        headers=otp_headers(),
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
        },
    )
    assert request_response.status_code == 200

    verify_response = client.post(
        "/otp/verify",
        headers=otp_headers(),
        json={
            "tenantId": "demo",
            "nationalId": "2123456788",
            "email": "patient@example.com",
            "otp": captured["otp"],
        },
    )

    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["ok"] is True
    assert body["verified"] is True