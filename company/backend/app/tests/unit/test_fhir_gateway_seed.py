from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path

import pytest

import app.modules.fhir_gateway.seed as seed


def test_load_provider_seed_items_reads_all_specialties(tmp_path: Path, monkeypatch) -> None:
    providers_file = tmp_path / "providers_static.json"
    providers_file.write_text(
        """
        {
          "cardiology": [
            {
              "practitionerRef": "Practitioner/prac-card-1",
              "practitionerDisplay": "Dr. Lina Alharbi"
            }
          ],
          "general_practice": [
            {
              "practitionerRef": "Practitioner/prac-gp-1",
              "practitionerDisplay": "Dr. Mona Alqahtani"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(seed, "PROVIDERS_PATH", providers_file)

    items = seed._load_provider_seed_items()

    assert len(items) == 2
    assert items[0].specialty == "cardiology"
    assert items[0].practitioner_id == "prac-card-1"
    assert items[1].specialty == "general_practice"
    assert items[1].practitioner_id == "prac-gp-1"


def test_schedule_id_generation_sanitizes_invalid_fhir_id_characters() -> None:
    item = seed.ProviderSeedItem(
        specialty="general_practice",
        practitioner_id="prac-gp-1",
        practitioner_ref="Practitioner/prac-gp-1",
        practitioner_display="Dr. Mona Alqahtani",
    )

    assert seed._schedule_id_for(item) == "sched-general-practice-prac-gp-1"


def test_slot_id_generation_sanitizes_invalid_fhir_id_characters() -> None:
    schedule_id = "sched-general-practice-prac-gp-1"
    start_dt = datetime(2026, 4, 8, 9, 0, tzinfo=UTC)

    assert seed._slot_id_for(schedule_id, start_dt) == (
        "slot-sched-general-practice-prac-gp-1-20260408T0900"
    )


def test_build_schedule_resource_contains_actor_specialty_and_tenant_identifier() -> None:
    item = seed.ProviderSeedItem(
        specialty="cardiology",
        practitioner_id="prac-card-1",
        practitioner_ref="Practitioner/prac-card-1",
        practitioner_display="Dr. Lina Alharbi",
    )

    resource = seed._build_schedule_resource(
        item=item,
        schedule_id="sched-cardiology-prac-card-1",
        horizon_start_utc="2026-04-08T00:00:00Z",
        horizon_end_utc="2026-04-21T23:59:00Z",
    )

    assert resource["resourceType"] == "Schedule"
    assert resource["id"] == "sched-cardiology-prac-card-1"
    assert resource["identifier"][0]["system"] == "urn:ai-hospital-assistant:tenant-id"
    assert resource["identifier"][0]["value"] == "demo"
    assert resource["actor"][0]["reference"] == "Practitioner/prac-card-1"
    assert resource["actor"][0]["display"] == "Dr. Lina Alharbi"
    assert resource["specialty"][0]["coding"][0]["code"] == "cardiology"
    assert resource["planningHorizon"]["start"] == "2026-04-08T00:00:00Z"


def test_build_slot_resource_contains_schedule_reference_and_status() -> None:
    item = seed.ProviderSeedItem(
        specialty="cardiology",
        practitioner_id="prac-card-1",
        practitioner_ref="Practitioner/prac-card-1",
        practitioner_display="Dr. Lina Alharbi",
    )

    resource = seed._build_slot_resource(
        item=item,
        schedule_id="sched-cardiology-prac-card-1",
        slot_id="slot-sched-cardiology-prac-card-1-20260408T0900",
        start_utc="2026-04-08T09:00:00Z",
        end_utc="2026-04-08T09:30:00Z",
        status="free",
        comment="Available for booking",
    )

    assert resource["resourceType"] == "Slot"
    assert resource["id"] == "slot-sched-cardiology-prac-card-1-20260408T0900"
    assert resource["schedule"]["reference"] == "Schedule/sched-cardiology-prac-card-1"
    assert resource["status"] == "free"
    assert resource["start"] == "2026-04-08T09:00:00Z"
    assert resource["end"] == "2026-04-08T09:30:00Z"
    assert resource["comment"] == "Available for booking"


@pytest.mark.asyncio
async def test_seed_preserves_existing_slot_status_when_rerun(monkeypatch) -> None:
    item = seed.ProviderSeedItem(
        specialty="cardiology",
        practitioner_id="prac-card-1",
        practitioner_ref="Practitioner/prac-card-1",
        practitioner_display="Dr. Lina Alharbi",
    )

    monkeypatch.setattr(seed, "SEED_DAYS_AHEAD", 1)
    monkeypatch.setattr(
        seed,
        "CLINIC_WINDOWS",
        ((time(hour=9, minute=0), time(hour=9, minute=30)),),
    )

    async def fake_check_fhir_ready(client):
        return None

    async def fake_get_if_exists(client, resource_type: str, resource_id: str):
        if resource_type == "Slot":
            return {
                "resourceType": "Slot",
                "id": resource_id,
                "status": "busy",
                "comment": "Already booked",
            }
        return None

    captured_slot_resources: list[dict] = []

    async def fake_put_resource(client, resource_type: str, resource_id: str, resource: dict):
        if resource_type == "Slot":
            captured_slot_resources.append(resource)
            return "updated"
        return "created"

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(seed, "_load_provider_seed_items", lambda: [item])
    monkeypatch.setattr(seed, "_check_fhir_ready", fake_check_fhir_ready)
    monkeypatch.setattr(seed, "_get_if_exists", fake_get_if_exists)
    monkeypatch.setattr(seed, "_put_resource", fake_put_resource)
    monkeypatch.setattr(seed.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(seed.settings, "fhir_base_url", "http://localhost:8080/fhir")

    await seed.run_async()

    assert len(captured_slot_resources) == 1
    assert captured_slot_resources[0]["status"] == "busy"
    assert captured_slot_resources[0]["comment"] == "Already booked"