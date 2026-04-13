from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import HospitalRequestContext, get_db, get_hospital_request_context
from app.api.schemas.scheduling import (
    BookingRequest,
    BookingResponse,
    SlotsRequest,
    SlotsResponse,
)
from app.modules.scheduling.reason_codes import SchedulingError
from app.modules.scheduling.service import book_appointment, list_available_slots

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


def raise_from_scheduling_error(exc: SchedulingError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": exc.user_message,
            "reasonCode": exc.reason_code,
            **({"details": exc.details} if exc.details else {}),
        },
    )


@router.post("/slots", response_model=SlotsResponse)
async def get_slots(
    body: SlotsRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> SlotsResponse:
    try:
        result = await list_available_slots(
            db=db,
            header_tenant_id=context.tenant_id,
            session_id=context.session_id,
            body_tenant_id=body.tenantId,
            specialty=body.specialty,
        )
    except SchedulingError as exc:
        raise_from_scheduling_error(exc)

    return SlotsResponse(**result)


@router.post("/book", response_model=BookingResponse)
async def create_booking(
    body: BookingRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> BookingResponse:
    try:
        result = await book_appointment(
            db=db,
            header_tenant_id=context.tenant_id,
            session_id=context.session_id,
            body_tenant_id=body.tenantId,
            national_id=body.nationalId,
            email=body.email,
            specialty=body.specialty,
            slot_id=body.slotId,
            idempotency_key=idempotency_key,
        )
    except SchedulingError as exc:
        raise_from_scheduling_error(exc)

    return BookingResponse(**result)