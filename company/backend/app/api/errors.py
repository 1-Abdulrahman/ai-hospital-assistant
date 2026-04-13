from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import get_correlation_id


class ErrorResponseBuilder:
    @staticmethod
    def build(
        *,
        status_code: int,
        message: str,
        reason_code: str | None = None,
        details: str | None = None,
    ) -> JSONResponse:
        body = {
            "message": message,
            "correlationId": get_correlation_id(),
        }
        if reason_code:
            body["reasonCode"] = reason_code
        if details:
            body["details"] = details
        return JSONResponse(status_code=status_code, content=body)


def make_error_response(
    *,
    status_code: int,
    message: str,
    reason_code: str | None = None,
    details: str | None = None,
) -> JSONResponse:
    return ErrorResponseBuilder.build(
        status_code=status_code,
        message=message,
        reason_code=reason_code,
        details=details,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail

    if isinstance(detail, dict):
        return make_error_response(
            status_code=exc.status_code,
            message=detail.get("message", "Request failed."),
            reason_code=detail.get("reasonCode"),
            details=detail.get("details"),
        )

    return make_error_response(
        status_code=exc.status_code,
        message=str(detail) if detail else "Request failed.",
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return make_error_response(
        status_code=422,
        message="Request validation failed.",
        reason_code="VALIDATION_ERROR",
        details="Ensure the request body and required headers are valid.",
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return make_error_response(
        status_code=500,
        message="An unexpected error occurred.",
        reason_code="INTERNAL_ERROR",
    )