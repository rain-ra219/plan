from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import get_conn, mcp_call_log_dict, mcp_mapping_dict, mcp_server_dict, now_iso, to_json
from ..mcp_client import McpClientError, call_tool as call_mcp_tool, discover_tools

router = APIRouter()

class McpServerRequest(BaseModel):
    name: str
    endpoint_url: str
    transport: str = "http"
    enabled: bool = True

class McpServerPatchRequest(BaseModel):
    name: str | None = None
    endpoint_url: str | None = None
    transport: str | None = None
    enabled: bool | None = None

class McpToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    capability: str = ""

class McpMappingRequest(BaseModel):
    server_id: str
    tool_name: str
    capability: str
    enabled: bool = True

@router.get("/api/mcp/servers")
def list_mcp_servers() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mcp_servers ORDER BY updated_at DESC").fetchall()
        return [mcp_server_dict(row) for row in rows]

@router.post("/api/mcp/servers")
def create_mcp_server(payload: McpServerRequest) -> dict[str, Any]:
    endpoint_url = payload.endpoint_url.strip()
    validate_mcp_endpoint(endpoint_url)
    if payload.transport != "http":
        raise HTTPException(status_code=400, detail="当前 Lite 版仅支持 HTTP MCP Server")
    server_id = f"mcp_{uuid.uuid4().hex[:10]}"
    current = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO mcp_servers (
                id, name, transport, endpoint_url, enabled, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'unknown', ?, ?)
            """,
            (server_id, payload.name.strip() or server_id, payload.transport, endpoint_url, int(payload.enabled), current, current),
        )
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        return mcp_server_dict(row)

@router.patch("/api/mcp/servers/{server_id}")
def patch_mcp_server(server_id: str, payload: McpServerPatchRequest) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP 服务不存在")
        name = row["name"] if payload.name is None else payload.name.strip()
        transport = row["transport"] if payload.transport is None else payload.transport
        endpoint_url = row["endpoint_url"] if payload.endpoint_url is None else payload.endpoint_url.strip()
        enabled = row["enabled"] if payload.enabled is None else int(payload.enabled)
        validate_mcp_endpoint(endpoint_url)
        if transport != "http":
            raise HTTPException(status_code=400, detail="当前 Lite 版仅支持 HTTP MCP Server")
        status = row["status"] if enabled else "disabled"
        conn.execute(
            """
            UPDATE mcp_servers
            SET name = ?, transport = ?, endpoint_url = ?, enabled = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (name or server_id, transport, endpoint_url, enabled, status, now_iso(), server_id),
        )
        return mcp_server_dict(conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone())

@router.delete("/api/mcp/servers/{server_id}")
def delete_mcp_server(server_id: str) -> dict[str, str]:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP 服务不存在")
        conn.execute("DELETE FROM mcp_tool_mappings WHERE server_id = ?", (server_id,))
        conn.execute("DELETE FROM mcp_call_logs WHERE server_id = ?", (server_id,))
        conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
        return {"status": "deleted"}

@router.post("/api/mcp/servers/{server_id}/discover")
def discover_mcp_server(server_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP 服务不存在")
        if not row["enabled"]:
            raise HTTPException(status_code=409, detail="MCP 服务已停用")
        try:
            tools = discover_tools(row["endpoint_url"])
            conn.execute(
                """
                UPDATE mcp_servers
                SET status = 'healthy', last_error = NULL, last_connected_at = ?, tools_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (now_iso(), to_json(tools), now_iso(), server_id),
            )
        except McpClientError as exc:
            conn.execute(
                "UPDATE mcp_servers SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
                (str(exc), now_iso(), server_id),
            )
            conn.commit()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return mcp_server_dict(conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone())

@router.post("/api/mcp/servers/{server_id}/call")
def call_mcp_server_tool(server_id: str, payload: McpToolCallRequest) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP 服务不存在")
        if not row["enabled"]:
            raise HTTPException(status_code=409, detail="MCP 服务已停用")
        started_at = now_iso()
        started = time.perf_counter()
        try:
            result = call_mcp_tool(row["endpoint_url"], payload.tool_name, payload.arguments)
            status = "success"
            error = None
        except McpClientError as exc:
            result = {}
            status = "failed"
            error = str(exc)
            conn.execute(
                "UPDATE mcp_servers SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
                (error, now_iso(), server_id),
            )
        ended_at = now_iso()
        duration_ms = int((time.perf_counter() - started) * 1000)
        conn.execute(
            """
            INSERT INTO mcp_call_logs (
                server_id, tool_name, capability, input_summary, output_summary,
                started_at, ended_at, duration_ms, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server_id,
                payload.tool_name,
                payload.capability or None,
                to_json({"arguments": payload.arguments}),
                to_json(result),
                started_at,
                ended_at,
                duration_ms,
                status,
                error,
            ),
        )
        if status == "failed":
            conn.commit()
            raise HTTPException(status_code=502, detail=error)
        return {"status": status, "duration_ms": duration_ms, "result": result}

@router.get("/api/mcp/mappings")
def list_mcp_mappings() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mcp_tool_mappings ORDER BY updated_at DESC").fetchall()
        return [mcp_mapping_dict(row) for row in rows]

@router.post("/api/mcp/mappings")
def upsert_mcp_mapping(payload: McpMappingRequest) -> dict[str, Any]:
    current = now_iso()
    with get_conn() as conn:
        server = conn.execute("SELECT id FROM mcp_servers WHERE id = ?", (payload.server_id,)).fetchone()
        if not server:
            raise HTTPException(status_code=404, detail="MCP 服务不存在")
        conn.execute(
            """
            INSERT INTO mcp_tool_mappings (
                server_id, tool_name, capability, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(server_id, tool_name, capability)
            DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at
            """,
            (
                payload.server_id,
                payload.tool_name.strip(),
                payload.capability.strip(),
                int(payload.enabled),
                current,
                current,
            ),
        )
        row = conn.execute(
            """
            SELECT * FROM mcp_tool_mappings
            WHERE server_id = ? AND tool_name = ? AND capability = ?
            """,
            (payload.server_id, payload.tool_name.strip(), payload.capability.strip()),
        ).fetchone()
        return mcp_mapping_dict(row)

@router.delete("/api/mcp/mappings/{mapping_id}")
def delete_mcp_mapping(mapping_id: int) -> dict[str, str]:
    with get_conn() as conn:
        conn.execute("DELETE FROM mcp_tool_mappings WHERE id = ?", (mapping_id,))
        return {"status": "deleted"}

@router.get("/api/mcp/call-logs")
def list_mcp_call_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mcp_call_logs ORDER BY started_at DESC LIMIT ?",
            (min(max(limit, 1), 300),),
        ).fetchall()
        return [mcp_call_log_dict(row) for row in rows]

def validate_mcp_endpoint(endpoint_url: str) -> None:
    if not endpoint_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="MCP endpoint 必须是 http:// 或 https:// 地址")
