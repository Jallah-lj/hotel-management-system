from __future__ import annotations

from fastapi.testclient import TestClient


def test_csrf_is_required_for_cookie_authenticated_writes(client, staff):
    login = client.post("/api/v1/auth/login", json={"email": "test@aurora.example", "password": "StrongTest!2026"})
    assert login.status_code == 200
    # No CSRF header: the request is stopped before it reaches a domain route.
    response = client.post("/api/v1/guests", json={"first_name": "No", "last_name": "Token"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_unknown_permission_is_forbidden(client, staff):
    client.post("/api/v1/auth/login", json={"email": "test@aurora.example", "password": "StrongTest!2026"})
    # The test role has the normal catalogue; this endpoint requires an admin
    # permission that the manager role does not possess.
    response = client.get("/api/v1/admin/audit-logs")
    assert response.status_code == 403
