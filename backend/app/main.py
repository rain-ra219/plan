from __future__ import annotations

import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import (
    capability_dict,
    from_json,
    get_conn,
    init_db,
    mcp_call_log_dict,
    mcp_mapping_dict,
    mcp_server_dict,
    module_manifest,
    now_iso,
    row_to_dict,
    to_json,
    workflow_dict,
)
from .mcp_client import McpClientError, call_tool as call_mcp_tool, discover_tools
from tools.feishu_intake.listener import (
    list_intake_runs,
    listener_state,
    scan_intake_once,
    start_intake_worker,
    update_listener_state,
)
from .tool_registry import list_tool_manifests
from tools.lead_import.workflow import WORKFLOW_ID, run_lead_import


app = FastAPI(title="AI 自动化控制台 Lite", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModuleToggleRequest(BaseModel):
    enabled: bool


class ModuleConfigRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class CsvWorkflowRequest(BaseModel):
    filename: str = "leads.csv"
    content: str
    submitted_by: str = ""
    note: str = ""
    submission_channel: str = "admin-upload"


class IntakeListenerRequest(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None


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


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    start_intake_worker()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with get_conn() as conn:
        today = now_iso()[:10]
        run_counts = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status = 'partial_success' THEN 1 ELSE 0 END) AS partial_success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                AVG(duration_ms) AS avg_duration
            FROM workflow_runs
            WHERE started_at LIKE ?
            """,
            (f"{today}%",),
        ).fetchone()
        abnormal_modules = conn.execute(
            """
            SELECT id, name, status, enabled, last_error
            FROM modules
            WHERE enabled = 0 OR status NOT IN ('healthy')
            ORDER BY enabled ASC, name ASC
            """
        ).fetchall()
        recent_runs = conn.execute("SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT 5").fetchall()
        recent_logs = conn.execute("SELECT * FROM task_logs ORDER BY started_at DESC LIMIT 6").fetchall()
        return {
            "todayTasks": run_counts["total"] or 0,
            "todaySuccess": run_counts["success"] or 0,
            "todayPartialSuccess": run_counts["partial_success"] or 0,
            "todayFailed": run_counts["failed"] or 0,
            "avgDurationMs": int(run_counts["avg_duration"] or 0),
            "abnormalModules": [row_to_dict(row) for row in abnormal_modules],
            "recentRuns": [row_to_dict(row) for row in recent_runs],
            "recentLogs": [row_to_dict(row) for row in recent_logs],
        }


@app.get("/api/modules")
def list_modules() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM modules ORDER BY enabled DESC, name ASC").fetchall()
        return [module_manifest(row) for row in rows]


@app.patch("/api/modules/{module_id}")
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


@app.post("/api/modules/{module_id}/test")
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


@app.get("/api/modules/{module_id}/config")
def get_module_config(module_id: str) -> dict[str, Any]:
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
            values[item["key"]] = "********" if item["is_secret"] else item["value"]
        return {"module": module_manifest(row), "schema": manifest.get("configSchema", {}), "values": values}


@app.put("/api/modules/{module_id}/config")
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


@app.get("/api/capabilities")
def list_capabilities() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM capabilities ORDER BY name ASC").fetchall()
        return [capability_dict(row) for row in rows]


@app.get("/api/tools")
def list_tools() -> list[dict[str, Any]]:
    return list_tool_manifests()


@app.get("/api/mcp/servers")
def list_mcp_servers() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mcp_servers ORDER BY updated_at DESC").fetchall()
        return [mcp_server_dict(row) for row in rows]


@app.post("/api/mcp/servers")
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


@app.patch("/api/mcp/servers/{server_id}")
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


@app.delete("/api/mcp/servers/{server_id}")
def delete_mcp_server(server_id: str) -> dict[str, str]:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP 服务不存在")
        conn.execute("DELETE FROM mcp_tool_mappings WHERE server_id = ?", (server_id,))
        conn.execute("DELETE FROM mcp_call_logs WHERE server_id = ?", (server_id,))
        conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
        return {"status": "deleted"}


@app.post("/api/mcp/servers/{server_id}/discover")
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


@app.post("/api/mcp/servers/{server_id}/call")
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


@app.get("/api/mcp/mappings")
def list_mcp_mappings() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mcp_tool_mappings ORDER BY updated_at DESC").fetchall()
        return [mcp_mapping_dict(row) for row in rows]


@app.post("/api/mcp/mappings")
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


@app.delete("/api/mcp/mappings/{mapping_id}")
def delete_mcp_mapping(mapping_id: int) -> dict[str, str]:
    with get_conn() as conn:
        conn.execute("DELETE FROM mcp_tool_mappings WHERE id = ?", (mapping_id,))
        return {"status": "deleted"}


@app.get("/api/mcp/call-logs")
def list_mcp_call_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mcp_call_logs ORDER BY started_at DESC LIMIT ?",
            (min(max(limit, 1), 300),),
        ).fetchall()
        return [mcp_call_log_dict(row) for row in rows]


@app.get("/api/workflows")
def list_workflows() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY name ASC").fetchall()
        return [workflow_dict(row) for row in rows]


@app.get("/api/intake/listener")
def get_intake_listener() -> dict[str, Any]:
    with get_conn() as conn:
        return listener_state(conn)


@app.patch("/api/intake/listener")
def patch_intake_listener(payload: IntakeListenerRequest) -> dict[str, Any]:
    with get_conn() as conn:
        return update_listener_state(conn, enabled=payload.enabled, interval_seconds=payload.interval_seconds)


@app.post("/api/intake/scan")
def scan_intake() -> dict[str, Any]:
    return scan_intake_once(trigger_type="manual", limit=10)


@app.get("/api/intake/runs")
def get_intake_runs(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list_intake_runs(conn, limit)


@app.post("/api/workflows/lead-import/run")
def run_lead_import_endpoint(payload: CsvWorkflowRequest) -> dict[str, Any]:
    with get_conn() as conn:
        workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", ("lead-import-to-feishu",)).fetchone()
        if not workflow or not workflow["enabled"]:
            raise HTTPException(status_code=409, detail="工作流未启用")
        try:
            return run_lead_import(
                conn,
                payload.filename,
                payload.content,
                submitted_by=payload.submitted_by,
                note=payload.note,
                submission_channel=payload.submission_channel,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/workflow-runs")
def list_workflow_runs(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?",
            (min(max(limit, 1), 200),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/task-logs")
def list_task_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM task_logs ORDER BY started_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/upload-history")
def list_upload_history(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        runs = conn.execute(
            "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?",
            (WORKFLOW_ID, min(max(limit, 1), 200)),
        ).fetchall()
        history = []
        for run in runs:
            output = from_json(run["output_summary"], {})
            input_summary = from_json(run["input_summary"], {})
            step_logs = conn.execute(
                """
                SELECT module_id, capability, input_summary, output_summary, status, error_message, duration_ms
                FROM task_logs
                WHERE workflow_run_id = ?
                ORDER BY id ASC
                """,
                (run["id"],),
            ).fetchall()
            file_log = first_log(step_logs, "file.upload")
            lead_log = first_log(step_logs, "lead.normalize")
            customer_log = first_log(step_logs, "customer.merge")
            file_input = from_json(file_log["input_summary"], {}) if file_log else {}
            file_output = from_json(file_log["output_summary"], {}) if file_log else {}
            lead_input = from_json(lead_log["input_summary"], {}) if lead_log else {}
            lead_output = from_json(lead_log["output_summary"], {}) if lead_log else {}
            customer_output = from_json(customer_log["output_summary"], {}) if customer_log else {}
            file_id = output.get("file_id") or file_output.get("file_id")
            file_row = None
            if file_id:
                file_row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
            table_logs = [row for row in step_logs if row["capability"] == "table.write"]
            history.append(
                {
                    "workflow_run_id": run["id"],
                    "workflow_id": run["workflow_id"],
                    "status": run["status"],
                    "started_at": run["started_at"],
                    "ended_at": run["ended_at"],
                    "duration_ms": run["duration_ms"],
                    "submitted_by": input_summary.get("submitted_by", ""),
                    "note": input_summary.get("note", ""),
                    "submission_channel": input_summary.get("submission_channel", ""),
                    "filename": file_row["filename"] if file_row else file_input.get("filename", input_summary.get("filename", "")),
                    "file_id": file_id,
                    "size_bytes": file_row["size_bytes"] if file_row else file_input.get("bytes", input_summary.get("bytes", 0)),
                    "rows": output.get("rows") or lead_input.get("rows", 0),
                    "lead_count": output.get("leads", {}).get("affected_count") or lead_output.get("affected_count", 0),
                    "customer_count": output.get("customers", {}).get("affected_count") or customer_output.get("affected_count", 0),
                    "tables": [table_history_dict(row) for row in table_logs],
                    "error_message": run["error_message"],
                }
            )
        return history


@app.get("/api/leads")
def list_leads(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY updated_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/customers")
def list_customers(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM customers ORDER BY updated_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


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


def validate_mcp_endpoint(endpoint_url: str) -> None:
    if not endpoint_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="MCP endpoint 必须是 http:// 或 https:// 地址")


def table_history_dict(row: Any) -> dict[str, Any]:
    input_summary = from_json(row["input_summary"], {})
    output_summary = from_json(row["output_summary"], {})
    return {
        "module_id": row["module_id"],
        "capability": row["capability"],
        "target": output_summary.get("target") or input_summary.get("target", ""),
        "rows": output_summary.get("rows", input_summary.get("rows", 0)),
        "status": row["status"],
        "duration_ms": row["duration_ms"],
        "error_message": row["error_message"] or output_summary.get("reason"),
        "created": output_summary.get("created"),
        "updated": output_summary.get("updated"),
        "unmapped_created": output_summary.get("unmapped_created"),
    }


def first_log(rows: list[Any], capability: str) -> Any | None:
    for row in rows:
        if row["capability"] == capability:
            return row
    return None
