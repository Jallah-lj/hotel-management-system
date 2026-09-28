from __future__ import annotations


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_login_sets_secure_session_cookies(client, staff):
    response = client.post("/api/v1/auth/login", json={"email": "test@aurora.example", "password": "StrongTest!2026"})
    assert response.status_code == 200
    assert "hms_access" in response.cookies
    assert "hms_refresh" in response.cookies
    assert "hms_csrf" in response.cookies
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "testmanager"


def test_bad_password_does_not_disclose_account(client, staff):
    response = client.post("/api/v1/auth/login", json={"email": "test@aurora.example", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_authenticated_session_reaches_dashboard_and_logout_ends_it(client, staff):
    login = client.post("/api/v1/auth/login", json={"email": "test@aurora.example", "password": "StrongTest!2026"})
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert "stats" in dashboard.json()

    csrf = client.cookies.get("hms_csrf")
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf} if csrf else {})
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
