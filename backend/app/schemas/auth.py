"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: str = Field(description="Staff email address or username", min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)
    remember_me: bool = False

    @field_validator("email")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return value.strip()


class PermissionOut(ORMModel):
    code: str
    resource: str
    action: str
    group_name: str
    description: str


class RoleBrief(ORMModel):
    id: str
    code: str
    name: str
    level: int


class SessionUser(ORMModel):
    id: str
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    full_name: str
    job_title: str | None = None
    department: str | None = None
    avatar_url: str | None = None
    status: str
    is_superuser: bool
    must_change_password: bool
    roles: list[RoleBrief] = []
    permissions: list[str] = []


class TokenInfo(BaseModel):
    access_token: str | None = Field(default=None, description="Only returned when cookies are disabled")
    token_type: str = "bearer"
    expires_at: datetime
    session_id: str
    user: SessionUser


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

    @model_validator(mode="after")
    def _different(self):
        if self.current_password == self.new_password:
            raise ValueError("The new password must be different from the current password.")
        return self


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=200)


class SessionOut(ORMModel):
    id: str
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime
    current: bool = False
