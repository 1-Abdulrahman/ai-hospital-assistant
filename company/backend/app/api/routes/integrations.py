from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/fhir/status")
async def fhir_status() -> dict:
    timeout = httpx.Timeout(
        connect=settings.fhir_timeout_connect,
        read=settings.fhir_timeout_read,
        write=settings.fhir_timeout_read,
        pool=settings.fhir_timeout_read,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{settings.fhir_base_url}/metadata")
            response.raise_for_status()

        return {
            "status": "OK",
            "fhirBaseUrl": settings.fhir_base_url,
            "time": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return {
            "status": "DEGRADED",
            "fhirBaseUrl": settings.fhir_base_url,
            "time": datetime.now(timezone.utc).isoformat(),
            "reasonCode": "FHIR_UNREACHABLE",
        }