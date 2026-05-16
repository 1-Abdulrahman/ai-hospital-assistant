from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_portal_user, get_db
from app.api.schemas.auth import AuthenticatedPortalUser, CurrentUserResponse
from app.modules.observability.query_service import (
    get_analytics_summary,
    get_audit_page,
    get_bookings_page,
    get_nlp_recent,
    get_nlp_stats,
    get_recent_bookings,
    get_sessions_page,
    get_tenant_detail,
    get_tenants,
    get_traces_by_correlation_id,
    get_traces_by_session_id,
)

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
) -> CurrentUserResponse:
    """Return the authenticated portal identity used by the frontend shell.

    This endpoint is typically called after login to hydrate user context
    (tenant, email, role) for route guards and role-aware UI rendering.
    """
    return CurrentUserResponse(
        tenantId=current_user.tenantId,
        email=current_user.email,
        role=current_user.role,
    )


@router.get("/analytics/summary")
def portal_analytics_summary(
    # Public API keeps `from`/`to` query names; map to Python-safe parameters.
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return aggregate metrics for dashboard cards within a date window.

    The query params are validated as ISO-like calendar dates (YYYY-MM-DD)
    before delegating to the observability query service.
    """
    return get_analytics_summary(
        db=db,
        current_user=current_user,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/bookings/recent")
def portal_recent_bookings(
    limit: int = Query(10, ge=1, le=50),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return a small, recency-ordered booking feed for quick portal views."""
    return get_recent_bookings(
        db=db,
        current_user=current_user,
        limit=limit,
    )


@router.get("/bookings")
def portal_bookings(
    # Alias external camelCase query keys to backend snake_case names.
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status: str | None = Query(default=None),
    specialty: str | None = Query(default=None),
    reason_code: str | None = Query(default=None, alias="reasonCode"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return paginated bookings filtered by operational and taxonomy fields.

    Supports optional filtering by status, specialty, and normalized reason code.
    Results are constrained by the authenticated user's tenant visibility.
    """
    return get_bookings_page(
        db=db,
        current_user=current_user,
        from_date=from_date,
        to_date=to_date,
        status=status,
        specialty=specialty,
        reason_code=reason_code,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions")
def portal_sessions(
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return paginated conversational session activity for reporting views.

    Tenant admins can optionally narrow results to a specific tenant id while
    keeping the same endpoint contract for super-admin and tenant scopes.
    """
    return get_sessions_page(
        db=db,
        current_user=current_user,
        from_date=from_date,
        to_date=to_date,
        status=status,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )


@router.get("/tenants")
def portal_tenants(
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """List tenants visible to the authenticated user role and scope."""
    return get_tenants(
        db=db,
        current_user=current_user,
    )


@router.get("/tenants/{tenant_id}")
def portal_tenant_detail(
    tenant_id: str,
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return tenant details by id with a consistent 404 error contract."""
    result = get_tenant_detail(
        db=db,
        current_user=current_user,
        tenant_id=tenant_id,
    )
    if result is None:
        # Keep error payload shape consistent with other API modules.
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Tenant not found.",
                "reasonCode": "TENANT_NOT_FOUND",
            },
        )
    return result


@router.get("/audit")
def portal_audit(
    # Preserve frontend query names while exposing Pythonic parameter names.
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    event_type: str | None = Query(default=None, alias="eventType"),
    outcome: str | None = Query(default=None),
    reason_code: str | None = Query(default=None, alias="reasonCode"),
    correlation_id: str | None = Query(default=None, alias="correlationId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return paginated audit events with optional traceability filters.

    Supports filtering by event dimensions plus `correlationId`/`sessionId`
    to help operators reconstruct end-to-end request flows.
    """
    return get_audit_page(
        db=db,
        current_user=current_user,
        from_date=from_date,
        to_date=to_date,
        event_type=event_type,
        outcome=outcome,
        reason_code=reason_code,
        correlation_id=correlation_id,
        session_id=session_id,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )


@router.get("/nlp/stats")
def portal_nlp_stats(
    request: Request,
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
) -> dict:
    """Expose runtime NLP health/status counters for portal observability."""
    return get_nlp_stats(
        # NLP service/state may be unset in limited test environments.
        nlp_service=getattr(request.app.state, "nlp_service", None),
        nlp_status=getattr(request.app.state, "nlp_status", None),
    )


@router.get("/nlp/recent")
def portal_nlp_recent(
    limit: int = Query(20, ge=1, le=100),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return recent NLP records scoped to the current user's visibility."""
    return get_nlp_recent(
        db=db,
        current_user=current_user,
        limit=limit,
    )


@router.get("/traces/{correlation_id}")
def portal_traces_by_correlation_id(
    correlation_id: str,
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return trace records grouped under a shared correlation identifier."""
    return get_traces_by_correlation_id(
        db=db,
        current_user=current_user,
        correlation_id=correlation_id,
    )


@router.get("/traces/by-session/{session_id}")
def portal_traces_by_session_id(
    session_id: str,
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return trace records associated with a conversational session id."""
    return get_traces_by_session_id(
        db=db,
        current_user=current_user,
        session_id=session_id,
    )