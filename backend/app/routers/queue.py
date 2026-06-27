from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..database import get_conn
from ..task_queue import list_task_queue

router = APIRouter()


@router.get("/api/task-queue")
def get_task_queue(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list_task_queue(conn, limit)
