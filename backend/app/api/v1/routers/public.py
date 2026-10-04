"""Guest-facing public endpoints.

These endpoints deliberately require no authentication: they power the
visitor homepage that showcases the hotel's features and services. Only
public configuration, active room types and active services are exposed -
never operational data (occupancy, guest records, finances).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.operations import HotelSetting, Service
from app.db.models.property import RoomType
from app.db.session import get_db

router = APIRouter(prefix="/public", tags=["Public"])

PUBLIC_SETTING_KEYS = ("hotel_name", "hotel_tagline", "hotel_phone", "hotel_email", "hotel_address", "check_in_time", "check_out_time", "currency")


@router.get("/hotel")
def public_hotel_profile(db: Session = Depends(get_db)):
    settings = {s.key: s.value for s in db.scalars(select(HotelSetting).where(HotelSetting.key.in_(PUBLIC_SETTING_KEYS), HotelSetting.is_public.is_(True))).all()}
    room_types = db.scalars(select(RoomType).where(RoomType.deleted_at.is_(None), RoomType.is_active.is_(True)).order_by(RoomType.sort_order, RoomType.base_price)).all()
    services = db.scalars(select(Service).where(Service.deleted_at.is_(None), Service.is_active.is_(True)).order_by(Service.category, Service.name)).all()
    return {
        "hotel": {
            "name": settings.get("hotel_name", "Aurora Grand Hotel"),
            "tagline": settings.get("hotel_tagline", ""),
            "phone": settings.get("hotel_phone", ""),
            "email": settings.get("hotel_email", ""),
            "address": settings.get("hotel_address", ""),
            "check_in_time": settings.get("check_in_time", "15:00"),
            "check_out_time": settings.get("check_out_time", "11:00"),
            "currency": settings.get("currency", "USD"),
        },
        "room_types": [
            {
                "id": str(rt.id),
                "code": rt.code,
                "name": rt.name,
                "description": rt.description or "",
                "base_price": float(rt.base_price),
                "weekend_price": float(rt.weekend_price) if rt.weekend_price is not None else None,
                "size_sqm": rt.size_sqm,
                "max_occupancy": rt.max_occupancy,
                "bed_type": rt.bed_type.value,
                "amenities": sorted(a.name for a in rt.amenities if a.is_active),
            }
            for rt in room_types
        ],
        "services": [
            {
                "code": s.code,
                "name": s.name,
                "description": s.description or "",
                "category": s.category,
                "price": float(s.price),
                "unit": s.unit,
                "requires_scheduling": s.requires_scheduling,
            }
            for s in services
        ],
    }
