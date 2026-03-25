from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "OK",
        "version": settings.app_version,
        "time": datetime.now(timezone.utc).isoformat(),
    }