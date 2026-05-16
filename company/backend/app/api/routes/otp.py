from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import HospitalRequestContext, get_db, get_hospital_request_context
from app.api.schemas.otp import OtpRequestIn, OtpRequestOut, OtpVerifyIn, OtpVerifyOut
from app.modules.otp.service import request_otp_code, verify_otp_code

router = APIRouter(prefix="/otp", tags=["otp"])


@router.post("/request", response_model=OtpRequestOut)
async def request_otp(
    body: OtpRequestIn,
    request: Request,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> OtpRequestOut:
    """Create an OTP challenge for the provided patient identity.

    The endpoint combines tenant/session metadata from headers with identity
    fields from the body, then delegates OTP issuance and rate-limit/audit
    checks to the OTP service layer.
    """
    # Request client can be absent in tests or synthetic requests.
    client_ip = request.client.host if request.client else "unknown"

    # Keep explicit mapping between transport schema (camelCase) and service
    # inputs to make validation and audit tracing unambiguous.
    result = await request_otp_code(
        db=db,
        header_tenant_id=context.tenant_id,
        session_id=context.session_id,
        client_ip=client_ip,
        body_tenant_id=body.tenantId,
        national_id=body.nationalId,
        email=body.email,
    )
    return OtpRequestOut(**result)


@router.post("/verify", response_model=OtpVerifyOut)
async def verify_otp(
    body: OtpVerifyIn,
    request: Request,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> OtpVerifyOut:
    """Verify a submitted OTP code for a patient identity request.

    The route forwards request context (tenant/session/client IP) together with
    user-submitted identity and OTP values so the service can enforce tenant
    isolation, expiry, attempt limits, and audit logging.
    """
    # Request client can be absent in tests or synthetic requests.
    client_ip = request.client.host if request.client else "unknown"

    # Preserve explicit field passing so schema/service contracts remain easy
    # to review when request or verification rules evolve.
    result = await verify_otp_code(
        db=db,
        header_tenant_id=context.tenant_id,
        session_id=context.session_id,
        client_ip=client_ip,
        body_tenant_id=body.tenantId,
        national_id=body.nationalId,
        email=body.email,
        otp=body.otp,
    )
    return OtpVerifyOut(**result)