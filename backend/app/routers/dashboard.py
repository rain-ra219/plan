from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..database import get_conn, now_iso, row_to_dict

router = APIRouter()


@router.get("/api/dashboard")
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
