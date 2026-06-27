from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_admin_auth_disabled_without_token(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    client = TestClient(app)

    response = client.get("/api/dashboard")

    assert response.status_code == 200


def test_admin_auth_blocks_api_without_matching_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/dashboard")

    assert response.status_code == 401


def test_admin_auth_accepts_x_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/dashboard", headers={"X-Admin-Token": "secret-token"})

    assert response.status_code == 200


def test_admin_auth_keeps_healthcheck_public(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
