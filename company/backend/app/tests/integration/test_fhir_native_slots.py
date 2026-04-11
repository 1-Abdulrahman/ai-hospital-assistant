from __future__ import annotations

import pytest

from app.modules.scheduling.service import list_available_slots


@pytest.mark.asyncio
async def test_backend_slots_endpoint_logic_reads_seeded_hapi_slots(db_session, live_fhir_client) -> None:
    result = await list_available_slots(
        db=db_session,
        header_tenant_id="demo",
        session_id="patient-session-integration-1",
        body_tenant_id="demo",
        specialty="cardiology",
        fhir_client=live_fhir_client,
    )

    assert result["ok"] is True
    assert result["reasonCode"] in {"OK", "NO_SLOTS_AVAILABLE"}

    if result["items"]:
        first = result["items"][0]
        assert first.slotId.startswith("slot-sched-cardiology-")
        assert first.scheduleRef.startswith("Schedule/sched-cardiology-")
        assert first.status == "free"