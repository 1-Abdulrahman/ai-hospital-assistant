from __future__ import annotations

import pytest

from app.modules.scheduling.idempotency import (
    get_replayed_result_or_raise,
    save_terminal_result,
    stable_request_hash,
)
from app.modules.scheduling.reason_codes import (
    IDEMPOTENCY_KEY_REUSE_MISMATCH,
    SchedulingError,
)


def test_stable_request_hash_is_order_independent() -> None:
    a = {
        "tenantId": "demo",
        "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        "specialty": "cardiology",
    }
    b = {
        "specialty": "cardiology",
        "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        "tenantId": "demo",
    }

    assert stable_request_hash(a) == stable_request_hash(b)


def test_replayed_result_returns_saved_payload(db_session) -> None:
    request_hash = stable_request_hash(
        {
            "tenantId": "demo",
            "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
        }
    )
    result = {
        "ok": True,
        "reasonCode": "OK",
        "appointmentId": "appt-1",
        "appointmentRef": "Appointment/appt-1",
        "specialty": "cardiology",
        "slot": {
            "slotId": "slot-sched-cardiology-prac-card-1-20260408T0900",
            "slotRef": "Slot/slot-sched-cardiology-prac-card-1-20260408T0900",
            "scheduleRef": "Schedule/sched-cardiology-prac-card-1",
            "practitionerRef": "Practitioner/prac-card-1",
            "practitionerDisplay": "Dr. Lina Alharbi",
            "specialty": "cardiology",
            "startUtc": "2026-04-08T09:00:00Z",
            "endUtc": "2026-04-08T09:30:00Z",
            "status": "busy",
        },
        "message": "Appointment booked successfully.",
    }

    save_terminal_result(
        db=db_session,
        idempotency_key="idem-1",
        tenant_id="demo",
        session_id="session-1",
        request_hash=request_hash,
        result=result,
    )
    db_session.commit()

    replayed = get_replayed_result_or_raise(
        db=db_session,
        idempotency_key="idem-1",
        tenant_id="demo",
        session_id="session-1",
        request_hash=request_hash,
    )

    assert replayed == result


def test_reused_idempotency_key_with_different_payload_raises(db_session) -> None:
    save_terminal_result(
        db=db_session,
        idempotency_key="idem-1",
        tenant_id="demo",
        session_id="session-1",
        request_hash=stable_request_hash({"slotId": "slot-1"}),
        result={"ok": True, "reasonCode": "OK"},
    )
    db_session.commit()

    with pytest.raises(SchedulingError) as exc:
        get_replayed_result_or_raise(
            db=db_session,
            idempotency_key="idem-1",
            tenant_id="demo",
            session_id="session-1",
            request_hash=stable_request_hash({"slotId": "slot-2"}),
        )

    assert exc.value.reason_code == IDEMPOTENCY_KEY_REUSE_MISMATCH