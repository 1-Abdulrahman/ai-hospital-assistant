"""Helpers for idempotent scheduling requests.

This module provides utilities to compute a stable request hash, normalize
payloads into JSON-serializable dictionaries, and persist/retrieve
idempotency results from the database via the `IdempotencyKey` model.

The intent is to allow safe retrying of requests: identical requests (by
tenant, session and request hash) return the stored result instead of being
re-executed; mismatched reuse of the same idempotency key raises a clear
error.
"""

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
    """Return a stable SHA-256 hex digest for the given request payload.

    The payload is canonicalized using JSON with sorted keys and compact
    separators so that semantically-equivalent dictionaries always produce the
    same hash. `ensure_ascii=False` preserves unicode characters.

    Args:
        payload: The request payload to hash.

    Returns:
        A hex string representing the SHA-256 digest of the canonical JSON.
    """
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # Use UTF-8 bytes for hashing to support non-ASCII characters.
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_jsonable_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Encode a payload into a JSON-serializable dictionary.

    `fastapi.encoders.jsonable_encoder` converts pydantic models, datetime
    objects, and other complex types into primitives that can be JSON
    serialized. This helper ensures the encoded value is a dictionary and
    raises a clear error otherwise.

    Args:
        payload: The input payload (typically a dict-like structure).

    Returns:
        A dictionary suitable for JSON serialization.

    Raises:
        TypeError: If the encoded payload is not a dictionary.
    """
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
    """Return a previously saved idempotent result or raise on mismatch.

    Looks up an `IdempotencyKey` by its `key` value. If no record exists,
    `None` is returned to indicate the caller should proceed and produce a
    new terminal result. If a record exists but the stored `tenant_id`,
    `session_id`, or `request_hash` don't match the current request, a
    `SchedulingError` is raised to signal unsafe reuse of the idempotency key.

    If a record exists and matches, the stored JSON result is decoded and
    returned as a dictionary.

    Args:
        db: SQLAlchemy session for DB operations.
        idempotency_key: The idempotency key string provided in the request.
        tenant_id: Tenant identifier for request scoping.
        session_id: Session identifier for request scoping.
        request_hash: Stable hash of the request payload (see
            `stable_request_hash`).

    Returns:
        The previously saved result as a dictionary, or `None` when no record
        exists.

    Raises:
        SchedulingError: If the key is reused with different request metadata.
        TypeError: If the stored JSON does not decode to a dictionary.
    """
    # Use Session.get for a primary-key lookup; `idempotency_key` is the PK.
    record = db.get(IdempotencyKey, idempotency_key)
    if record is None:
        # No saved result — caller should proceed to generate the terminal result.
        return None

    # Ensure the stored metadata matches the incoming request. If any field
    # differs we treat this as an unsafe reuse scenario and raise a domain
    # specific error so callers can surface an appropriate response.
    if (
        record.tenant_id != tenant_id
        or record.session_id != session_id
        or record.request_hash != request_hash
    ):
        raise SchedulingError(
            reason_code=IDEMPOTENCY_KEY_REUSE_MISMATCH,
            details="Stored request hash does not match the current request.",
        )

    # Load and validate the stored JSON result.
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
    """Persist a terminal result for an idempotency key.

    The `result` is normalized to a pure JSON-serializable dictionary using
    `to_jsonable_dict` before being serialized and stored. If no record exists
    for the given key, a new `IdempotencyKey` is created; otherwise the
    existing record is updated in-place.

    Args:
        db: SQLAlchemy session used for DB operations.
        idempotency_key: The idempotency key string.
        tenant_id: Tenant identifier for scoping.
        session_id: Session identifier for scoping.
        request_hash: Stable hash of the request payload.
        result: The terminal result to store (must be JSON-serializable).
    """
    normalized_result = to_jsonable_dict(result)
    # Use a deterministic JSON representation for storage.
    serialized = json.dumps(normalized_result, sort_keys=True, ensure_ascii=False)

    record = db.get(IdempotencyKey, idempotency_key)
    if record is None:
        # Create a new record; the caller's DB session should commit later.
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

    # Update existing record fields to reflect the terminal result.
    record.tenant_id = tenant_id
    record.session_id = session_id
    record.request_hash = request_hash
    record.result_json = serialized