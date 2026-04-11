from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.models import IdempotencyKey
from app.modules.scheduling.reason_codes import (
    IDEMPOTENCY_KEY_REUSE_MISMATCH,
    SchedulingError,
)


def stable_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_jsonable_dict(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = jsonable_encoder(payload)
    if not isinstance(encoded, dict):
        raise TypeError("Expected idempotency payload to encode to a dictionary.")
    return encoded


def get_replayed_result_or_raise(
    *,
    db: Session,
    idempotency_key: str,
    tenant_id: str,
    session_id: str,
    request_hash: str,
) -> dict[str, Any] | None:
    record = db.get(IdempotencyKey, idempotency_key)
    if record is None:
        return None

    if (
        record.tenant_id != tenant_id
        or record.session_id != session_id
        or record.request_hash != request_hash
    ):
        raise SchedulingError(
            reason_code=IDEMPOTENCY_KEY_REUSE_MISMATCH,
            details="Stored request hash does not match the current request.",
        )

    loaded = json.loads(record.result_json)
    if not isinstance(loaded, dict):
        raise TypeError("Stored idempotency result must decode to a dictionary.")
    return loaded


def save_terminal_result(
    *,
    db: Session,
    idempotency_key: str,
    tenant_id: str,
    session_id: str,
    request_hash: str,
    result: dict[str, Any],
) -> None:
    normalized_result = to_jsonable_dict(result)
    serialized = json.dumps(normalized_result, sort_keys=True, ensure_ascii=False)

    record = db.get(IdempotencyKey, idempotency_key)
    if record is None:
        db.add(
            IdempotencyKey(
                key=idempotency_key,
                tenant_id=tenant_id,
                session_id=session_id,
                request_hash=request_hash,
                result_json=serialized,
            )
        )
        return

    record.tenant_id = tenant_id
    record.session_id = session_id
    record.request_hash = request_hash
    record.result_json = serialized