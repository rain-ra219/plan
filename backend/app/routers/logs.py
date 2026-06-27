from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..database import get_conn, row_to_dict

router = APIRouter()


@router.get("/api/task-logs")
def list_task_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM task_logs ORDER BY started_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]
