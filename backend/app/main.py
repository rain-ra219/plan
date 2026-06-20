from __future__ import annotations

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
from .lead_workflow import run_lead_import


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
    required = [key for key, kind in schema.items() if kind in ("string", "secret")]
    return [key for key in required if not existing.get(key)]
