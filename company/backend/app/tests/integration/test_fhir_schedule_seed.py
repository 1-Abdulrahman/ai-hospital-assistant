from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_seed_creates_schedule_and_slots_for_cardiology_practitioner(live_fhir_client) -> None:
    schedule = await live_fhir_client.get_schedule_or_raise("Schedule/sched-cardiology-prac-card-1")

    assert schedule.scheduleId == "sched-cardiology-prac-card-1"
    assert schedule.practitionerRef == "Practitioner/prac-card-1"

    slots = await live_fhir_client.search_slots(
        schedule_ref=schedule.scheduleRef,
        status="free",
    )

    assert len(slots) > 0
    assert all(item.scheduleRef == schedule.scheduleRef for item in slots)