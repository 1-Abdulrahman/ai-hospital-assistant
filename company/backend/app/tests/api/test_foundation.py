from __future__ import annotations

import pytest


def test_fhir_status_returns_degraded_when_unreachable(client, monkeypatch) -> None:
    async def fake_get_status_payload(self) -> dict:
        return {
            "status": "DEGRADED",
            "fhirBaseUrl": "http://fhir:8080/fhir",
            "time": "2026-04-06T00:00:00Z",
            "reasonCode": "FHIR_UNAVAILABLE",
        }

    monkeypatch.setattr(
        "app.api.routes.integrations.FhirClient.get_status_payload",
        fake_get_status_payload,
    )

    response = client.get("/integrations/fhir/status")

    assert response.status_code == 200
    
    body = response.json()

    assert body["status"] == "DEGRADED"
    assert body["fhirBaseUrl"] == "http://fhir:8080/fhir"
    assert body["reasonCode"] == "FHIR_UNAVAILABLE"
    assert "correlationId" not in body or isinstance(body["correlationId"], str)
    assert "time" in body