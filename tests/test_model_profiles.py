from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import get_model_profile_config
from app.main import app


def test_model_profile_api_create_update_and_set_default(monkeypatch, temp_db) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    client = TestClient(app)

    created = client.post(
        "/api/model-profiles",
        json={
            "name": "DeepSeek",
            "purpose": "text",
            "baseUrl": "https://api.deepseek.com/chat/completions",
            "apiKey": "sk-test",
            "model": "deepseek-chat",
            "authMode": "bearer",
            "providerMode": "chat",
            "enabled": True,
            "isDefault": False,
        },
    )
    assert created.status_code == 200
    profile_id = created.json()["id"]
    assert created.json()["apiKey"] == "********"

    updated = client.patch(
        f"/api/model-profiles/{profile_id}",
        json={"name": "DeepSeek Text", "apiKey": "********"},
    )
    assert updated.status_code == 200

    defaulted = client.post(f"/api/model-profiles/{profile_id}/set-default")
    assert defaulted.status_code == 200
    assert defaulted.json()["isDefault"] is True

    revealed = client.get("/api/model-profiles?reveal=1")
    assert revealed.status_code == 200
    assert revealed.json()[0]["apiKey"] == "sk-test"


def test_get_model_profile_config_prefers_purpose_then_default(temp_db) -> None:
    with temp_db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO model_profiles (
                id, name, purpose, base_url, api_key, model, auth_mode, provider_mode,
                enabled, is_default, created_at, updated_at
            ) VALUES
            ('model_default', 'Default', 'default', 'https://default.example/v1/chat/completions', 'default-key', 'default-model', 'bearer', 'chat', 1, 1, '2026-01-01T00:00:00', '2026-01-01T00:00:00'),
            ('model_text', 'Text', 'text', 'https://text.example/v1/chat/completions', 'text-key', 'text-model', 'bearer', 'chat', 1, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:01')
            """
        )

        text_config = get_model_profile_config(conn, "text")
        vision_config = get_model_profile_config(conn, "vision")

    assert text_config["model"] == "text-model"
    assert text_config["apiKey"] == "text-key"
    assert vision_config["model"] == "default-model"
