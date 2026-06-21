from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import (
    capability_dict,
    from_json,
    get_conn,
    init_db,
    module_manifest,
    now_iso,
    row_to_dict,
    to_json,
    workflow_dict,
)
from .lead_workflow import WORKFLOW_ID, run_lead_import


app = FastAPI(title="AI 自动化后台平台", version="0.1.0")
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


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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


@app.get("/api/workflows")
def list_workflows() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY name ASC").fetchall()
        return [workflow_dict(row) for row in rows]


@app.post("/api/workflows/lead-import/run")
def run_lead_import_endpoint(payload: CsvWorkflowRequest) -> dict[str, Any]:
    with get_conn() as conn:
        workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", ("lead-import-to-feishu",)).fetchone()
        if not workflow or not workflow["enabled"]:
            raise HTTPException(status_code=409, detail="工作流未启用")
        try:
            return run_lead_import(conn, payload.filename, payload.content)
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
    required = [key for key, kind in schema.items() if kind in ("string", "secret")]
    return [key for key in required if not existing.get(key)]


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
