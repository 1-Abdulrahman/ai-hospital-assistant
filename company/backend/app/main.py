from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.api.middleware import CorrelationIdMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.otp import router as otp_router
from app.api.routes.portal import router as portal_router
from app.api.routes.scheduling import router as scheduling_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.modules.nlp.inference import try_load_nlp_service

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    nlp_service, nlp_status = try_load_nlp_service()

    app.state.nlp_service = nlp_service
    app.state.nlp_status = nlp_status
    app.state.nlp_available = nlp_service is not None
    app.state.started_at_utc = datetime.now(timezone.utc)

    try:
        yield
    finally:
        app.state.nlp_service = None
        app.state.nlp_available = False

        if hasattr(app.state, "nlp_status") and isinstance(app.state.nlp_status, dict):
            app.state.nlp_status["shutdownAt"] = datetime.now(timezone.utc).isoformat()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
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

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(health_router)
app.include_router(integrations_router)
app.include_router(auth_router)
app.include_router(portal_router)
app.include_router(otp_router)
app.include_router(scheduling_router)
app.include_router(chat_router)
