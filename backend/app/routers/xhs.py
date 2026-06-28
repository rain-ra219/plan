from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_conn, now_iso
from ..workflow_registry import WorkflowRegistryError, run_workflow
from tools.xhs_weekly_report.workflow import NOTE_ANALYSIS_SYSTEM, REPORT_SYSTEM


XHS_WEEKLY_REPORT_WORKFLOW_ID = "xhs-weekly-report"

router = APIRouter()


class XhsWeeklyReportRequest(BaseModel):
    keyword: str = ""
    max_notes: int | None = None
    sort_type: str = "comment_descending"
    time_filter: str = "一周内"
    note_type: str = "不限"


class XhsPromptsRequest(BaseModel):
    noteAnalysisSystemPrompt: str = ""
    reportSystemPrompt: str = ""


@router.get("/api/xhs/prompts")
def get_xhs_prompts() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT key, value
            FROM module_configs
            WHERE module_id = ? AND key IN (?, ?)
            """,
            (XHS_WEEKLY_REPORT_WORKFLOW_ID, "noteAnalysisSystemPrompt", "reportSystemPrompt"),
        ).fetchall()
        values = {row["key"]: row["value"] for row in rows}
        return {
            "noteAnalysisSystemPrompt": values.get("noteAnalysisSystemPrompt") or NOTE_ANALYSIS_SYSTEM,
            "reportSystemPrompt": values.get("reportSystemPrompt") or REPORT_SYSTEM,
        }


@router.put("/api/xhs/prompts")
def update_xhs_prompts(payload: XhsPromptsRequest) -> dict[str, str]:
    current = now_iso()
    with get_conn() as conn:
        module = conn.execute("SELECT id FROM modules WHERE id = ?", (XHS_WEEKLY_REPORT_WORKFLOW_ID,)).fetchone()
        if not module:
            raise HTTPException(status_code=404, detail="TikHub module not found")
        values = {
            "noteAnalysisSystemPrompt": payload.noteAnalysisSystemPrompt,
            "reportSystemPrompt": payload.reportSystemPrompt,
        }
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO module_configs (module_id, key, value, is_secret, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                ON CONFLICT(module_id, key)
                DO UPDATE SET value = excluded.value, is_secret = 0, updated_at = excluded.updated_at
                """,
                (XHS_WEEKLY_REPORT_WORKFLOW_ID, key, value, current, current),
            )
        conn.commit()
        return values


@router.post("/api/xhs-weekly-report/run")
def run_xhs_weekly_report_endpoint(payload: XhsWeeklyReportRequest) -> dict[str, Any]:
    with get_conn() as conn:
        workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", (XHS_WEEKLY_REPORT_WORKFLOW_ID,)).fetchone()
        if not workflow or not workflow["enabled"]:
            raise HTTPException(status_code=409, detail="工作流未启用")
        try:
            return run_workflow(
                conn,
                XHS_WEEKLY_REPORT_WORKFLOW_ID,
                keyword=payload.keyword,
                max_notes=payload.max_notes,
                sort_type=payload.sort_type,
                time_filter=payload.time_filter,
                note_type=payload.note_type,
            )
        except WorkflowRegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
