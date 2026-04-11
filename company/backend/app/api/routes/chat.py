from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import HospitalRequestContext, get_db, get_hospital_request_context
from app.api.schemas.chat import (
    ChatConfirmRequest,
    ChatDirectStartRequest,
    ChatMessageRequest,
    ChatRenewalRequest,
    ChatResponse,
    ChatSelectionRequest,
    ChatRenewalIdentifyRequest,
)
from app.modules.orchestration.service import (
    ChatOrchestrationError,
    process_chat_message,
    process_confirm,
    process_direct_start,
    process_renewal_request,
    process_selection,
    process_renewal_identity,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _raise_from_chat_error(exc: ChatOrchestrationError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": exc.user_message,
            "reasonCode": exc.reason_code,
            **({"details": exc.details} if exc.details else {}),
        },
    )


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    body: ChatMessageRequest,
    request: Request,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = await process_chat_message(
            db=db,
            header_tenant_id=context.tenant_id,
            header_session_id=context.session_id,
            body_tenant_id=body.tenantId,
            client_session_id=body.clientSessionId,
            message_text=body.messageText,
            nlp_service=getattr(request.app.state, "nlp_service", None),
        )
    except ChatOrchestrationError as exc:
        _raise_from_chat_error(exc)
    return ChatResponse(**result)


@router.post("/direct/start", response_model=ChatResponse)
async def chat_direct_start(
    body: ChatDirectStartRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = await process_direct_start(
            db=db,
            header_tenant_id=context.tenant_id,
            header_session_id=context.session_id,
            body_tenant_id=body.tenantId,
            client_session_id=body.clientSessionId,
        )
    except ChatOrchestrationError as exc:
        _raise_from_chat_error(exc)
    return ChatResponse(**result)


@router.post("/renewal/request", response_model=ChatResponse)
async def chat_renewal_request(
    body: ChatRenewalRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = await process_renewal_request(
            db=db,
            header_tenant_id=context.tenant_id,
            header_session_id=context.session_id,
            body_tenant_id=body.tenantId,
            client_session_id=body.clientSessionId,
        )
    except ChatOrchestrationError as exc:
        _raise_from_chat_error(exc)
    return ChatResponse(**result)


@router.post("/selection", response_model=ChatResponse)
async def chat_selection(
    body: ChatSelectionRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = await process_selection(
            db=db,
            header_tenant_id=context.tenant_id,
            header_session_id=context.session_id,
            body_tenant_id=body.tenantId,
            client_session_id=body.clientSessionId,
            selection_type=body.selectionType,
            selection_id=body.selectionId,
            selection_value=body.selectionValue,
        )
    except ChatOrchestrationError as exc:
        _raise_from_chat_error(exc)
    return ChatResponse(**result)


@router.post("/confirm", response_model=ChatResponse)
async def chat_confirm(
    body: ChatConfirmRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = await process_confirm(
            db=db,
            header_tenant_id=context.tenant_id,
            header_session_id=context.session_id,
            body_tenant_id=body.tenantId,
            client_session_id=body.clientSessionId,
            action=body.action,
            specialty_id=body.specialtyId,
            slot_id=body.slotId,
            national_id=body.nationalId,
            email=body.email,
            renewal_item_id=body.renewalItemId,
            idempotency_key=idempotency_key,
        )
    except ChatOrchestrationError as exc:
        _raise_from_chat_error(exc)
    return ChatResponse(**result)

@router.post("/renewal/identify", response_model=ChatResponse)
async def chat_renewal_identify(
    body: ChatRenewalIdentifyRequest,
    context: HospitalRequestContext = Depends(get_hospital_request_context),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = await process_renewal_identity(
            db=db,
            header_tenant_id=context.tenant_id,
            header_session_id=context.session_id,
            body_tenant_id=body.tenantId,
            client_session_id=body.clientSessionId,
            national_id=body.nationalId,
        )
    except ChatOrchestrationError as exc:
        _raise_from_chat_error(exc)

    return ChatResponse(**result)