from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import get_conn, model_profile_dict, now_iso

router = APIRouter()


class ModelProfilePayload(BaseModel):
    name: str = Field(default="新模型")
    purpose: str = Field(default="default")
    baseUrl: str = Field(default="")
    apiKey: str = Field(default="")
    model: str = Field(default="")
    authMode: str = Field(default="bearer")
    providerMode: str = Field(default="chat")
    enabled: bool = True
    isDefault: bool = False


class ModelProfilePatch(BaseModel):
    name: str | None = None
    purpose: str | None = None
    baseUrl: str | None = None
    apiKey: str | None = None
    model: str | None = None
    authMode: str | None = None
    providerMode: str | None = None
    enabled: bool | None = None
    isDefault: bool | None = None


@router.get("/api/model-profiles")
def list_model_profiles(reveal: bool = False) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM model_profiles ORDER BY is_default DESC, enabled DESC, purpose ASC, name ASC"
        ).fetchall()
        return [model_profile_dict(row, reveal=reveal) for row in rows]


@router.post("/api/model-profiles")
def create_model_profile(payload: ModelProfilePayload) -> dict[str, Any]:
    current = now_iso()
    profile_id = f"model_{uuid.uuid4().hex[:12]}"
    with get_conn() as conn:
        if payload.isDefault:
            conn.execute("UPDATE model_profiles SET is_default = 0, updated_at = ?", (current,))
        conn.execute(
            """
            INSERT INTO model_profiles (
                id, name, purpose, base_url, api_key, model, auth_mode, provider_mode,
                enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                normalize_text(payload.name, "新模型"),
                normalize_text(payload.purpose, "default"),
                payload.baseUrl.strip(),
                normalize_secret(payload.apiKey),
                payload.model.strip(),
                normalize_text(payload.authMode, "bearer"),
                normalize_text(payload.providerMode, "chat"),
                int(payload.enabled),
                int(payload.isDefault),
                current,
                current,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        return model_profile_dict(row, reveal=False)


@router.patch("/api/model-profiles/{profile_id}")
def update_model_profile(profile_id: str, payload: ModelProfilePatch) -> dict[str, Any]:
    current = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在")

        values = {
            "name": normalize_text(payload.name, row["name"]) if payload.name is not None else row["name"],
            "purpose": normalize_text(payload.purpose, row["purpose"]) if payload.purpose is not None else row["purpose"],
            "base_url": payload.baseUrl.strip() if payload.baseUrl is not None else row["base_url"],
            "api_key": normalize_updated_secret(payload.apiKey, row["api_key"]) if payload.apiKey is not None else row["api_key"],
            "model": payload.model.strip() if payload.model is not None else row["model"],
            "auth_mode": normalize_text(payload.authMode, row["auth_mode"]) if payload.authMode is not None else row["auth_mode"],
            "provider_mode": normalize_text(payload.providerMode, row["provider_mode"]) if payload.providerMode is not None else row["provider_mode"],
            "enabled": int(payload.enabled) if payload.enabled is not None else row["enabled"],
            "is_default": int(payload.isDefault) if payload.isDefault is not None else row["is_default"],
        }
        if payload.isDefault:
            conn.execute("UPDATE model_profiles SET is_default = 0, updated_at = ? WHERE id != ?", (current, profile_id))
        conn.execute(
            """
            UPDATE model_profiles
            SET name = ?, purpose = ?, base_url = ?, api_key = ?, model = ?,
                auth_mode = ?, provider_mode = ?, enabled = ?, is_default = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                values["name"],
                values["purpose"],
                values["base_url"],
                values["api_key"],
                values["model"],
                values["auth_mode"],
                values["provider_mode"],
                values["enabled"],
                values["is_default"],
                current,
                profile_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        return model_profile_dict(row, reveal=False)


@router.post("/api/model-profiles/{profile_id}/set-default")
def set_default_model_profile(profile_id: str) -> dict[str, Any]:
    current = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        conn.execute("UPDATE model_profiles SET is_default = 0, updated_at = ?", (current,))
        conn.execute(
            "UPDATE model_profiles SET is_default = 1, enabled = 1, updated_at = ? WHERE id = ?",
            (current, profile_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        return model_profile_dict(row, reveal=False)


@router.delete("/api/model-profiles/{profile_id}")
def delete_model_profile(profile_id: str) -> dict[str, str]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        conn.execute("DELETE FROM model_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return {"status": "deleted", "id": profile_id}


def normalize_text(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def normalize_secret(value: str | None) -> str:
    text = str(value or "").strip()
    return "" if text == "********" else text


def normalize_updated_secret(value: str | None, current: str) -> str:
    text = str(value or "").strip()
    return current if text == "********" else text
