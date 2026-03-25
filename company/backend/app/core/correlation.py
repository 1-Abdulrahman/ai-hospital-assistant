import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "X-Correlation-Id"

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def get_correlation_id() -> str | None:
    return correlation_id_ctx.get()