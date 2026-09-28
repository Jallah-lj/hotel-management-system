"""Domain errors and the exception handlers that translate them into a
consistent, client friendly JSON error envelope::

    {
      "error": {
        "code": "insufficient_balance",
        "message": "Outstanding balance of 120.00 USD must be settled first.",
        "details": {...},
        "request_id": "..."
      }
    }

Stack traces are never returned to clients - unexpected exceptions are logged
with the request id and answered with a generic 500.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for expected, business level failures."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.status_code = status_code or self.status_code
        super().__init__(self.message)


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "The submitted data is invalid."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"
    message = "Authentication is required."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class BusinessRuleError(AppError):
    """Violation of a hotel business rule (double booking, closed folio ...)."""

    status_code = status.HTTP_409_CONFLICT
    code = "business_rule_violation"
    message = "This operation violates a hotel policy."


class RoomNotAvailableError(BusinessRuleError):
    code = "room_not_available"
    message = "The selected room is not available for the requested dates."


class AccountLockedError(AppError):
    status_code = status.HTTP_423_LOCKED
    code = "account_locked"
    message = "This account is temporarily locked after repeated failed sign-in attempts."


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Please slow down and try again shortly."


def error_payload(
    code: str, message: str, details: Any | None = None, request_id: str | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id or request_id_ctx.get("-"),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:  # noqa: C901 - declarative registry
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.exception("Application error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for err in exc.errors():
            location = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
            fields.append({"field": location or "request", "message": err.get("msg", "Invalid value")})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload(
                "validation_error", "Please correct the highlighted fields.", fields
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "not_authenticated",
            403: "permission_denied",
            404: "not_found",
            405: "method_not_allowed",
            429: "rate_limited",
        }.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(status_code=exc.status_code, content=error_payload(code, message))

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Database integrity error: %s", exc.orig)
        detail = str(getattr(exc, "orig", ""))
        if "unique" in detail.lower() or "duplicate" in detail.lower():
            message = "A record with these details already exists."
            code = "duplicate_record"
        elif "foreign key" in detail.lower():
            message = "This record is referenced by other data and cannot be changed."
            code = "reference_error"
        else:
            message = "The data conflicts with an existing record or database rule."
            code = "integrity_error"
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=error_payload(code, message))

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Unexpected database error")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_payload(
                "database_unavailable",
                "The database is temporarily unavailable. Please try again.",
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        incident = str(uuid.uuid4())[:8]
        logger.exception("Unhandled exception [incident=%s]", incident)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(
                "internal_error",
                f"Something went wrong on our side. Reference: {incident}",
            ),
        )
