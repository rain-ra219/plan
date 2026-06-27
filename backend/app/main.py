from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import (
    from_json,
    get_conn,
    init_db,
    now_iso,
    row_to_dict,
    workflow_dict,
)
from .routers.feishu import router as feishu_router
from .routers.intake import router as intake_router
from .routers.mcp import router as mcp_router
from .routers.modules import router as modules_router
from .routers.product import router as product_router
from .task_queue import list_task_queue
from .workflow_registry import WorkflowRegistryError, run_workflow
from tools.feishu_intake.listener import start_intake_worker

LEAD_IMPORT_WORKFLOW_ID = "lead-import-to-feishu"
app = FastAPI(title="AI 自动化控制台 Lite", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(modules_router)
app.include_router(feishu_router)
app.include_router(mcp_router)
app.include_router(product_router)
app.include_router(intake_router)

class CsvWorkflowRequest(BaseModel):
    filename: str = "leads.csv"
    content: str
    submitted_by: str = ""
    note: str = ""
    submission_channel: str = "admin-upload"

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

@app.get("/api/workflows")
def list_workflows() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY name ASC").fetchall()
        return [workflow_dict(row) for row in rows]

@app.post("/api/workflows/lead-import/run")
def run_lead_import_endpoint(payload: CsvWorkflowRequest) -> dict[str, Any]:
    with get_conn() as conn:
        workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", (LEAD_IMPORT_WORKFLOW_ID,)).fetchone()
        if not workflow or not workflow["enabled"]:
            raise HTTPException(status_code=409, detail="工作流未启用")
        try:
            return run_workflow(
                conn,
                LEAD_IMPORT_WORKFLOW_ID,
                payload.filename,
                payload.content,
                submitted_by=payload.submitted_by,
                note=payload.note,
                submission_channel=payload.submission_channel,
            )
        except WorkflowRegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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

@app.get("/api/task-queue")
def get_task_queue(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list_task_queue(conn, limit)

@app.get("/api/upload-history")
def list_upload_history(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        runs = conn.execute(
            "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?",
            (LEAD_IMPORT_WORKFLOW_ID, min(max(limit, 1), 200)),
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
