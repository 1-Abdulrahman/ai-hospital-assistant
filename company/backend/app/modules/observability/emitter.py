import json
import uuid

from sqlalchemy.orm import Session

from app.core.correlation import get_correlation_id
from app.db.models import Event


def emit_event(
    *,
    db: Session,
    tenant_id: str,
    session_id: str,
    actor_type: str,
    event_type: str,
    outcome: str,
    reason_code: str | None = None,
    payload: dict | None = None,
) -> None:
    """Persist a single observability event with the active correlation ID.

    The payload is stored as JSON text only when present so the database row
    stays compact for events that do not need extra structured context.
    """
    safe_payload_json = None
    if payload:
        # Keep the raw payload in a JSON column-compatible string; non-ASCII
        # characters are preserved for diagnostics and UI display.
        safe_payload_json = json.dumps(payload, ensure_ascii=False)

    # Capture the current request/session correlation so downstream queries can
    # stitch related events together without the caller having to pass it in.
    db.add(
        Event(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            session_id=session_id,
            correlation_id=get_correlation_id(),
            actor_type=actor_type,
            event_type=event_type,
            outcome=outcome,
            reason_code=reason_code,
            payload_json=safe_payload_json,
        )
    )