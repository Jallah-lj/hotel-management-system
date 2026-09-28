"""Declarative base, naming conventions and shared mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names keep Alembic migrations stable across
# environments (important for Postgres, where unnamed constraints are painful
# to alter later).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        """Derive ``snake_case`` table names from CamelCase class names."""
        name = cls.__name__
        out = [name[0].lower()]
        for char in name[1:]:
            out.append(f"_{char.lower()}" if char.isupper() else char)
        table = "".join(out)
        if not table.endswith("s"):
            table += "s"
        return table


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Financial and guest records are never hard deleted.

    ``deleted_at`` marks the row as archived; all repository queries filter
    these rows out unless ``include_deleted`` is requested.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, index=True)
    deleted_reason: Mapped[str | None] = mapped_column(default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditColumnsMixin:
    @declared_attr
    def created_by_id(cls):  # noqa: N805, ANN201
        return mapped_column(Uuid(as_uuid=True), nullable=True)

    @declared_attr
    def updated_by_id(cls):  # noqa: N805, ANN201
        return mapped_column(Uuid(as_uuid=True), nullable=True)


def enum_column(enum_cls, name: str, **kwargs):
    """Portable enum column.

    Stored as VARCHAR with a CHECK constraint rather than a native Postgres
    ENUM type: this keeps migrations simple, avoids ``ALTER TYPE`` lock pain and
    lets the same schema run on SQLite for the fast test suite.
    """
    return mapped_column(
        SAEnum(
            enum_cls,
            name=name,
            native_enum=False,
            length=32,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        **kwargs,
    )
