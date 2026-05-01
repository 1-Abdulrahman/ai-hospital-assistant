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
    client_ip = request.client.host if request.client else "unknown"

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
    client_ip = request.client.host if request.client else "unknown"

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