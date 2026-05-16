from dataclasses import dataclass
from typing import Generator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.auth import AuthenticatedPortalUser
from app.core.security import TokenValidationError, decode_access_token
from app.db.models import PortalUser
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Provide a SQLAlchemy session per request and always close it afterward.
    
    This is a dependency injection function designed for use with FastAPI's Depends()
    to automatically provide a database session to route handlers. The session is
    guaranteed to be closed after the request completes, whether successful or not.
    
    Yields:
        Session: A SQLAlchemy ORM session for database operations.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _raise_http_error(*, status_code: int, message: str, reason_code: str, details: str | None = None) -> None:
    """Raise the API error envelope expected by the frontend and integration tests.
    
    Constructs a standardized error response that includes a human-readable message,
    a machine-readable reason code, and optional additional details. This ensures
    consistent error handling across all API endpoints.
    
    Args:
        status_code: HTTP status code (e.g., 400, 401, 403).
        message: Human-readable error message for the user.
        reason_code: Machine-readable error code for frontend error handling (e.g., 'MISSING_TOKEN').
        details: Optional additional error details for debugging purposes.
    
    Raises:
        HTTPException: Always raises with the provided status code and error details.
    """
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
    """Authenticate the caller and enforce tenant scoping from request headers.
    
    This dependency function validates Bearer tokens and extracts user/tenant information,
    ensuring that each request comes from an authenticated, active user accessing only
    their own tenant's data. Multi-factor security checks include:
    - Session ID presence verification
    - Bearer token format and presence validation
    - JWT token decode and claims extraction
    - Database user existence and status check
    - Tenant isolation enforcement
    
    Args:
        authorization: Authorization header containing "Bearer <token>".
        x_tenant_id: Tenant ID header for tenant scope isolation.
        x_session_id: Session ID header identifying the user session.
        db: SQLAlchemy session for database queries.
    
    Returns:
        AuthenticatedPortalUser: Authenticated user info with tenant context.
    
    Raises:
        HTTPException: 400 if required headers are missing or empty.
        HTTPException: 401 if token is missing, malformed, invalid, or user not found.
        HTTPException: 403 if user is inactive or tenant scope is violated.
    """
    # Validate session ID is provided and non-empty
    if not x_session_id.strip():
        _raise_http_error(
            status_code=400,
            message="X-Session-Id header is required.",
            reason_code="INVALID_REQUEST",
        )

    # Verify authorization header exists
    if authorization is None:
        _raise_http_error(
            status_code=401,
            message="Authorization token is required.",
            reason_code="MISSING_TOKEN",
        )

    # Parse Bearer scheme and extract token
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        _raise_http_error(
            status_code=401,
            message="Authorization header format must be Bearer <token>.",
            reason_code="INVALID_TOKEN",
        )

    # Validate Bearer scheme format
    if scheme.lower() != "bearer" or not token.strip():
        _raise_http_error(
            status_code=401,
            message="Authorization header format must be Bearer <token>.",
            reason_code="INVALID_TOKEN",
        )

    # Decode JWT token and extract claims
    try:
        claims = decode_access_token(token)
    except TokenValidationError as exc:
        _raise_http_error(
            status_code=exc.status_code,
            message=exc.message,
            reason_code=exc.reason_code,
        )

    # Extract user and tenant IDs from token claims
    user_id = claims.get("sub")
    tenant_id = claims.get("tenantId")

    # Verify required claims are present
    if not user_id or not tenant_id:
        _raise_http_error(
            status_code=401,
            message="Token is invalid.",
            reason_code="INVALID_TOKEN",
        )

    # Look up user in database, ensuring they belong to the correct tenant
    user = (
        db.query(PortalUser)
        .filter(PortalUser.id == user_id, PortalUser.tenant_id == tenant_id)
        .first()
    )

    # Ensure user exists
    if user is None:
        _raise_http_error(
            status_code=401,
            message="Authenticated user was not found.",
            reason_code="AUTH_USER_NOT_FOUND",
        )

    # Check that user account is active
    if not user.is_active:
        _raise_http_error(
            status_code=403,
            message="User account is inactive.",
            reason_code="INACTIVE_USER",
        )

    # Enforce tenant isolation: tenant admins can only access their own tenant
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
    """Validated request-scoped identifiers used across hospital portal calls.
    
    This dataclass encapsulates the essential routing and tracing information
    extracted from request headers. It ensures multi-tenant isolation and enables
    request correlation for logging and debugging purposes.
    
    Attributes:
        tenant_id: Unique identifier for the tenant making the request.
        session_id: Session identifier linking the request to a user session.
        correlation_id: Optional unique ID for tracing related requests across services.
    """

    tenant_id: str
    session_id: str
    correlation_id: str | None = None


def get_hospital_request_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> HospitalRequestContext:
    """Extract the tenant/session headers that tie a request to a portal flow.
    
    This dependency function validates and extracts request headers necessary for
    multi-tenant request routing and session tracking. Unlike get_current_portal_user(),
    this function does not perform authentication or database lookups—it only validates
    and normalizes the request context headers.
    
    Args:
        x_tenant_id: Tenant identifier header (required, non-empty).
        x_session_id: Session identifier header (required, non-empty).
        x_correlation_id: Optional correlation ID for distributed tracing.
    
    Returns:
        HospitalRequestContext: Validated request context with tenant/session/correlation IDs.
    
    Raises:
        HTTPException: 400 if X-Tenant-Id or X-Session-Id headers are missing or empty.
    """
    # Validate tenant ID is provided and non-empty
    if x_tenant_id is None or not x_tenant_id.strip():
        _raise_http_error(
            status_code=400,
            message="X-Tenant-Id header is required.",
            reason_code="INVALID_REQUEST",
        )

    # Validate session ID is provided and non-empty
    if x_session_id is None or not x_session_id.strip():
        _raise_http_error(
            status_code=400,
            message="X-Session-Id header is required.",
            reason_code="INVALID_REQUEST",
        )

    # Return context with trimmed header values; correlation ID is optional
    return HospitalRequestContext(
        tenant_id=x_tenant_id.strip(),
        session_id=x_session_id.strip(),
        correlation_id=x_correlation_id.strip() if x_correlation_id else None,
    )