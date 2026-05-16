"""Database seeding module for initial data population.

This module initializes the database with default tenants and portal users.
It creates a Platform tenant for company-level administration and a Demo tenant
for testing purposes, along with their respective admin accounts.
"""
import os
import uuid

from app.core.security import hash_password
from app.db.models import PortalUser, Tenant
from app.db.session import SessionLocal


# Platform tenant configuration (company-level administration)
PLATFORM_TENANT_ID = "platform"
PLATFORM_TENANT_NAME = "Platform"

# Demo tenant configuration (for testing and demonstration)
DEMO_TENANT_ID = "demo"
DEMO_TENANT_NAME = "Demo Hospital Tenant"

# Platform-level admin credentials
COMPANY_ADMIN_EMAIL = "admin@company.local"
COMPANY_ADMIN_ROLE = "company_admin"

# Tenant-level admin credentials for demo environment
TENANT_ADMIN_EMAIL = "admin@mvp.local"
TENANT_ADMIN_ROLE = "tenant_admin"


def ensure_tenant(db, tenant_id: str, name: str) -> None:
    """Create a tenant if it does not already exist.

    Args:
        db: Database session instance.
        tenant_id: Unique identifier for the tenant.
        name: Display name for the tenant.
    """
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
    """Create a portal user if one with the same email does not exist in the tenant.

    This function provides idempotent user creation - it only adds a new user if
    an account with the given email doesn't already exist in the specified tenant.
    The password is hashed before storage for security.

    Args:
        db: Database session instance.
        tenant_id: ID of the tenant to which the user belongs.
        email: Email address of the user (must be unique per tenant).
        password: Plain text password (will be hashed before storage).
        role: User role within the system (e.g., 'tenant_admin', 'company_admin').
    """
    # Check if user already exists for this tenant
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
    """Execute the database seeding process.

    This function initializes the database with required tenants and admin users.
    It retrieves admin passwords from environment variables with secure defaults.
    All database operations are committed atomically, with rollback on error.

    Environment Variables:
        DEMO_COMPANY_ADMIN_PASSWORD: Password for platform admin (default: CompanyAdmin123!)
        DEMO_TENANT_ADMIN_PASSWORD: Password for tenant admin (default: Admin123!)
    """
    db = SessionLocal()
    try:
        # Retrieve admin passwords from environment, with fallback defaults
        company_admin_password = os.getenv("DEMO_COMPANY_ADMIN_PASSWORD", "CompanyAdmin123!")
        tenant_admin_password = os.getenv("DEMO_TENANT_ADMIN_PASSWORD", "Admin123!")

        # Create default tenants
        ensure_tenant(db, PLATFORM_TENANT_ID, PLATFORM_TENANT_NAME)
        ensure_tenant(db, DEMO_TENANT_ID, DEMO_TENANT_NAME)

        # Create platform-level admin user
        ensure_portal_user(
            db,
            tenant_id=PLATFORM_TENANT_ID,
            email=COMPANY_ADMIN_EMAIL,
            password=company_admin_password,
            role=COMPANY_ADMIN_ROLE,
        )

        # Create tenant-level admin user for demo
        ensure_portal_user(
            db,
            tenant_id=DEMO_TENANT_ID,
            email=TENANT_ADMIN_EMAIL,
            password=tenant_admin_password,
            role=TENANT_ADMIN_ROLE,
        )

        # Persist all changes to the database
        db.commit()
        print("Seed complete.")
    except Exception:
        # Rollback all changes if any error occurs
        db.rollback()
        raise
    finally:
        # Ensure database connection is properly closed
        db.close()


if __name__ == "__main__":
    run()