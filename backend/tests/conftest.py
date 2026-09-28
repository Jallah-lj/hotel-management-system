from __future__ import annotations

import os
from pathlib import Path

# Tests default to an isolated SQLite database so they are runnable without a
# local service. CI can provide TEST_DATABASE_URL for full PostgreSQL coverage.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-jwt")
os.environ.setdefault("DATABASE_URL", os.getenv("TEST_DATABASE_URL", "sqlite:////tmp/aurora-grand-hms-test.sqlite3"))
os.environ.setdefault("CSRF_ENABLED", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.permissions import PERMISSIONS
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Permission, Role, User
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(database):
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client(database):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def staff(db):
    perms = [Permission(code=p.code, resource=p.resource, action=p.action, group_name=p.group, description=p.description) for p in PERMISSIONS]
    role = Role(code="test_manager", name="Test Manager", level=80, permissions=[p for p in perms if p.code in {"dashboard:view", "guests:view", "guests:create", "guests:update"}])
    user = User(email="test@aurora.example", username="testmanager", first_name="Test", last_name="Manager", password_hash=hash_password("StrongTest!2026"), roles=[role])
    db.add(user); db.commit(); db.refresh(user)
    return user
