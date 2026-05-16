"""
Error handling module for API responses.

This module provides utilities for building standardized error responses with
correlation IDs and custom exception handlers for FastAPI applications.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import get_correlation_id


class ErrorResponseBuilder:
    """Builder class for constructing standardized JSON error responses."""

    @staticmethod
    def build(
        *,
        status_code: int,
        message: str,
        reason_code: str | None = None,
        details: str | None = None,
    ) -> JSONResponse:
        """
        Build a standardized JSON error response.

        Args:
            status_code: HTTP status code for the response.
            message: User-friendly error message.
            reason_code: Optional machine-readable error code for categorization.
            details: Optional detailed error information for debugging.

        Returns:
            JSONResponse with status code and formatted error body including
            a unique correlation ID for tracking.
        """
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
    """
    Convenience function to create a standardized error response.

    Wraps ErrorResponseBuilder.build() for simpler usage in exception handlers.

    Args:
        status_code: HTTP status code for the response.
        message: User-friendly error message.
        reason_code: Optional machine-readable error code for categorization.
        details: Optional detailed error information for debugging.

    Returns:
        JSONResponse with formatted error body.
    """
    return ErrorResponseBuilder.build(
        status_code=status_code,
        message=message,
        reason_code=reason_code,
        details=details,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions raised by Starlette/FastAPI.

    Extracts error details from the exception and formats them into a
    standardized error response. Supports both string messages and structured
    error detail dictionaries.

    Args:
        request: The incoming HTTP request.
        exc: The HTTP exception to handle.

    Returns:
        JSONResponse with appropriate status code and error details.
    """
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
    """
    Handle request validation errors from Pydantic.

    Returns a 422 Unprocessable Entity status with a standardized error
    response indicating that the request body or headers failed validation.

    Args:
        request: The incoming HTTP request.
        exc: The validation error raised by Pydantic.

    Returns:
        JSONResponse with 422 status code and validation error details.
    """
    return make_error_response(
        status_code=422,
        message="Request validation failed.",
        reason_code="VALIDATION_ERROR",
        details="Ensure the request body and required headers are valid.",
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all exception handler for unexpected errors.

    This is the final fallback for any unhandled exceptions in the application.
    Returns a generic 500 Internal Server Error without exposing sensitive
    exception details to the client.

    Args:
        request: The incoming HTTP request.
        exc: The unexpected exception.

    Returns:
        JSONResponse with 500 status code and generic error message.
    """
    return make_error_response(
        status_code=500,
        message="An unexpected error occurred.",
        reason_code="INTERNAL_ERROR",
    )