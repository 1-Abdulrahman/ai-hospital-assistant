from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.correlation import get_correlation_id


class ErrorResponse(BaseModel):
    message: str
    correlationId: str | None = None
    reasonCode: str | None = None
    details: str | None = None


def make_error_response(
    *,
    status_code: int,
    message: str,
    reason_code: str | None = None,
    details: str | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        message=message,
        correlationId=get_correlation_id(),
        reasonCode=reason_code,
        details=details,
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return make_error_response(
        status_code=500,
        message="An unexpected error occurred.",
        reason_code="INTERNAL_ERROR",
    )