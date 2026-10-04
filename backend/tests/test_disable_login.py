"""Behaviour of the DISABLE_LOGIN testing mode.

When the platform is being tested the login screen must disappear entirely:
the UI reads ``/auth/config`` and then opens the seeded workspace through
``/auth/demo-login`` without credentials. Both routes stay locked down when
the flag is off.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Role, User


@pytest.fixture
def disable_login(monkeypatch):
    monkeypatch.setattr(settings, "disable_login", True)
    monkeypatch.setattr(settings, "demo_mode", False)
    yield


@pytest.fixture
def seeded_admin(db):
    role = Role(code="test_admin", name="Test Admin", level=90)
    user = User(
        email=settings.demo_user_email,
        username="demoadmin",
        first_name="Avery",
        last_name="Quinn",
        password_hash=hash_password(settings.demo_user_password),
        is_superuser=True,
        roles=[role],
    )
    db.add(user)
    db.commit()
    return user


def test_auth_config_reports_login_enabled_by_default(client):
    response = client.get("/api/v1/auth/config")
    assert response.status_code == 200
    assert response.json() == {"login_disabled": False}


def test_demo_login_is_unavailable_when_login_is_enabled(client, seeded_admin):
    response = client.post("/api/v1/auth/demo-login")
    assert response.status_code == 404


def test_disable_login_authenticates_protected_routes_without_credentials(client, disable_login, seeded_admin):
    """No cookies, no tokens: every protected endpoint just works."""
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == settings.demo_user_email
    assert client.get("/api/v1/dashboard").status_code == 200
    assert client.get("/api/v1/reservations").status_code == 200


def test_protected_routes_still_require_credentials_by_default(client, staff):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/dashboard").status_code == 401


def test_disable_login_provisions_missing_demo_account(client, disable_login):
    """A fresh/unseeded database must still open the workspace, not 401."""
    demo = client.post("/api/v1/auth/demo-login")
    assert demo.status_code == 200
    assert demo.json()["user"]["email"] == settings.demo_user_email

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["is_superuser"] is True

    # The provisioned account can use the whole workspace.
    assert client.get("/api/v1/dashboard").status_code == 200


def test_disable_login_opens_workspace_without_credentials(client, disable_login, seeded_admin):
    config = client.get("/api/v1/auth/config")
    assert config.status_code == 200
    assert config.json() == {"login_disabled": True}

    demo = client.post("/api/v1/auth/demo-login")
    assert demo.status_code == 200
    body = demo.json()
    assert body["user"]["email"] == settings.demo_user_email
    assert "hms_access" in demo.cookies

    # The automatic session must be immediately usable.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == settings.demo_user_email
