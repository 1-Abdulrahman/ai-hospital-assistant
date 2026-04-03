from fastapi import APIRouter, Depends

from app.api.deps import get_current_portal_user
from app.api.schemas.auth import AuthenticatedPortalUser, CurrentUserResponse

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