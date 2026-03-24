import os
import uuid

from app.core.security import hash_password
from app.db.models import PortalUser, Tenant
from app.db.session import SessionLocal


DEMO_TENANT_ID = "demo-tenant"
DEMO_TENANT_NAME = "Demo Hospital Tenant"
DEMO_ADMIN_EMAIL = "admin@demo.local"
DEMO_ADMIN_ROLE = "admin"


def run() -> None:
    db = SessionLocal()
    try:
        tenant = db.get(Tenant, DEMO_TENANT_ID)
        if not tenant:
            db.add(Tenant(id=DEMO_TENANT_ID, name=DEMO_TENANT_NAME))

        email = DEMO_ADMIN_EMAIL
        existing = (
            db.query(PortalUser)
            .filter_by(tenant_id=DEMO_TENANT_ID, email=email)
            .first()
        )

        if not existing:
            demo_password = os.getenv("DEMO_ADMIN_PASSWORD", "Admin123!")
            db.add(
                PortalUser(
                    id=uuid.uuid4().hex,
                    tenant_id=DEMO_TENANT_ID,
                    email=email,
                    password_hash=hash_password(demo_password),
                    role=DEMO_ADMIN_ROLE,
                )
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