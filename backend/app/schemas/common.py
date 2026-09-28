"""Shared schema helpers: pagination, ordering and generic responses."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from math import ceil
from typing import Generic, Literal, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, str_strip_whitespace=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Total number of matching records")
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool

    @classmethod
    def build(cls, items: Sequence[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = max(1, ceil(total / page_size)) if total else 0
        return cls(
            items=list(items),
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            has_next=page < pages,
            has_previous=page > 1,
        )


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class PaginationParams:
    """Reusable dependency providing validated pagination + sorting."""

    def __init__(
        self,
        page: int = Query(1, ge=1, le=10_000, description="1-based page number"),
        page_size: int = Query(20, ge=1, le=200, description="Records per page"),
        sort_by: str | None = Query(None, description="Column to sort by"),
        sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
        search: str | None = Query(None, max_length=120, description="Free text search"),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_dir = SortDirection(sort_dir)
        self.search = search.strip() if search else None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def order_column(self, mapping: dict[str, object], default: object) -> object:
        if self.sort_by and self.sort_by in mapping:
            return mapping[self.sort_by]
        return default

    def apply_order(self, query, mapping: dict[str, object], default: object):
        column = self.order_column(mapping, default)
        if self.sort_dir == SortDirection.DESC:
            return query.order_by(column.desc())  # type: ignore[attr-defined]
        return query.order_by(column.asc())  # type: ignore[attr-defined]


class Message(BaseModel):
    message: str
    detail: str | None = None


class IdResponse(BaseModel):
    id: str
    message: str = "Created"


class DateRangeFilter:
    def __init__(
        self,
        date_from: date | None = Query(None, description="Inclusive start date"),
        date_to: date | None = Query(None, description="Inclusive end date"),
    ) -> None:
        self.date_from = date_from
        self.date_to = date_to


class TimeSeriesPoint(BaseModel):
    label: str
    value: float
    secondary: float | None = None


class NamedCount(BaseModel):
    label: str
    value: float
    meta: str | None = None


class DeletedFilter(str, Enum):
    EXCLUDE = "exclude"
    INCLUDE = "include"
    ONLY = "only"


__all__ = [
    "ORMModel",
    "Page",
    "PaginationParams",
    "SortDirection",
    "Message",
    "IdResponse",
    "DateRangeFilter",
    "TimeSeriesPoint",
    "NamedCount",
    "DeletedFilter",
    "Literal",
    "datetime",
]
