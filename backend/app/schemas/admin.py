"""Administrative user, role and settings schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.schemas.auth import PermissionOut, RoleBrief
from app.schemas.common import ORMModel


class UserCreate(ORMModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    first_name: str = Field(min_length=1, max_length=96)
    last_name: str = Field(min_length=1, max_length=96)
    password: str = Field(min_length=8, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=96)
    employee_code: str | None = Field(default=None, max_length=32)
    department: str | None = Field(default=None, max_length=64)
    role_codes: list[str] = []
    status: str = "active"
    must_change_password: bool = True


class UserUpdate(ORMModel):
    email: EmailStr | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=96)
    last_name: str | None = Field(default=None, min_length=1, max_length=96)
    phone: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=96)
    employee_code: str | None = Field(default=None, max_length=32)
    department: str | None = Field(default=None, max_length=64)
    role_codes: list[str] | None = None
    status: str | None = None
    must_change_password: bool | None = None


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    full_name: str
    phone: str | None = None
    job_title: str | None = None
    employee_code: str | None = None
    department: str | None = None
    status: str
    is_superuser: bool
    must_change_password: bool
    roles: list[RoleBrief] = []
    created_at: datetime
    last_login_at: datetime | None = None


class RoleOut(ORMModel):
    id: UUID
    code: str
    name: str
    description: str
    level: int
    is_system: bool
    is_active: bool
    permissions: list[PermissionOut] = []


class RoleCreate(ORMModel):
    code: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=96)
    description: str = ""
    level: int = Field(default=10, ge=1, le=99)
    permission_codes: list[str] = []


class RoleUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=2, max_length=96)
    description: str | None = None
    level: int | None = Field(default=None, ge=1, le=99)
    permission_codes: list[str] | None = None
    is_active: bool | None = None


class SettingOut(ORMModel):
    key: str
    value: str | None
    value_type: str
    group_name: str
    label: str
    description: str | None = None
    is_public: bool
    editable: bool


class SettingUpdate(ORMModel):
    value: str | None = None
