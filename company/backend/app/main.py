from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import generic_exception_handler
from app.api.middleware import CorrelationIdMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.integrations import router as integrations_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.hospital_origin, settings.portal_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Correlation-Id",
        "X-Tenant-Id",
        "X-Session-Id",
        "Idempotency-Key",
    ],
    expose_headers=["X-Correlation-Id"],
)

app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(health_router)
app.include_router(integrations_router)