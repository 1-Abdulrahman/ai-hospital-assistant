from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_portal_user, get_db
from app.api.schemas.auth import AuthenticatedPortalUser, CurrentUserResponse
from app.modules.observability.query_service import (
    get_analytics_summary,
    get_bookings_page,
    get_recent_bookings,
    get_sessions_page,
    get_traces_by_correlation_id,
    get_traces_by_session_id,
)

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        tenantId=current_user.tenantId,
        email=current_user.email,
        role=current_user.role,
    )


@router.get("/analytics/summary")
def portal_analytics_summary(
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> dict:
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
    return get_recent_bookings(
        db=db,
        current_user=current_user,
        limit=limit,
    )


@router.get("/bookings")
def portal_bookings(
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


@router.get("/traces/{correlation_id}")
def portal_traces_by_correlation_id(
    correlation_id: str,
    current_user: AuthenticatedPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> list[dict]:
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
    return get_traces_by_session_id(
        db=db,
        current_user=current_user,
        session_id=session_id,
    )