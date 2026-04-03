from dataclasses import dataclass
from typing import Generator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.auth import AuthenticatedPortalUser
from app.core.security import TokenValidationError, decode_access_token
from app.db.models import PortalUser
from app.db.session import SessionLocal

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _raise_http_error(*, status_code: int, message: str, reason_code: str, details: str | None = None) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": message,
            "reasonCode": reason_code,
            **({"details": details} if details else {}),
        },
    )


def get_current_portal_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_tenant_id: str = Header(alias="X-Tenant-Id"),
    x_session_id: str = Header(alias="X-Session-Id"),
    db: Session = Depends(get_db),
) -> AuthenticatedPortalUser:
    if not x_session_id.strip():
        _raise_http_error(
            status_code=400,
            message="X-Session-Id header is required.",
            reason_code="INVALID_REQUEST",
        )

    if authorization is None:
        _raise_http_error(
            status_code=401,
            message="Authorization token is required.",
            reason_code="MISSING_TOKEN",
        )

    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        _raise_http_error(
            status_code=401,
            message="Authorization header format must be Bearer <token>.",
            reason_code="INVALID_TOKEN",
        )

    if scheme.lower() != "bearer" or not token.strip():
        _raise_http_error(
            status_code=401,
            message="Authorization header format must be Bearer <token>.",
            reason_code="INVALID_TOKEN",
        )

    try:
        claims = decode_access_token(token)
    except TokenValidationError as exc:
        _raise_http_error(
            status_code=exc.status_code,
            message=exc.message,
            reason_code=exc.reason_code,
        )

    user_id = claims.get("sub")
    tenant_id = claims.get("tenantId")

    if not user_id or not tenant_id:
        _raise_http_error(
            status_code=401,
            message="Token is invalid.",
            reason_code="INVALID_TOKEN",
        )

    user = (
        db.query(PortalUser)
        .filter(PortalUser.id == user_id, PortalUser.tenant_id == tenant_id)
        .first()
    )

    if user is None:
        _raise_http_error(
            status_code=401,
            message="Authenticated user was not found.",
            reason_code="AUTH_USER_NOT_FOUND",
        )

    if not user.is_active:
        _raise_http_error(
            status_code=403,
            message="User account is inactive.",
            reason_code="INACTIVE_USER",
        )

    if user.role == "tenant_admin" and x_tenant_id != user.tenant_id:
        _raise_http_error(
            status_code=403,
            message="Tenant access is restricted to the signed-in tenant.",
            reason_code="TENANT_SCOPE_VIOLATION",
        )

    return AuthenticatedPortalUser(
        id=user.id,
        tenantId=user.tenant_id,
        email=user.email,
        role=user.role,
        requestTenantId=x_tenant_id,
        isActive=user.is_active,
    )
    
    

@dataclass(frozen=True)
class HospitalRequestContext:
    tenant_id: str
    session_id: str
    correlation_id: str | None = None


def get_hospital_request_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> HospitalRequestContext:
    if x_tenant_id is None or not x_tenant_id.strip():
        _raise_http_error(
            status_code=400,
            message="X-Tenant-Id header is required.",
            reason_code="INVALID_REQUEST",
        )

    if x_session_id is None or not x_session_id.strip():
        _raise_http_error(
            status_code=400,
            message="X-Session-Id header is required.",
            reason_code="INVALID_REQUEST",
        )

    return HospitalRequestContext(
        tenant_id=x_tenant_id.strip(),
        session_id=x_session_id.strip(),
        correlation_id=x_correlation_id.strip() if x_correlation_id else None,
    )