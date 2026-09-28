"""Application configuration.

All secrets and environment specific values are read from environment
variables (or a local ``.env`` file, which is never committed).  Nothing in
this module contains a production credential - the defaults are development
safe fallbacks only.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Application -------------------------------------------------------
    project_name: str = "Aurora Grand Hotel Management System"
    api_v1_prefix: str = "/api/v1"
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    enable_docs: bool = True
    # Explicitly disabled by default. The Arena preview enables this to avoid
    # repeated sign-ins while testing seeded workflows; never enable in prod.
    demo_mode: bool = False
    demo_user_email: str = "admin@auroragrand.example"
    demo_user_password: str = "AuroraAdmin!2026"
    timezone: str = "UTC"
    default_currency: str = "USD"
    default_tax_rate: float = 10.0  # percentage applied to accommodation & services

    # -- Security ----------------------------------------------------------
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    password_reset_expire_minutes: int = 60
    jwt_algorithm: str = "HS256"
    max_failed_logins: int = 5
    account_lockout_minutes: int = 15
    login_rate_limit: str = "10/minute"
    api_rate_limit: str = "600/minute"
    # Cookies
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    session_cookie_name: str = "hms_session"
    refresh_cookie_name: str = "hms_refresh"
    csrf_cookie_name: str = "hms_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    csrf_enabled: bool = True
    password_min_length: int = 10

    # -- Database ----------------------------------------------------------
    # Production (PostgreSQL): postgresql+psycopg://user:pass@host:5432/hms
    database_url: str = "postgresql+psycopg://hms:hms@localhost:5432/hms"
    sql_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # -- CORS --------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_credentials: bool = True

    # -- Email (optional; password reset links are logged when unset) ------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@auroragrand.example"
    smtp_use_tls: bool = True

    # -- Operational -------------------------------------------------------
    backup_retention_days: int = 30
    low_inventory_threshold_ratio: float = 1.0

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        raw = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if "*" in raw:
            return ["*"]
        return raw

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def model_post_init(self, __context: Any) -> None:  # pragma: no cover
        if self.is_production:
            if self.cookie_samesite == "none" and not self.cookie_secure:
                raise ValueError("SameSite=None cookies must be Secure")
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
