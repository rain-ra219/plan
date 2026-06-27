from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_core_console_routes_are_mounted(monkeypatch, temp_db):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    client = TestClient(app)

    paths = [
        "/api/health",
        "/api/dashboard",
        "/api/workflows",
        "/api/workflow-runs",
        "/api/upload-history",
        "/api/task-logs",
        "/api/task-queue",
        "/api/leads",
        "/api/customers",
    ]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
