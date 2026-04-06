from __future__ import annotations

import httpx
import pytest

from app.modules.fhir_gateway.client import FhirClient
from app.modules.fhir_gateway.reason_codes import (
    APPOINTMENT_CONFLICT,
    FHIR_TIMEOUT,
    FhirGatewayError,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_get_capability_statement_retries_once_on_503(monkeypatch) -> None:
    calls = {"count": 0}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def request(self, method, url, params=None, json=None, headers=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeResponse(503, {"resourceType": "OperationOutcome"})
            return FakeResponse(200, {"resourceType": "CapabilityStatement"})

    monkeypatch.setattr("app.modules.fhir_gateway.client.httpx.AsyncClient", FakeAsyncClient)

    payload = await FhirClient().get_capability_statement()

    assert calls["count"] == 2
    assert payload["resourceType"] == "CapabilityStatement"


@pytest.mark.asyncio
async def test_get_capability_statement_maps_timeout(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def request(self, method, url, params=None, json=None, headers=None):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.modules.fhir_gateway.client.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(FhirGatewayError) as exc:
        await FhirClient().get_capability_statement()

    assert exc.value.reason_code == FHIR_TIMEOUT
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_create_appointment_maps_409_to_conflict(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def request(self, method, url, params=None, json=None, headers=None):
            return FakeResponse(
                409,
                {
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "details": {
                                "text": "Appointment already exists in this time window.",
                            }
                        }
                    ],
                },
            )

    monkeypatch.setattr("app.modules.fhir_gateway.client.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(FhirGatewayError) as exc:
        await FhirClient().create_appointment(
            tenant_id="demo",
            patient_ref="Patient/patient-123",
            practitioner_ref="Practitioner/prac-1",
            specialty_code="cardiology",
            specialty_display="Cardiology",
            start_utc="2026-04-07T09:00:00Z",
            end_utc="2026-04-07T09:30:00Z",
        )

    assert exc.value.reason_code == APPOINTMENT_CONFLICT
    assert exc.value.status_code == 409