"""Authentication endpoints.  Access and refresh tokens are HttpOnly cookies
for the first-party web UI; the JSON response also supports non-browser API
clients without ever exposing a password or raw refresh session in logs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.errors import AuthenticationError
from app.core.security import generate_opaque_token
from app.db.models.user import RefreshToken, Role, User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RoleBrief,
    SessionUser,
    TokenInfo,
)
from app.schemas.common import Message
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def user_payload(user: User) -> SessionUser:
    return SessionUser(
        id=str(user.id), email=user.email, username=user.username, first_name=user.first_name, last_name=user.last_name,
        full_name=user.full_name, job_title=user.job_title, department=user.department, avatar_url=user.avatar_url,
        status=user.status.value, is_superuser=user.is_superuser, must_change_password=user.must_change_password,
        roles=[RoleBrief(id=str(r.id), code=r.code, name=r.name, level=r.level) for r in user.roles if r.is_active],
        permissions=sorted(user.permission_codes),
    )


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    common = dict(httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, domain=settings.cookie_domain, path="/")
    response.set_cookie("hms_access", access, max_age=settings.access_token_expire_minutes * 60, **common)
    response.set_cookie(settings.refresh_cookie_name, refresh, max_age=settings.refresh_token_expire_days * 86400, **common)
    # Non-HttpOnly token used by the browser to prove same-site intent.  The
    # API checks it in production middleware for state-changing requests.
    if settings.csrf_enabled:
        response.set_cookie(settings.csrf_cookie_name, generate_opaque_token(24), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite, domain=settings.cookie_domain, path="/")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("hms_access", path="/", domain=settings.cookie_domain)
    response.delete_cookie(settings.refresh_cookie_name, path="/", domain=settings.cookie_domain)
    response.delete_cookie(settings.csrf_cookie_name, path="/", domain=settings.cookie_domain)


@router.post("/login", response_model=TokenInfo, summary="Sign in a staff member")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    result = AuthService(db).login(payload.email, payload.password, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), request=request, enforce_rate_limit=not settings.demo_mode)
    _set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return TokenInfo(access_token=result["access_token"], expires_at=result["expires_at"], session_id=str(result["session_id"]), user=user_payload(result["user"]))


@router.post("/demo-login", response_model=TokenInfo, summary="Test-only automatic demo sign-in")
def demo_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """Open the seeded admin session for the isolated development preview.

    This route is deliberately unavailable unless DEMO_MODE=true, and the
    production configuration keeps that flag false. It exists only so a
    sandbox reviewer can open the operational workspace without repeatedly
    entering development credentials.
    """
    if not settings.demo_mode or settings.environment == "production":
        from app.core.errors import NotFoundError
        raise NotFoundError("Demo sign-in is not enabled.")
    result = AuthService(db).login(
        settings.demo_user_email,
        settings.demo_user_password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request=request,
        enforce_rate_limit=False,
    )
    _set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return TokenInfo(access_token=result["access_token"], expires_at=result["expires_at"], session_id=str(result["session_id"]), user=user_payload(result["user"]))


@router.post("/refresh",  response_model=TokenInfo, summary="Rotate the refresh session")
def refresh(payload: RefreshRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    raw = payload.refresh_token or request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise AuthenticationError("Refresh session is missing.")
    result = AuthService(db).refresh(raw, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), request=request)
    _set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return TokenInfo(access_token=result["access_token"], expires_at=result["expires_at"], session_id=str(result["session_id"]), user=user_payload(result["user"]))


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).logout(request.cookies.get(settings.refresh_cookie_name), user, request)
    _clear_auth_cookies(response)
    return Message(message="Signed out successfully.")


@router.get("/me", response_model=SessionUser)
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


@router.post("/change-password", response_model=Message)
def change_password(payload: PasswordChangeRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).change_password(user, payload.current_password, payload.new_password, request)
    return Message(message="Password changed. Other sessions have been signed out.")


@router.post("/password-reset/request", response_model=Message)
def password_reset_request(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    # Never reveal whether an address exists.
    raw = AuthService(db).request_password_reset(payload.email, request.client.host if request.client else None, request)
    return Message(message="If that account exists, a password reset link has been sent.", detail=raw if settings.environment != "production" else None)


@router.post("/password-reset/confirm", response_model=Message)
def password_reset_confirm(payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    AuthService(db).confirm_password_reset(payload.token, payload.new_password, request)
    return Message(message="Password reset successfully. Please sign in again.")


@router.get("/sessions")
def sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).order_by(RefreshToken.created_at.desc())).all()
    return [{"id": str(r.id), "ip_address": r.ip_address, "user_agent": r.user_agent, "created_at": r.created_at, "expires_at": r.expires_at, "current": False} for r in rows]


@router.delete("/sessions", response_model=Message)
def revoke_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from datetime import UTC, datetime
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))
    db.commit()
    return Message(message="All active sessions have been revoked.")
