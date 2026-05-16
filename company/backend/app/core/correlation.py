"""
Correlation ID management module.

Provides utilities for tracking request correlation IDs across async contexts.
Correlation IDs are used to trace related operations throughout the system,
making it easier to debug and correlate logs from different components.
"""

import uuid
from contextvars import ContextVar

# HTTP header name for passing correlation IDs between services
CORRELATION_HEADER = "X-Correlation-Id"

# Context variable to store correlation ID per async context
# Using ContextVar ensures each async task/request has its own isolated correlation ID
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    """
    Generate a new unique correlation ID.

    Creates a new UUID-based correlation ID for tracking related operations
    across the system. Typically called at the start of a request.

    Returns:
        str: A new UUID-based correlation ID as a string.

    Example:
        >>> corr_id = new_correlation_id()
        >>> correlation_id_ctx.set(corr_id)
    """
    return str(uuid.uuid4())


def get_correlation_id() -> str | None:
    """
    Retrieve the current correlation ID from the context.

    Gets the correlation ID associated with the current async context.
    Returns None if no correlation ID has been set for this context.

    Returns:
        str | None: The current correlation ID, or None if not set.

    Example:
        >>> corr_id = get_correlation_id()
        >>> if corr_id:
        ...     headers[CORRELATION_HEADER] = corr_id
    """
    return correlation_id_ctx.get()