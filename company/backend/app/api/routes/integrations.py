from fastapi import APIRouter

from app.modules.fhir_gateway.client import FhirClient

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/fhir/status")
async def fhir_status() -> dict:
    """Return current FHIR gateway integration status for diagnostics."""
    # Instantiate the gateway client per request to use current app configuration.
    client = FhirClient()
    return await client.get_status_payload()
