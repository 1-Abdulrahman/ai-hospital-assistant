from __future__ import annotations

import httpx


def test_health_returns_status_version_and_time(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "OK"
    assert "version" in body
    assert "time" in body


def test_health_echoes_correlation_id(client) -> None:
    response = client.get(
        "/health",
        headers={"X-Correlation-Id": "test-correlation-id-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "test-correlation-id-123"


def test_validation_error_is_safe_and_minimal(client) -> None:
    # Missing password and wrong login shape
    response = client.post("/auth/login", json={})

    assert response.status_code == 422
    body = response.json()

    assert body["message"] == "Request validation failed."
    assert body["reasonCode"] == "VALIDATION_ERROR"
    assert "correlationId" in body
    assert "traceback" not in str(body).lower()


def test_fhir_status_returns_degraded_when_unreachable(client, monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            raise httpx.ConnectError("cannot connect")

    monkeypatch.setattr("app.api.routes.integrations.httpx.AsyncClient", FakeAsyncClient)

    response = client.get("/integrations/fhir/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DEGRADED"
    assert body["reasonCode"] == "FHIR_UNREACHABLE"