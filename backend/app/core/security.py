"""Password hashing, JWT issuing/verification and token helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

TokenType = Literal["access", "refresh", "password_reset"]

WEAK_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "admin123",
    "letmein123",
    "welcome123",
    "changeme",
    "hotel123",
    "passw0rd",
}


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return a bcrypt hash. Plaintext is never persisted anywhere."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> None:
    """Raise ``ValueError`` when a password does not meet policy."""
    from app.core.errors import ValidationError

    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"be at least {settings.password_min_length} characters long")
    if not re.search(r"[A-Z]", password):
        problems.append("contain an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("contain a lowercase letter")
    if not re.search(r"\d", password):
        problems.append("contain a digit")
    if password.lower() in WEAK_PASSWORDS:
        problems.append("not be a commonly used password")
    if problems:
        raise ValidationError("Password must " + ", ".join(problems) + ".")


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Create a signed JWT.  Returns ``(token, jti, expires_at)``."""
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "aurora-grand-hms",
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def create_access_token(
    subject: str, extra_claims: dict[str, Any] | None = None, expires_minutes: int | None = None
) -> tuple[str, str, datetime]:
    minutes = expires_minutes or settings.access_token_expire_minutes
    return _create_token(subject, "access", timedelta(minutes=minutes), extra_claims)


def create_refresh_token(subject: str, extra_claims: dict[str, Any] | None = None) -> tuple[str, str, datetime]:
    return _create_token(
        subject, "refresh", timedelta(days=settings.refresh_token_expire_days), extra_claims
    )


def create_password_reset_token(subject: str) -> tuple[str, str, datetime]:
    return _create_token(subject, "password_reset", timedelta(minutes=settings.password_reset_expire_minutes))


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    from app.core.errors import AuthenticationError

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer="aurora-grand-hms",
        )
    except JWTError as exc:  # expired, bad signature, malformed ...
        raise AuthenticationError("Your session is invalid or has expired. Please sign in again.") from exc

    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError("Invalid token type for this operation.")
    return payload


# ---------------------------------------------------------------------------
# Opaque tokens / CSRF
# ---------------------------------------------------------------------------
def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 digest - refresh/reset tokens are stored hashed, never raw."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def mask_secret(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return value
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)
