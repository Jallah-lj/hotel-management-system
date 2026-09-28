"""Authentication workflows: login throttling, rotating refresh sessions,
password change/reset and audit entries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import AccountLockedError, AuthenticationError, ConflictError, NotFoundError, RateLimitError
from app.core.security import (
    constant_time_compare,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.db.enums import AuditAction, UserStatus
from app.db.models.operations import AuditLog
from app.db.models.user import LoginAttempt, PasswordResetToken, RefreshToken, Role, User
from app.services.common import audit

logger = logging.getLogger("app.auth.service")


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def find_user(self, identifier: str) -> User | None:
        value = identifier.strip().lower()
        return self.db.scalar(
            select(User)
            .where(
                or_(func.lower(User.email) == value, func.lower(User.username) == value),
                User.deleted_at.is_(None),
            )
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )

    def login(self, identifier: str, password: str, *, ip: str | None, user_agent: str | None, request=None, enforce_rate_limit: bool = True) -> dict:
        # A database-backed IP throttle survives worker restarts and applies
        # before account lookup, making it resistant to credential stuffing and
        # account enumeration through timing differences. The isolated demo
        # bootstrap is explicitly exempt so repeated sandbox reloads cannot
        # lock the test workspace out.
        if enforce_rate_limit and ip:
            window_start = datetime.now(UTC) - timedelta(minutes=1)
            recent = self.db.scalar(select(func.count(LoginAttempt.id)).where(LoginAttempt.ip_address == ip, LoginAttempt.attempted_at >= window_start)) or 0
            if recent >= 10:
                raise RateLimitError()
        user = self.find_user(identifier)
        now = datetime.now(UTC)
        if user and user.locked_until and user.locked_until > now:
            self._record_attempt(identifier, user, False, ip, user_agent, "locked")
            self.db.commit()
            raise AccountLockedError()

        valid = bool(user and verify_password(password, user.password_hash))
        if not valid:
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= settings.max_failed_logins:
                    user.locked_until = now + timedelta(minutes=settings.account_lockout_minutes)
                    user.failed_login_count = 0
            self._record_attempt(identifier, user, False, ip, user_agent, "invalid_credentials")
            audit(self.db, user=user, action=AuditAction.LOGIN_FAILED.value, resource="auth", description="Failed sign in", request=request, success=False, status_code=401)
            self.db.commit()
            raise AuthenticationError("Invalid email/username or password.")

        if user.status != UserStatus.ACTIVE:
            self._record_attempt(identifier, user, False, ip, user_agent, "inactive")
            self.db.commit()
            raise AuthenticationError("This account is not active. Contact an administrator.")
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        user.last_login_ip = ip
        self._record_attempt(identifier, user, True, ip, user_agent, None)
        access, _access_jti, access_exp = create_access_token(
            str(user.id), {"roles": user.role_codes, "permissions": sorted(user.permission_codes)}
        )
        refresh, refresh_jti, refresh_exp = create_refresh_token(str(user.id))
        session = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            jti=refresh_jti,
            expires_at=refresh_exp,
            ip_address=ip,
            user_agent=(user_agent or "")[:400],
        )
        self.db.add(session)
        audit(self.db, user=user, action=AuditAction.LOGIN.value, resource="auth", resource_id=user.id, description="Successful sign in", request=request, status_code=200)
        self.db.commit()
        return {"user": user, "access_token": access, "refresh_token": refresh, "expires_at": access_exp, "session_id": session.id}

    def refresh(self, raw_refresh: str, *, ip: str | None, user_agent: str | None, request=None) -> dict:
        payload = decode_token(raw_refresh, expected_type="refresh")
        jti = payload.get("jti")
        row = self.db.scalar(
            select(RefreshToken).where(RefreshToken.jti == jti, RefreshToken.token_hash == hash_token(raw_refresh)).with_for_update()
        )
        if not row or not row.is_valid:
            raise AuthenticationError("This refresh session is no longer valid. Please sign in again.")
        user = self.db.scalar(
            select(User).where(User.id == row.user_id, User.deleted_at.is_(None)).options(selectinload(User.roles).selectinload(Role.permissions))
        )
        if not user or not user.is_active:
            raise AuthenticationError("This account is not active.")
        row.revoked_at = datetime.now(UTC)
        access, _, access_exp = create_access_token(str(user.id), {"roles": user.role_codes, "permissions": sorted(user.permission_codes)})
        refresh, refresh_jti, refresh_exp = create_refresh_token(str(user.id))
        row.replaced_by_jti = refresh_jti
        self.db.add(RefreshToken(user_id=user.id, token_hash=hash_token(refresh), jti=refresh_jti, expires_at=refresh_exp, ip_address=ip, user_agent=(user_agent or "")[:400]))
        audit(self.db, user=user, action="token_refresh", resource="auth", resource_id=user.id, request=request)
        self.db.commit()
        return {"user": user, "access_token": access, "refresh_token": refresh, "expires_at": access_exp, "session_id": row.id}

    def logout(self, raw_refresh: str | None, user: User, request=None) -> None:
        if raw_refresh:
            payload = None
            try:
                payload = decode_token(raw_refresh, expected_type="refresh")
            except AuthenticationError:
                pass
            if payload:
                self.db.execute(update(RefreshToken).where(RefreshToken.jti == payload.get("jti"), RefreshToken.user_id == user.id).values(revoked_at=datetime.now(UTC)))
        audit(self.db, user=user, action=AuditAction.LOGOUT.value, resource="auth", resource_id=user.id, request=request)
        self.db.commit()

    def change_password(self, user: User, current: str, new: str, request=None) -> None:
        if not verify_password(current, user.password_hash):
            raise AuthenticationError("Current password is incorrect.")
        validate_password_strength(new)
        user.password_hash = hash_password(new)
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        # Password change invalidates every other refresh session.
        self.db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))
        audit(self.db, user=user, action="password_change", resource="users", resource_id=user.id, request=request)
        self.db.commit()

    def request_password_reset(self, email: str, ip: str | None, request=None) -> str | None:
        # Deliberately identical behaviour for unknown emails (anti-enumeration).
        user = self.db.scalar(select(User).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None)))
        if not user:
            return None
        raw, _, expires = create_password_reset_token(str(user.id))
        self.db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(raw), expires_at=expires, requested_ip=ip))
        self.db.commit()
        logger.info("Password reset requested for user id=%s; delivery is delegated to the configured mailer", user.id)
        return raw if not settings.smtp_host else None

    def confirm_password_reset(self, raw_token: str, new_password: str, request=None) -> None:
        validate_password_strength(new_password)
        payload = decode_token(raw_token, expected_type="password_reset")
        row = self.db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token)).with_for_update())
        if not row or row.used_at or row.expires_at <= datetime.now(UTC) or str(row.user_id) != str(payload.get("sub")):
            raise AuthenticationError("This password reset link is invalid or has expired.")
        user = self.db.get(User, row.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("This account is not active.")
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        row.used_at = datetime.now(UTC)
        self.db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))
        audit(self.db, user=user, action="password_reset", resource="users", resource_id=user.id, request=request)
        self.db.commit()

    def _record_attempt(self, identifier: str, user: User | None, succeeded: bool, ip: str | None, agent: str | None, reason: str | None) -> None:
        self.db.add(LoginAttempt(email=identifier[:255].lower(), user_id=user.id if user else None, succeeded=succeeded, ip_address=ip, user_agent=(agent or "")[:400], failure_reason=reason))
