from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

from .database import BEIJING_TZ, now_iso, task_queue_dict, to_json


PENDING = "pending"
RUNNING = "running"
SUCCESS = "success"
PARTIAL_SUCCESS = "partial_success"
FAILED = "failed"
SKIPPED = "skipped"
TERMINAL_STATUSES = {SUCCESS, PARTIAL_SUCCESS, FAILED, SKIPPED}
DEFAULT_TOTAL_CONCURRENCY = 5
DEFAULT_GROUP_LIMITS = {
    "image": 3,
    "csv": 2,
    "xhs": 2,
}
DEFAULT_WORKFLOW_GROUPS = {
    "product-main-image": "image",
    "product-main-detail": "image",
    "lead-import-to-feishu": "csv",
    "xhs-link-analysis": "xhs",
}


def enqueue_task(
    conn: Any,
    *,
    source: str,
    source_key: str,
    workflow_id: str,
    payload: dict[str, Any],
    listener_id: str = "",
    intake_run_id: str = "",
    remote_record_id: str = "",
    priority: int = 100,
    max_attempts: int = 1,
) -> dict[str, Any]:
    current = now_iso()
    task_id = f"queue_{uuid.uuid4().hex[:12]}"
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO task_queue (
            id, source, source_key, workflow_id, listener_id, intake_run_id,
            remote_record_id, payload_json, status, priority, max_attempts,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (
            task_id,
            source,
            source_key,
            workflow_id,
            listener_id or None,
            intake_run_id or None,
            remote_record_id or None,
            to_json(payload),
            priority,
            max(1, int(max_attempts)),
            current,
            current,
        ),
    )
    row = conn.execute("SELECT * FROM task_queue WHERE source_key = ?", (source_key,)).fetchone()
    result = task_queue_dict(row)
    result["created"] = cursor.rowcount == 1
    return result


def claim_next_task(conn: Any, *, source: str = "") -> dict[str, Any] | None:
    current = now_iso()
    params: list[Any] = [current, current, current]
    total_limit = queue_total_concurrency()
    group_limits = queue_group_limits()
    workflow_groups = queue_workflow_groups()

    source_filter = ""
    source_running_filter = ""
    if source:
        source_filter = "AND q.source = ?"
        source_running_filter = "AND r.source = ?"

    params.append(current)
    if source:
        params.append(source)

    params.extend(group_limit_params(group_limits, workflow_groups, source=source))
    if source:
        params.append(source)
    params.append(total_limit)

    row = conn.execute(
        f"""
        UPDATE task_queue
        SET status = 'running',
            attempt_count = attempt_count + 1,
            locked_at = ?,
            started_at = COALESCE(started_at, ?),
            updated_at = ?
        WHERE id = (
            SELECT q.id
            FROM task_queue q
            WHERE q.status = 'pending'
              AND (q.run_after IS NULL OR q.run_after <= ?)
              {source_filter}
              AND {group_limit_sql(group_limits, workflow_groups, source=source)}
              AND (
                  SELECT COUNT(*)
                  FROM task_queue r
                  WHERE r.status = 'running'
                  {source_running_filter}
              ) < ?
            ORDER BY q.priority ASC, q.created_at ASC
            LIMIT 1
        )
        RETURNING *
        """,
        params,
    ).fetchone()
    return task_queue_dict(row) if row else None


def complete_task(
    conn: Any,
    task_id: str,
    *,
    status: str,
    output: dict[str, Any] | None = None,
    workflow_run_id: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"invalid queue task status: {status}")
    current = now_iso()
    conn.execute(
        """
        UPDATE task_queue
        SET status = ?,
            output_summary = ?,
            workflow_run_id = ?,
            error_message = ?,
            ended_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            to_json(output or {}),
            workflow_run_id or None,
            error_message or None,
            current,
            current,
            task_id,
        ),
    )
    row = conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
    return task_queue_dict(row)


def retry_task(
    conn: Any,
    task_id: str,
    *,
    error_message: str,
    delay_seconds: int,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = now_iso()
    conn.execute(
        """
        UPDATE task_queue
        SET status = 'pending',
            output_summary = ?,
            error_message = ?,
            run_after = ?,
            locked_at = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (
            to_json(output or {}),
            error_message or None,
            retry_after(delay_seconds),
            current,
            task_id,
        ),
    )
    row = conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
    return task_queue_dict(row)


def list_task_queue(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM task_queue
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (min(max(limit, 1), 300),),
    ).fetchall()
    return [task_queue_dict(row) for row in rows]


def queue_total_concurrency() -> int:
    return env_int("TASK_QUEUE_TOTAL_CONCURRENCY", DEFAULT_TOTAL_CONCURRENCY, minimum=1, maximum=20)


def queue_group_limits() -> dict[str, int]:
    return {
        "image": env_int("TASK_QUEUE_IMAGE_CONCURRENCY", DEFAULT_GROUP_LIMITS["image"], minimum=1, maximum=20),
        "csv": env_int("TASK_QUEUE_CSV_CONCURRENCY", DEFAULT_GROUP_LIMITS["csv"], minimum=1, maximum=20),
        "xhs": env_int("TASK_QUEUE_XHS_CONCURRENCY", DEFAULT_GROUP_LIMITS["xhs"], minimum=1, maximum=20),
    }


def queue_workflow_groups() -> dict[str, str]:
    return DEFAULT_WORKFLOW_GROUPS.copy()


def queue_worker_count() -> int:
    return env_int("TASK_QUEUE_WORKERS", queue_total_concurrency(), minimum=1, maximum=20)


def retry_after(delay_seconds: int) -> str:
    return (datetime.now(BEIJING_TZ) + timedelta(seconds=max(delay_seconds, 1))).isoformat(timespec="seconds")


def retry_delay_seconds(attempt_count: int) -> int:
    return min(300, 30 * (2 ** max(attempt_count - 1, 0)))


def group_limit_sql(group_limits: dict[str, int], workflow_groups: dict[str, str], *, source: str = "") -> str:
    grouped = workflows_by_group(group_limits, workflow_groups)
    clauses: list[str] = []
    for group, workflows in grouped.items():
        placeholders = ", ".join("?" for _ in workflows)
        source_filter = "AND r.source = ?" if source else ""
        clauses.append(
            f"""
            (
                q.workflow_id IN ({placeholders})
                AND (
                    SELECT COUNT(*)
                    FROM task_queue r
                    WHERE r.status = 'running'
                      AND r.workflow_id IN ({placeholders})
                      {source_filter}
                ) < ?
            )
            """
        )
    if not clauses:
        return "1 = 1"
    all_workflows = [workflow for workflows in grouped.values() for workflow in workflows]
    other_placeholders = ", ".join("?" for _ in all_workflows)
    clauses.append(f"q.workflow_id NOT IN ({other_placeholders})")
    return "(" + " OR ".join(clauses) + ")"


def group_limit_params(group_limits: dict[str, int], workflow_groups: dict[str, str], *, source: str = "") -> list[Any]:
    grouped = workflows_by_group(group_limits, workflow_groups)
    params: list[Any] = []
    all_workflows: list[str] = []
    for group, workflows in grouped.items():
        params.extend(workflows)
        params.extend(workflows)
        if source:
            params.append(source)
        params.append(group_limits[group])
        all_workflows.extend(workflows)
    params.extend(all_workflows)
    return params


def workflows_by_group(group_limits: dict[str, int], workflow_groups: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for workflow_id, group in workflow_groups.items():
        if group not in group_limits:
            continue
        grouped.setdefault(group, []).append(workflow_id)
    return grouped


def env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(os.getenv(name, str(default))), maximum))
    except ValueError:
        return default
