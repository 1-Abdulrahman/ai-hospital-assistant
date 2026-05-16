"""Middleware to propagate a correlation id and log request duration.

This module provides a small Starlette/ASGI middleware that ensures every
incoming request has a correlation id associated with it. The id is read
from the incoming request header named by `CORRELATION_HEADER` or generated
when absent. The middleware stores the id in a context variable so other
parts of the application (for example logging or services) can retrieve it.

Behavior:
- Read or generate a correlation id for the request.
- Set the correlation id into `correlation_id_ctx` (a contextvar) and keep
  the token so the previous context can be restored.
- Measure the request handling duration and log a brief info message.
- Reset the contextvar to avoid leaking the id across requests.
- Add the correlation id to the outgoing response headers.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import CORRELATION_HEADER, correlation_id_ctx, new_correlation_id

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach and propagate a correlation id for each request.

    The middleware sets a correlation id into a context variable so other
    code can access it during request processing. It also logs the request
    duration and ensures the correlation id is present on the response so
    clients and downstream services can correlate logs and traces.
    """

    async def dispatch(self, request: Request, call_next):
        """Handle an incoming request and return the response.

        Args:
            request: Incoming Starlette `Request` object.
            call_next: Callable that forwards the request to the next
                handler and returns a `Response`.

        Returns:
            A `Response` instance with the correlation id header set.
        """

        # Obtain an existing correlation id from the incoming headers or
        # generate a new one when not provided by the client. This enables
        # distributed tracing where upstream services pass their correlation
        # id down the chain.
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_correlation_id()

        # Store the correlation id in the contextvar and keep the token so
        # the previous value can be restored after the request completes.
        # This is critical in async environments where multiple requests may
        # be processed concurrently by the same thread.
        token = correlation_id_ctx.set(correlation_id)

        # Measure request processing duration using perf_counter for precise
        # elapsed time measurement. Unlike time.time(), perf_counter is not
        # affected by system clock adjustments.
        start = time.perf_counter()
        try:
            # Forward the request to the next handler in the ASGI app stack.
            response: Response = await call_next(request)
        finally:
            # Always executed: compute duration and log basic request info.
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request completed",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "durationMs": duration_ms,
                },
            )
            # Restore the previous contextvar value to avoid cross-request
            # contamination. This is essential because the same async task
            # or thread pool thread may handle multiple requests sequentially.
            correlation_id_ctx.reset(token)

        # Ensure the response includes the correlation id for tracing.
        # This allows clients and downstream services to track the complete
        # request lifecycle across service boundaries.
        response.headers[CORRELATION_HEADER] = correlation_id
        return response