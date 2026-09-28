"""Cross-module service helpers."""

from __future__ import annotations

import copy
import re
from datetime import date, datetime, UTC
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.operations import AuditLog, HotelSetting, Notification
from app.db.models.user import User

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def safe_float(value: Any) -> float:
    return float(money(value))


def make_number(prefix: str, sequence: int | None = None) -> str:
    """Public document ids are human-friendly but not security identifiers."""
    stamp = datetime.now(UTC).strftime("%y%m%d")
    if sequence is None:
        import secrets

        sequence = secrets.randbelow(9000) + 1000
    return f"{prefix}-{stamp}-{sequence:04d}"


def next_setting_number(db: Session, key: str, prefix: str) -> str:
    setting = db.scalar(select(HotelSetting).where(HotelSetting.key == key).with_for_update())
    if not setting:
        setting = HotelSetting(
            key=key,
            value="1",
            value_type="int",
            group_name="system",
            label=key.replace("_", " ").title(),
            editable=False,
        )
        db.add(setting)
        db.flush()
        return make_number(prefix, 1)
    current = int(setting.value or 0) + 1
    setting.value = str(current)
    return make_number(prefix, current)


def audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    resource: str,
    resource_id: UUID | str | None = None,
    description: str | None = None,
    before: Any | None = None,
    after: Any | None = None,
    request: Any | None = None,
    success: bool = True,
    status_code: int | None = None,
) -> AuditLog:
    """Append an audit record.  Values are copied and normalised so a later
    ORM mutation cannot change the historical snapshot in memory."""
    ip = None
    agent = None
    method = None
    path = None
    request_id = None
    if request is not None:
        ip = request.client.host if request.client else None
        agent = request.headers.get("user-agent", "")[:400]
        method = request.method
        path = request.url.path[:255]
        request_id = getattr(request.state, "request_id", None)
    role = user.primary_role.code if user and user.primary_role else None
    row = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        user_role=role,
        action=action,
        resource=resource,
        resource_id=str(resource_id) if resource_id else None,
        description=description,
        method=method,
        path=path,
        status_code=status_code,
        success=success,
        ip_address=ip,
        user_agent=agent,
        request_id=request_id,
        before_data=copy.deepcopy(_json_safe(before)) if before is not None else None,
        after_data=copy.deepcopy(_json_safe(after)) if after is not None else None,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    return row


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def notify(
    db: Session,
    *,
    user_id: UUID,
    title: str,
    message: str,
    category: str = "system",
    severity: str = "info",
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | str | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    if dedupe_key:
        exists = db.scalar(select(Notification.id).where(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key))
        if exists:
            return None
    row = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        severity=severity,
        link=link,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    return row


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
