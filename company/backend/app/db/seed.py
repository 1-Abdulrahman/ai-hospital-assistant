import os
import uuid

from app.core.security import hash_password
from app.db.models import PortalUser, Tenant
from app.db.session import SessionLocal


PLATFORM_TENANT_ID = "platform"
PLATFORM_TENANT_NAME = "Platform"

DEMO_TENANT_ID = "demo"
DEMO_TENANT_NAME = "Demo Hospital Tenant"

COMPANY_ADMIN_EMAIL = "admin@company.local"
COMPANY_ADMIN_ROLE = "company_admin"

TENANT_ADMIN_EMAIL = "admin@mvp.local"
TENANT_ADMIN_ROLE = "tenant_admin"


def ensure_tenant(db, tenant_id: str, name: str) -> None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        db.add(Tenant(id=tenant_id, name=name))


def ensure_portal_user(
    db,
    *,
    tenant_id: str,
    email: str,
    password: str,
    role: str,
) -> None:
    existing = (
        db.query(PortalUser)
        .filter_by(tenant_id=tenant_id, email=email)
        .first()
    )

    if existing is None:
        db.add(
            PortalUser(
                id=uuid.uuid4().hex,
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
        )


def run() -> None:
    db = SessionLocal()
    try:
        company_admin_password = os.getenv("DEMO_COMPANY_ADMIN_PASSWORD", "CompanyAdmin123!")
        tenant_admin_password = os.getenv("DEMO_TENANT_ADMIN_PASSWORD", "Admin123!")

        ensure_tenant(db, PLATFORM_TENANT_ID, PLATFORM_TENANT_NAME)
        ensure_tenant(db, DEMO_TENANT_ID, DEMO_TENANT_NAME)

        ensure_portal_user(
            db,
            tenant_id=PLATFORM_TENANT_ID,
            email=COMPANY_ADMIN_EMAIL,
            password=company_admin_password,
            role=COMPANY_ADMIN_ROLE,
        )

        ensure_portal_user(
            db,
            tenant_id=DEMO_TENANT_ID,
            email=TENANT_ADMIN_EMAIL,
            password=tenant_admin_password,
            role=TENANT_ADMIN_ROLE,
        )

        db.commit()
        print("Seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()