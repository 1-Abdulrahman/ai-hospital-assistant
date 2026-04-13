from __future__ import annotations

import os

import pytest

from app.core.security import (
    TokenValidationError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db import seed
from app.db.models import PortalUser, Tenant


def test_hash_password_and_verify_password() -> None:
    password = "Admin123!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("WrongPassword", password_hash) is False


def test_create_and_decode_access_token() -> None:
    token = create_access_token(
        subject="user-123",
        tenant_id="demo",
        email="admin@mvp.local",
        role="tenant_admin",
        expires_in_seconds=3600,
    )

    claims = decode_access_token(token)

    assert claims["sub"] == "user-123"
    assert claims["tenantId"] == "demo"
    assert claims["email"] == "admin@mvp.local"
    assert claims["role"] == "tenant_admin"


def test_decode_expired_access_token_raises() -> None:
    token = create_access_token(
        subject="user-123",
        tenant_id="demo",
        email="admin@mvp.local",
        role="tenant_admin",
        expires_in_seconds=-1,
    )

    with pytest.raises(TokenValidationError) as exc:
        decode_access_token(token)

    assert exc.value.reason_code == "TOKEN_EXPIRED"


def test_seed_run_is_idempotent(db_session, monkeypatch) -> None:
    class FakeSessionLocal:
        def __call__(self):
            return db_session

    monkeypatch.setattr(seed, "SessionLocal", FakeSessionLocal())

    # Set demo passwords explicitly so the test is deterministic
    monkeypatch.setenv("DEMO_COMPANY_ADMIN_PASSWORD", "CompanyAdmin123!")
    monkeypatch.setenv("DEMO_TENANT_ADMIN_PASSWORD", "Admin123!")

    seed.run()
    seed.run()

    tenants = db_session.query(Tenant).all()
    users = db_session.query(PortalUser).all()

    # conftest seeded 2 tenants and 3 users already, so idempotent re-run should not duplicate them
    assert len([t for t in tenants if t.id == "platform"]) == 1
    assert len([t for t in tenants if t.id == "demo"]) == 1
    assert len([u for u in users if u.email == "admin@company.local" and u.tenant_id == "platform"]) == 1
    assert len([u for u in users if u.email == "admin@mvp.local" and u.tenant_id == "demo"]) == 1