from __future__ import annotations

import httpx
import pytest

from app.modules.fhir_gateway.client import FhirClient
from app.modules.fhir_gateway.reason_codes import (
    APPOINTMENT_CONFLICT,
    FHIR_TIMEOUT,
    SLOT_NO_LONGER_AVAILABLE,
    FhirGatewayError,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def install_router(monkeypatch, router):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def request(self, method, url, params=None, json=None, headers=None):
            return router(
                method=method,
                url=url,
                params=params,
                json_payload=json,
                headers=headers,
            )

    monkeypatch.setattr("app.modules.fhir_gateway.client.httpx.AsyncClient", FakeAsyncClient)


@pytest.mark.asyncio
async def test_get_capability_statement_retries_once_on_503(monkeypatch) -> None:
    calls = {"count": 0}

    def router(*, method, url, params=None, json_payload=None, headers=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse(503, {"resourceType": "OperationOutcome"})
        return FakeResponse(200, {"resourceType": "CapabilityStatement"})

    install_router(monkeypatch, router)

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
async def test_search_schedules_returns_safe_schedule_dtos(monkeypatch) -> None:
    def router(*, method, url, params=None, json_payload=None, headers=None):
        assert method == "GET"
        assert url.endswith("/Schedule")
        return FakeResponse(
            200,
            {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Schedule",
                            "id": "sched-cardiology-prac-card-1",
                            "active": True,
                            "identifier": [
                                {
                                    "system": "urn:ai-hospital-assistant:tenant-id",
                                    "value": "demo",
                                }
                            ],
                            "specialty": [
                                {
                                    "coding": [
                                        {
                                            "system": "urn:ai-hospital-assistant:specialty",
                                            "code": "cardiology",
                                            "display": "Cardiology",
                                        }
                                    ],
                                    "text": "Cardiology",
                                }
                            ],
                            "actor": [
                                {
                                    "reference": "Practitioner/prac-card-1",
                                    "display": "Dr. Lina Alharbi",
                                }
                            ],
                            "planningHorizon": {
                                "start": "2026-04-08T00:00:00Z",
                                "end": "2026-04-21T23:59:00Z",
                            },
                        }
                    }
                ],
            },
        )

    install_router(monkeypatch, router)

    items = await FhirClient().search_schedules(
        tenant_id="demo",
        specialty="cardiology",
        active=True,
    )

    assert len(items) == 1
    assert items[0].scheduleId == "sched-cardiology-prac-card-1"
    assert items[0].scheduleRef == "Schedule/sched-cardiology-prac-card-1"
    assert items[0].practitionerRef == "Practitioner/prac-card-1"
    assert items[0].practitionerDisplay == "Dr. Lina Alharbi"
    assert items[0].specialty == "cardiology"
    assert items[0].tenantId == "demo"


@pytest.mark.asyncio
async def test_search_slots_returns_safe_slot_dtos(monkeypatch) -> None:
    def router(*, method, url, params=None, json_payload=None, headers=None):
        if method == "GET" and url.endswith("/Schedule/sched-cardiology-prac-card-1"):
            return FakeResponse(
                200,
                {
                    "resourceType": "Schedule",
                    "id": "sched-cardiology-prac-card-1",
                    "identifier": [
                        {
                            "system": "urn:ai-hospital-assistant:tenant-id",
                            "value": "demo",
                        }
                    ],
                    "specialty": [
                        {
                            "coding": [
                                {
                                    "system": "urn:ai-hospital-assistant:specialty",
                                    "code": "cardiology",
                                    "display": "Cardiology",
                                }
                            ],
                            "text": "Cardiology",
                        }
                    ],
                    "actor": [
                        {
                            "reference": "Practitioner/prac-card-1",
                            "display": "Dr. Lina Alharbi",
                        }
                    ],
                    "planningHorizon": {
                        "start": "2026-04-08T00:00:00Z",
                        "end": "2026-04-21T23:59:00Z",
                    },
                },
            )

        if method == "GET" and url.endswith("/Slot"):
            return FakeResponse(
                200,
                {
                    "resourceType": "Bundle",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "Slot",
                                "id": "slot-sched-cardiology-prac-card-1-20260408T0900",
                                "schedule": {
                                    "reference": "Schedule/sched-cardiology-prac-card-1"
                                },
                                "status": "free",
                                "start": "2026-04-08T09:00:00Z",
                                "end": "2026-04-08T09:30:00Z",
                                "specialty": [
                                    {
                                        "coding": [
                                            {
                                                "code": "cardiology",
                                                "display": "Cardiology",
                                            }
                                        ],
                                        "text": "Cardiology",
                                    }
                                ],
                            }
                        }
                    ],
                },
            )

        raise AssertionError(f"Unexpected request: {method} {url}")

    install_router(monkeypatch, router)

    items = await FhirClient().search_slots(
        schedule_ref="Schedule/sched-cardiology-prac-card-1",
        status="free",
        start_from_utc="2026-04-08T00:00:00Z",
    )

    assert len(items) == 1
    assert items[0].slotId == "slot-sched-cardiology-prac-card-1-20260408T0900"
    assert items[0].slotRef == "Slot/slot-sched-cardiology-prac-card-1-20260408T0900"
    assert items[0].scheduleRef == "Schedule/sched-cardiology-prac-card-1"
    assert items[0].practitionerRef == "Practitioner/prac-card-1"
    assert items[0].practitionerDisplay == "Dr. Lina Alharbi"
    assert items[0].status == "free"


@pytest.mark.asyncio
async def test_get_slot_or_raise_maps_404_to_slot_no_longer_available(monkeypatch) -> None:
    def router(*, method, url, params=None, json_payload=None, headers=None):
        if method == "GET" and url.endswith("/Slot/slot-sched-cardiology-prac-card-1-20260408T0900"):
            return FakeResponse(
                404,
                {
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "details": {
                                "text": "Slot was not found.",
                            }
                        }
                    ],
                },
            )

        raise AssertionError(f"Unexpected request: {method} {url}")

    install_router(monkeypatch, router)

    with pytest.raises(FhirGatewayError) as exc:
        await FhirClient().get_slot_or_raise("slot-sched-cardiology-prac-card-1-20260408T0900")

    assert exc.value.reason_code == SLOT_NO_LONGER_AVAILABLE
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_slot_status_sets_busy_successfully(monkeypatch) -> None:
    def router(*, method, url, params=None, json_payload=None, headers=None):
        if method == "GET" and url.endswith("/Slot/slot-sched-cardiology-prac-card-1-20260408T0900"):
            return FakeResponse(
                200,
                {
                    "resourceType": "Slot",
                    "id": "slot-sched-cardiology-prac-card-1-20260408T0900",
                    "schedule": {
                        "reference": "Schedule/sched-cardiology-prac-card-1"
                    },
                    "status": "free",
                    "start": "2026-04-08T09:00:00Z",
                    "end": "2026-04-08T09:30:00Z",
                    "specialty": [
                        {
                            "coding": [
                                {"code": "cardiology", "display": "Cardiology"}
                            ],
                            "text": "Cardiology",
                        }
                    ],
                },
            )

        if method == "PUT" and url.endswith("/Slot/slot-sched-cardiology-prac-card-1-20260408T0900"):
            assert json_payload["status"] == "busy"
            return FakeResponse(
                200,
                {
                    "resourceType": "Slot",
                    "id": "slot-sched-cardiology-prac-card-1-20260408T0900",
                    "schedule": {
                        "reference": "Schedule/sched-cardiology-prac-card-1"
                    },
                    "status": "busy",
                    "start": "2026-04-08T09:00:00Z",
                    "end": "2026-04-08T09:30:00Z",
                    "specialty": [
                        {
                            "coding": [
                                {"code": "cardiology", "display": "Cardiology"}
                            ],
                            "text": "Cardiology",
                        }
                    ],
                },
            )

        if method == "GET" and url.endswith("/Schedule/sched-cardiology-prac-card-1"):
            return FakeResponse(
                200,
                {
                    "resourceType": "Schedule",
                    "id": "sched-cardiology-prac-card-1",
                    "identifier": [
                        {
                            "system": "urn:ai-hospital-assistant:tenant-id",
                            "value": "demo",
                        }
                    ],
                    "specialty": [
                        {
                            "coding": [
                                {
                                    "system": "urn:ai-hospital-assistant:specialty",
                                    "code": "cardiology",
                                    "display": "Cardiology",
                                }
                            ],
                            "text": "Cardiology",
                        }
                    ],
                    "actor": [
                        {
                            "reference": "Practitioner/prac-card-1",
                            "display": "Dr. Lina Alharbi",
                        }
                    ],
                    "planningHorizon": {
                        "start": "2026-04-08T00:00:00Z",
                        "end": "2026-04-21T23:59:00Z",
                    },
                },
            )

        raise AssertionError(f"Unexpected request: {method} {url}")

    install_router(monkeypatch, router)

    updated = await FhirClient().update_slot_status(
        slot_id="slot-sched-cardiology-prac-card-1-20260408T0900",
        new_status="busy",
        comment="Booked via Appointment/appt-1",
    )

    assert updated.slotId == "slot-sched-cardiology-prac-card-1-20260408T0900"
    assert updated.status == "busy"
    assert updated.scheduleRef == "Schedule/sched-cardiology-prac-card-1"


@pytest.mark.asyncio
async def test_create_appointment_maps_409_to_conflict(monkeypatch) -> None:
    def router(*, method, url, params=None, json_payload=None, headers=None):
        assert method == "POST"
        assert url.endswith("/Appointment")
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

    install_router(monkeypatch, router)

    with pytest.raises(FhirGatewayError) as exc:
        await FhirClient().create_appointment(
            tenant_id="demo",
            patient_ref="Patient/patient-123",
            practitioner_ref="Practitioner/prac-card-1",
            specialty_code="cardiology",
            specialty_display="Cardiology",
            start_utc="2026-04-08T09:00:00Z",
            end_utc="2026-04-08T09:30:00Z",
            slot_ref="Slot/slot-sched-cardiology-prac-card-1-20260408T0900",
        )

    assert exc.value.reason_code == APPOINTMENT_CONFLICT
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_search_appointments_includes_slot_refs(monkeypatch) -> None:
    def router(*, method, url, params=None, json_payload=None, headers=None):
        assert method == "GET"
        assert url.endswith("/Appointment")
        return FakeResponse(
            200,
            {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Appointment",
                            "id": "appt-1",
                            "status": "booked",
                            "start": "2026-04-08T09:00:00Z",
                            "end": "2026-04-08T09:30:00Z",
                            "identifier": [
                                {
                                    "system": "urn:ai-hospital-assistant:tenant-id",
                                    "value": "demo",
                                }
                            ],
                            "serviceType": [
                                {
                                    "coding": [
                                        {
                                            "system": "urn:ai-hospital-assistant:specialty",
                                            "code": "cardiology",
                                            "display": "Cardiology",
                                        }
                                    ],
                                    "text": "Cardiology",
                                }
                            ],
                            "slot": [
                                {
                                    "reference": "Slot/slot-sched-cardiology-prac-card-1-20260408T0900"
                                }
                            ],
                            "participant": [
                                {
                                    "actor": {
                                        "reference": "Patient/patient-1",
                                        "display": "Demo Patient",
                                    },
                                    "status": "accepted",
                                },
                                {
                                    "actor": {
                                        "reference": "Practitioner/prac-card-1",
                                        "display": "Dr. Lina Alharbi",
                                    },
                                    "status": "accepted",
                                },
                            ],
                        }
                    }
                ],
            },
        )

    install_router(monkeypatch, router)

    items = await FhirClient().search_appointments(
        practitioner_ref="Practitioner/prac-card-1",
        start_utc="2026-04-08T00:00:00Z",
        status="booked",
    )

    assert len(items) == 1
    assert items[0].appointmentId == "appt-1"
    assert items[0].slotRefs == ["Slot/slot-sched-cardiology-prac-card-1-20260408T0900"]