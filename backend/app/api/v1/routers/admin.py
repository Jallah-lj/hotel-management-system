"""Staff, roles, permissions and system setting administration."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import require_permission, require_super_admin
from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import PERMISSIONS, ROLE_DEFINITIONS
from app.core.security import hash_password, validate_password_strength
from app.db.enums import UserStatus
from app.db.models.operations import AuditLog, HotelSetting
from app.db.models.user import Permission, Role, User
from app.db.session import get_db
from app.schemas.admin import RoleCreate, RoleOut, RoleUpdate, SettingOut, SettingUpdate, UserCreate, UserOut, UserUpdate
from app.schemas.auth import PermissionOut, RoleBrief
from app.schemas.common import Message, Page, PaginationParams
from app.services.common import audit

router = APIRouter(prefix="/admin", tags=["Administration"])


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, username=user.username, first_name=user.first_name, last_name=user.last_name, full_name=user.full_name, phone=user.phone, job_title=user.job_title, employee_code=user.employee_code, department=user.department, status=user.status.value, is_superuser=user.is_superuser, must_change_password=user.must_change_password, roles=[RoleBrief(id=r.id, code=r.code, name=r.name, level=r.level) for r in user.roles if r.is_active], created_at=user.created_at, last_login_at=user.last_login_at)


@router.get("/users", response_model=Page[UserOut])
def list_users(pagination: PaginationParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_permission("users:view"))):
    q = select(User).where(User.deleted_at.is_(None)).options(selectinload(User.roles))
    if pagination.search:
        t = f"%{pagination.search.lower()}%"; q = q.where(or_(func.lower(User.email).like(t), func.lower(User.username).like(t), func.lower(User.first_name).like(t), func.lower(User.last_name).like(t)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(User.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    rows = db.scalars(q).all()
    return Page.build([user_out(row) for row in rows], total, pagination.page, pagination.page_size)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("users:create"))):
    validate_password_strength(payload.password)
    if db.scalar(select(User.id).where(or_(func.lower(User.email) == payload.email.lower(), func.lower(User.username) == payload.username.lower()), User.deleted_at.is_(None))): raise ConflictError("A staff account with that email or username already exists.")
    roles = list(db.scalars(select(Role).where(Role.code.in_(payload.role_codes), Role.is_active.is_(True))).all())
    if len(roles) != len(set(payload.role_codes)): raise NotFoundError("One or more requested roles were not found.")
    row = User(email=payload.email.lower(), username=payload.username, first_name=payload.first_name, last_name=payload.last_name, password_hash=hash_password(payload.password), phone=payload.phone, job_title=payload.job_title, employee_code=payload.employee_code, department=payload.department, status=UserStatus(payload.status), must_change_password=payload.must_change_password, created_by_id=actor.id, roles=roles)
    db.add(row); db.flush(); audit(db, user=actor, action="create", resource="users", resource_id=row.id, request=request); db.commit(); db.refresh(row); return user_out(row)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("users:update"))):
    row = db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)).options(selectinload(User.roles)))
    if not row: raise NotFoundError("Staff account not found.")
    values = payload.model_dump(exclude_unset=True, exclude={"role_codes"})
    for key, value in values.items(): setattr(row, key, UserStatus(value) if key == "status" else value)
    if payload.role_codes is not None:
        roles = list(db.scalars(select(Role).where(Role.code.in_(payload.role_codes), Role.is_active.is_(True))).all())
        if len(roles) != len(set(payload.role_codes)): raise NotFoundError("One or more requested roles were not found.")
        row.roles = roles
        audit(db, user=actor, action="permission_change", resource="users", resource_id=row.id, after={"roles": payload.role_codes}, request=request)
    db.commit(); db.refresh(row); return user_out(row)


@router.post("/users/{user_id}/deactivate", response_model=Message)
def deactivate_user(user_id: UUID, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("users:delete"))):
    row = db.get(User, user_id)
    if not row: raise NotFoundError("Staff account not found.")
    if row.id == actor.id: raise ConflictError("You cannot deactivate your own account.")
    row.status = UserStatus.INACTIVE; audit(db, user=actor, action="delete", resource="users", resource_id=row.id, request=request); db.commit(); return Message(message="Staff account deactivated.")


@router.get("/roles", response_model=Page[RoleOut])
def list_roles(pagination: PaginationParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_permission("roles:view"))):
    q = select(Role).where(Role.deleted_at.is_(None)).options(selectinload(Role.permissions)).order_by(Role.level.desc())
    total = db.scalar(select(func.count(Role.id)).where(Role.deleted_at.is_(None))) or 0
    rows = db.scalars(q.offset(pagination.offset).limit(pagination.page_size)).all()
    return Page.build(rows, total, pagination.page, pagination.page_size)


@router.post("/roles", response_model=RoleOut)
def create_role(payload: RoleCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("roles:manage"))):
    if db.scalar(select(Role.id).where(Role.code == payload.code, Role.deleted_at.is_(None))): raise ConflictError("A role with this code already exists.")
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(payload.permission_codes))).all())
    if len(perms) != len(set(payload.permission_codes)): raise NotFoundError("One or more permissions were not found.")
    row = Role(code=payload.code, name=payload.name, description=payload.description, level=payload.level, permissions=perms); db.add(row); db.flush(); audit(db, user=actor, action="permission_change", resource="roles", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: UUID, payload: RoleUpdate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("roles:manage"))):
    row = db.scalar(select(Role).where(Role.id == role_id, Role.deleted_at.is_(None)).options(selectinload(Role.permissions)))
    if not row: raise NotFoundError("Role not found.")
    if row.is_system and payload.level is not None and payload.level >= 100: raise ConflictError("System role hierarchy cannot be raised to administrator level.")
    for key, value in payload.model_dump(exclude_unset=True, exclude={"permission_codes"}).items(): setattr(row, key, value)
    if payload.permission_codes is not None:
        perms = list(db.scalars(select(Permission).where(Permission.code.in_(payload.permission_codes))).all())
        if len(perms) != len(set(payload.permission_codes)): raise NotFoundError("One or more permissions were not found.")
        row.permissions = perms
    audit(db, user=actor, action="permission_change", resource="roles", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(_: User = Depends(require_permission("roles:view"))):
    return [PermissionOut(code=p.code, resource=p.resource, action=p.action, group_name=p.group, description=p.description) for p in PERMISSIONS]


@router.get("/settings", response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db), _: User = Depends(require_permission("settings:view"))):
    return list(db.scalars(select(HotelSetting).where(HotelSetting.is_public.is_(True)).order_by(HotelSetting.group_name, HotelSetting.sort_order)).all())


@router.patch("/settings/{key}", response_model=SettingOut)
def update_setting(key: str, payload: SettingUpdate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("settings:manage"))):
    row = db.scalar(select(HotelSetting).where(HotelSetting.key == key))
    if not row: raise NotFoundError("Setting not found.")
    if not row.editable: raise ConflictError("This system setting is not editable.")
    row.value = payload.value; row.updated_by_id = actor.id; audit(db, user=actor, action="settings_change", resource="hotel_settings", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


@router.get("/audit-logs")
def audit_logs(pagination: PaginationParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_permission("audit_logs:view"))):
    q = select(AuditLog)
    if pagination.search: q = q.where(or_(AuditLog.resource.ilike(f"%{pagination.search}%"), AuditLog.action.ilike(f"%{pagination.search}%"), AuditLog.username.ilike(f"%{pagination.search}%")))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)).all()
    items = [{"id": str(row.id), "user_id": str(row.user_id) if row.user_id else None, "username": row.username, "user_role": row.user_role, "action": row.action, "resource": row.resource, "resource_id": row.resource_id, "description": row.description, "success": row.success, "ip_address": row.ip_address, "request_id": row.request_id, "created_at": row.created_at, "before_data": row.before_data, "after_data": row.after_data} for row in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)
