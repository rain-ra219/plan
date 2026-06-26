from __future__ import annotations

from collections import Counter

from app import task_queue


def enqueue(conn, source_key: str, workflow_id: str = "product-main-image"):
    return task_queue.enqueue_task(
        conn,
        source="feishu",
        source_key=source_key,
        workflow_id=workflow_id,
        payload={"source_key": source_key},
        max_attempts=3,
    )


def test_enqueue_deduplicates_active_source_key(temp_db):
    with temp_db.get_conn() as conn:
        first = enqueue(conn, "feishu:record-1")
        second = enqueue(conn, "feishu:record-1")

    assert first["created"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert second["status"] == task_queue.PENDING


def test_claim_next_task_marks_running_and_increments_attempt(temp_db):
    with temp_db.get_conn() as conn:
        queued = enqueue(conn, "feishu:record-2")
        claimed = task_queue.claim_next_task(conn)

    assert claimed is not None
    assert claimed["id"] == queued["id"]
    assert claimed["status"] == task_queue.RUNNING
    assert claimed["attempt_count"] == 1
    assert claimed["locked_at"]
    assert claimed["started_at"]


def test_claim_next_task_respects_total_and_group_concurrency(temp_db, monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_TOTAL_CONCURRENCY", "5")
    monkeypatch.setenv("TASK_QUEUE_IMAGE_CONCURRENCY", "3")
    monkeypatch.setenv("TASK_QUEUE_CSV_CONCURRENCY", "2")

    with temp_db.get_conn() as conn:
        for index in range(4):
            enqueue(conn, f"feishu:image-{index}", "product-main-image")
        for index in range(3):
            enqueue(conn, f"feishu:csv-{index}", "lead-import-to-feishu")

        claimed = [task_queue.claim_next_task(conn) for _ in range(7)]

    claimed_tasks = [item for item in claimed if item]
    counts = Counter(item["workflow_id"] for item in claimed_tasks)

    assert len(claimed_tasks) == 5
    assert counts["product-main-image"] == 3
    assert counts["lead-import-to-feishu"] == 2
    assert claimed[-1] is None


def test_retry_task_returns_to_pending_with_backoff(temp_db):
    with temp_db.get_conn() as conn:
        queued = enqueue(conn, "feishu:record-3")
        claimed = task_queue.claim_next_task(conn)
        retried = task_queue.retry_task(
            conn,
            claimed["id"],
            error_message="Image API HTTP 504",
            delay_seconds=60,
            output={"temporary": True},
        )

    assert retried["id"] == queued["id"]
    assert retried["status"] == task_queue.PENDING
    assert retried["attempt_count"] == 1
    assert retried["run_after"]
    assert retried["error_message"] == "Image API HTTP 504"
    assert retried["output"] == {"temporary": True}
