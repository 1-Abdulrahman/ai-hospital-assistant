from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.auth import LoginRequest, LoginResponse, normalize_portal_role
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.models import PortalUser

router = APIRouter(tags=["auth"])


def _raise_http_error(*, status_code: int, message: str, reason_code: str, details: str | None = None) -> None:
    """Raise a standardized API error payload for auth endpoints."""
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": message,
            "reasonCode": reason_code,
            **({"details": details} if details else {}),
        },
    )


def _resolve_user_for_login(payload: LoginRequest, db: Session) -> PortalUser | None:
    """Resolve a user from the login payload using supported identifier combinations."""
    if payload.tenantId and payload.email:
        return (
            db.query(PortalUser)
            .filter(
                PortalUser.tenant_id == payload.tenantId,
                PortalUser.email == str(payload.email),
            )
            .first()
        )

    username = (payload.username or "").strip().lower()

    # Keep backward compatibility with legacy/demo usernames used in local demos.
    if username in {"admin", "company_admin", "platform", "platform_admin"}:
        return (
            db.query(PortalUser)
            .filter(
                PortalUser.tenant_id == "platform",
                PortalUser.role == "company_admin",
            )
            .first()
        )

    if username in {"tenant", "tenant_admin", "demo", "demo_admin"}:
        return (
            db.query(PortalUser)
            .filter(
                PortalUser.tenant_id == "demo",
                PortalUser.role == "tenant_admin",
            )
            .first()
        )

    # Deterministic ordering avoids ambiguous user selection if email appears in many tenants.
    return (
        db.query(PortalUser)
        .filter(PortalUser.email == username)
        .order_by(PortalUser.tenant_id.asc())
        .first()
    )


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Authenticate a portal user and return an access token response."""
    user = _resolve_user_for_login(payload, db)

    if user is None:
        _raise_http_error(
            status_code=401,
            message="Invalid credentials.",
            reason_code="INVALID_CREDENTIALS",
        )

    if not user.is_active:
        _raise_http_error(
            status_code=403,
            message="User account is inactive.",
            reason_code="INACTIVE_USER",
        )

    if not verify_password(payload.password, user.password_hash):
        _raise_http_error(
            status_code=401,
            message="Invalid credentials.",
            reason_code="INVALID_CREDENTIALS",
        )

    access_token = create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
        expires_in_seconds=settings.jwt_access_token_ttl_seconds,
    )

    return LoginResponse.from_values(
        access_token=access_token,
        expires_in=settings.jwt_access_token_ttl_seconds,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
        portal_role=normalize_portal_role(user.role),
    )