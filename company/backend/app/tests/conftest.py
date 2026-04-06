from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# If latest branch includes NLP startup loading, keep these so startup
# never tries to reach the internet during tests.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_LOCAL_FILES_ONLY", "1")

from app.api.deps import get_db
from app.core.security import create_access_token, hash_password
from app.db.models import Base, PortalUser, Tenant
from app.main import app


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed minimum tenants
    db.add_all(
        [
            Tenant(id="platform", name="Platform"),
            Tenant(id="demo", name="Demo Hospital Tenant"),
        ]
    )

    # Seed minimum users
    db.add_all(
        [
            PortalUser(
                id=uuid.uuid4().hex,
                tenant_id="platform",
                email="admin@company.local",
                password_hash=hash_password("CompanyAdmin123!"),
                role="company_admin",
                is_active=True,
            ),
            PortalUser(
                id=uuid.uuid4().hex,
                tenant_id="demo",
                email="admin@mvp.local",
                password_hash=hash_password("Admin123!"),
                role="tenant_admin",
                is_active=True,
            ),
            PortalUser(
                id=uuid.uuid4().hex,
                tenant_id="demo",
                email="inactive@mvp.local",
                password_hash=hash_password("Admin123!"),
                role="tenant_admin",
                is_active=False,
            ),
        ]
    )
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def company_admin_token(db_session) -> str:
    user = (
        db_session.query(PortalUser)
        .filter(
            PortalUser.tenant_id == "platform",
            PortalUser.role == "company_admin",
        )
        .first()
    )
    return create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
        expires_in_seconds=3600,
    )


@pytest.fixture()
def tenant_admin_token(db_session) -> str:
    user = (
        db_session.query(PortalUser)
        .filter(
            PortalUser.tenant_id == "demo",
            PortalUser.role == "tenant_admin",
            PortalUser.is_active.is_(True),
        )
        .first()
    )
    return create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
        expires_in_seconds=3600,
    )