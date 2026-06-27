from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import feishu_base_dict, feishu_table_dict, get_conn, now_iso

router = APIRouter()

class FeishuBaseRequest(BaseModel):
    name: str
    app_token: str
    description: str = ""
    enabled: bool = True

class FeishuTableRequest(BaseModel):
    base_id: str
    name: str
    table_id: str
    purpose: str = ""

@router.get("/api/feishu/bases")
def list_feishu_bases() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM feishu_bases ORDER BY updated_at DESC").fetchall()
        return [feishu_base_dict(row) for row in rows]

@router.post("/api/feishu/bases")
def create_feishu_base(payload: FeishuBaseRequest) -> dict[str, Any]:
    if not payload.name.strip() or not payload.app_token.strip():
        raise HTTPException(status_code=400, detail="请填写 Base 名称和 appToken")
    base_id = f"base_{uuid.uuid4().hex[:10]}"
    current = now_iso()
    with get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO feishu_bases (
                    id, name, app_token, description, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    base_id,
                    payload.name.strip(),
                    payload.app_token.strip(),
                    payload.description.strip(),
                    int(payload.enabled),
                    current,
                    current,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="该 appToken 已经存在") from exc
        return feishu_base_dict(conn.execute("SELECT * FROM feishu_bases WHERE id = ?", (base_id,)).fetchone())

@router.patch("/api/feishu/bases/{base_id}")
def patch_feishu_base(base_id: str, payload: FeishuBaseRequest) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM feishu_bases WHERE id = ?", (base_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="飞书 Base 不存在")
        try:
            conn.execute(
                """
                UPDATE feishu_bases
                SET name = ?, app_token = ?, description = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name.strip(),
                    payload.app_token.strip(),
                    payload.description.strip(),
                    int(payload.enabled),
                    now_iso(),
                    base_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="该 appToken 已经存在") from exc
        return feishu_base_dict(conn.execute("SELECT * FROM feishu_bases WHERE id = ?", (base_id,)).fetchone())

@router.delete("/api/feishu/bases/{base_id}")
def delete_feishu_base(base_id: str) -> dict[str, str]:
    with get_conn() as conn:
        linked = conn.execute("SELECT COUNT(*) AS count FROM feishu_tables WHERE base_id = ?", (base_id,)).fetchone()
        if linked["count"]:
            raise HTTPException(status_code=409, detail="请先删除该 Base 下的飞书表配置")
        conn.execute("DELETE FROM feishu_bases WHERE id = ?", (base_id,))
        return {"status": "deleted"}

@router.get("/api/feishu/tables")
def list_feishu_tables() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.*, b.name AS base_name, b.app_token
            FROM feishu_tables t
            LEFT JOIN feishu_bases b ON b.id = t.base_id
            ORDER BY t.updated_at DESC
            """
        ).fetchall()
        return [feishu_table_dict(row) for row in rows]

@router.post("/api/feishu/tables")
def create_feishu_table(payload: FeishuTableRequest) -> dict[str, Any]:
    if not payload.base_id or not payload.name.strip() or not payload.table_id.strip():
        raise HTTPException(status_code=400, detail="请填写 Base、表名和 tableId")
    table_config_id = f"tblcfg_{uuid.uuid4().hex[:10]}"
    current = now_iso()
    with get_conn() as conn:
        base = conn.execute("SELECT id FROM feishu_bases WHERE id = ?", (payload.base_id,)).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="飞书 Base 不存在")
        try:
            conn.execute(
                """
                INSERT INTO feishu_tables (
                    id, base_id, name, table_id, purpose, field_mapping_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    table_config_id,
                    payload.base_id,
                    payload.name.strip(),
                    payload.table_id.strip(),
                    payload.purpose.strip(),
                    current,
                    current,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="该 Base 下已经存在这个 tableId") from exc
        row = conn.execute(
            """
            SELECT t.*, b.name AS base_name, b.app_token
            FROM feishu_tables t
            LEFT JOIN feishu_bases b ON b.id = t.base_id
            WHERE t.id = ?
            """,
            (table_config_id,),
        ).fetchone()
        return feishu_table_dict(row)

@router.delete("/api/feishu/tables/{table_config_id}")
def delete_feishu_table(table_config_id: str) -> dict[str, str]:
    with get_conn() as conn:
        linked = conn.execute(
            "SELECT COUNT(*) AS count FROM intake_listener_state WHERE table_config_id = ?",
            (table_config_id,),
        ).fetchone()
        if linked["count"]:
            raise HTTPException(status_code=409, detail="请先删除或改绑使用该表的监听器")
        conn.execute("DELETE FROM feishu_tables WHERE id = ?", (table_config_id,))
        return {"status": "deleted"}
