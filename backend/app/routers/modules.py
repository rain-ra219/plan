from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import capability_dict, from_json, get_conn, module_manifest, now_iso
from ..tool_registry import list_tool_manifests

router = APIRouter()

class ModuleToggleRequest(BaseModel):
    enabled: bool

class ModuleConfigRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)

@router.get("/api/modules")
def list_modules() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM modules ORDER BY enabled DESC, name ASC").fetchall()
        return [module_manifest(row) for row in rows]

@router.patch("/api/modules/{module_id}")
def toggle_module(module_id: str, payload: ModuleToggleRequest) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模块不存在")
        status = "healthy" if payload.enabled else "disabled"
        if payload.enabled and module_requires_config(row) and missing_config_keys(conn, module_id):
            status = "needs_config"
        conn.execute(
            "UPDATE modules SET enabled = ?, status = ?, updated_at = ? WHERE id = ?",
            (int(payload.enabled), status, now_iso(), module_id),
        )
        conn.commit()
        return module_manifest(conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone())

@router.post("/api/modules/{module_id}/test")
def test_module(module_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模块不存在")
        if not row["enabled"]:
            status = "disabled"
            error = "模块已停用"
        else:
            missing = missing_config_keys(conn, module_id)
            if missing:
                status = "needs_config"
                error = f"缺少配置：{', '.join(missing)}"
            else:
                status = "healthy"
                error = None
        conn.execute(
            "UPDATE modules SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (status, error, now_iso(), module_id),
        )
        conn.commit()
        return {"moduleId": module_id, "status": status, "message": error or "连接检查通过"}

@router.get("/api/modules/{module_id}/config")
def get_module_config(module_id: str, reveal: bool = False) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模块不存在")
        manifest = from_json(row["manifest_json"], {})
        configs = conn.execute(
            "SELECT key, value, is_secret FROM module_configs WHERE module_id = ? ORDER BY key",
            (module_id,),
        ).fetchall()
        values = {}
        for item in configs:
            values[item["key"]] = "********" if item["is_secret"] and not reveal else item["value"]
        return {"module": module_manifest(row), "schema": manifest.get("configSchema", {}), "values": values}

@router.put("/api/modules/{module_id}/config")
def update_module_config(module_id: str, payload: ModuleConfigRequest) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模块不存在")
        manifest = from_json(row["manifest_json"], {})
        schema = manifest.get("configSchema", {})
        for key, value in payload.values.items():
            if key not in schema:
                continue
            if schema.get(key) == "secret" and value == "********":
                continue
            conn.execute(
                """
                INSERT INTO module_configs (module_id, key, value, is_secret, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id, key)
                DO UPDATE SET value = excluded.value, is_secret = excluded.is_secret, updated_at = excluded.updated_at
                """,
                (module_id, key, value, int(schema.get(key) == "secret"), now_iso(), now_iso()),
            )
        status = "healthy" if not missing_config_keys(conn, module_id) and row["enabled"] else row["status"]
        conn.execute("UPDATE modules SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), module_id))
        conn.commit()
        return get_module_config(module_id)

@router.get("/api/capabilities")
def list_capabilities() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM capabilities ORDER BY name ASC").fetchall()
        return [capability_dict(row) for row in rows]

@router.get("/api/tools")
def list_tools() -> list[dict[str, Any]]:
    return list_tool_manifests()

def module_requires_config(row: Any) -> bool:
    manifest = from_json(row["manifest_json"], {})
    return bool(manifest.get("configSchema"))

def missing_config_keys(conn: Any, module_id: str) -> list[str]:
    row = conn.execute("SELECT manifest_json FROM modules WHERE id = ?", (module_id,)).fetchone()
    if not row:
        return []
    schema = from_json(row["manifest_json"], {}).get("configSchema", {})
    if not schema:
        return []
    existing = {
        item["key"]: item["value"]
        for item in conn.execute("SELECT key, value FROM module_configs WHERE module_id = ?", (module_id,)).fetchall()
    }
    if module_id == "feishu-sync":
        env_fallbacks = {
            "appId": "FEISHU_APP_ID",
            "appSecret": "FEISHU_APP_SECRET",
            "appToken": "FEISHU_BITABLE_APP_TOKEN",
            "leadTableId": "FEISHU_BITABLE_TABLE_ID",
            "customerTableId": "FEISHU_CUSTOMER_TABLE_ID",
        }
        for key, env_name in env_fallbacks.items():
            existing.setdefault(key, os.getenv(env_name, ""))
    if module_id == "message-notifier":
        existing.setdefault("webhookUrl", os.getenv("MESSAGE_WEBHOOK_URL", ""))
    required = [key for key, kind in schema.items() if kind in ("string", "secret")]
    return [key for key in required if not existing.get(key)]
