"""Operational dashboard endpoints backed by live database aggregates."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_permission
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.domain import DashboardOut
from app.services.dashboard import dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:view"))):
    return dashboard(db)


@router.get("/summary", response_model=DashboardOut)
def get_dashboard_summary(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:view"))):
    return dashboard(db)
