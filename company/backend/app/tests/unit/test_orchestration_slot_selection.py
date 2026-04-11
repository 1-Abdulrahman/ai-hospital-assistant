from __future__ import annotations

from dataclasses import dataclass

from app.modules.orchestration.service import _slot_selection_list


@dataclass
class FakeSlotDTO:
    slot_id: str
    slot_ref: str
    practitioner_ref: str
    practitioner_display: str
    specialty: str
    start_utc: str
    end_utc: str
    status: str


def test_slot_selection_list_accepts_slot_dto_objects() -> None:
    items = [
        FakeSlotDTO(
            slot_id="slot-1",
            slot_ref="Slot/slot-1",
            practitioner_ref="Practitioner/prac-1",
            practitioner_display="Dr. Lina Alharbi",
            specialty="cardiology",
            start_utc="2026-04-12T09:00:00Z",
            end_utc="2026-04-12T09:30:00Z",
            status="free",
        )
    ]

    result = _slot_selection_list(items=items)

    assert isinstance(result, list)
    assert result[0]["type"] == "slot"
    assert len(result[0]["items"]) == 1

    first_item = result[0]["items"][0]
    assert first_item["id"] == "slot-1"
    assert first_item["label"] == "Dr. Lina Alharbi • 2026-04-12 09:00:00 UTC"
    assert first_item["description"] == "Cardiology appointment slot."
    assert first_item["meta"]["isoDate"] == "2026-04-12T09:00:00Z"
    assert first_item["meta"]["timezone"] == "UTC"