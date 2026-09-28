"""FastAPI dependencies for authentication and RBAC."""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.enums import UserStatus
from app.db.models.user import Role, User
from app.db.session import get_db

logger = logging.getLogger("app.auth")

_bearer = HTTPBearer(auto_error=False)


def _extract_access_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    # Bearer is convenient for API clients and OpenAPI; the secure cookie is
    # used by the first-party web app.
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return request.cookies.get("hms_access") or request.cookies.get("hms_session")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_access_token(request, credentials)
    if not token:
        raise AuthenticationError()
    payload = decode_token(token, expected_type="access")
    subject = payload.get("sub")
    try:
        user_id = UUID(str(subject))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("Invalid authentication subject.") from exc

    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
        )
    )
    if not user or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("This account is inactive. Contact an administrator.")
    if user.is_locked:
        raise AuthenticationError("This account is temporarily locked. Try again later.")
    request.state.user = user
    return user


def require_permission(permission: str) -> Callable:
    def _permission_dependency(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser or permission in user.permission_codes:
            return user
        raise PermissionDeniedError(
            f"Your role does not grant the {permission} permission.",
            details={"required_permission": permission},
        )

    return _permission_dependency


def require_any_permission(*permissions: str) -> Callable:
    def _permission_dependency(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser or any(p in user.permission_codes for p in permissions):
            return user
        raise PermissionDeniedError(
            "Your role does not grant access to this resource.",
            details={"required_any_permission": list(permissions)},
        )

    return _permission_dependency


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser and "users:update" not in user.permission_codes:
        raise PermissionDeniedError("Only a system administrator can perform this action.")
    return user
