"""Aurora Grand HMS API application entrypoint."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.api.v1.routers import admin, auth, dashboard, finance, guests, operations, property as property_router, reports, reservations
from app.core.config import settings
from app.core.errors import error_payload, register_exception_handlers
from app.core.logging import Timer, configure_logging, request_id_ctx
from app.db.base import Base
from app.db.models import *  # noqa: F401,F403 - registers every model for dev create_all
from app.db.session import check_database_connection, engine

configure_logging()
logger = logging.getLogger("app")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        timer = Timer()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-ms"] = str(timer.elapsed_ms)
            return response
        finally:
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit protection for cookie-authenticated state changes.

    Bearer API clients are not subject to this browser-specific check.  Login,
    refresh and health are public exceptions.
    """
    async def dispatch(self, request: Request, call_next):
        if settings.csrf_enabled and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path not in {"/health", f"{settings.api_v1_prefix}/auth/login", f"{settings.api_v1_prefix}/auth/refresh"}:
            cookie_access = request.cookies.get("hms_access") or request.cookies.get(settings.session_cookie_name)
            auth_header = request.headers.get("authorization", "")
            if cookie_access and not auth_header.lower().startswith("bearer "):
                csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
                csrf_header = request.headers.get(settings.csrf_header_name)
                if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                    return JSONResponse(status_code=403, content=error_payload("csrf_failed", "CSRF validation failed."))
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables only for local development/test convenience. Production
    # deploys use the explicit Alembic migration command in README.
    if settings.environment in ("development", "test"):
        Base.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        description="Secure, transactional hotel operations API for Aurora Grand Hotel.",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=settings.cors_allow_credentials, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"])
    register_exception_handlers(app)

    prefix = settings.api_v1_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(guests.router, prefix=prefix)
    app.include_router(property_router.router, prefix=prefix)
    app.include_router(reservations.router, prefix=prefix)
    app.include_router(finance.router, prefix=prefix)
    app.include_router(operations.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)

    @app.get("/health", tags=["System"])
    def health():
        ok, detail = check_database_connection()
        body = {"status": "ok" if ok else "degraded", "service": "aurora-grand-hms-api", "database": "connected" if ok else "unavailable"}
        if detail and settings.debug: body["detail"] = detail
        return JSONResponse(status_code=200 if ok else 503, content=body)

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": settings.project_name, "version": "1.0.0", "docs": "/docs" if settings.enable_docs else None, "health": "/health"}

    return app


app = create_app()
