from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import from_json, get_conn, now_iso, row_to_dict, to_json
from .feishu_client import FeishuApiError, FeishuClient
from .lead_workflow import WORKFLOW_ID, elapsed_ms, get_module_config, run_lead_import, summarize


LISTENER_ID = "feishu-form-csv"
DEFAULT_PENDING_STATUS = "待处理"
DEFAULT_PROCESSING_STATUS = "处理中"
DEFAULT_SUCCESS_STATUS = "处理成功"
DEFAULT_PARTIAL_STATUS = "部分成功"
DEFAULT_FAILED_STATUS = "处理失败"

_worker_started = False
_worker_lock = threading.Lock()


def listener_state(conn: Any) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (LISTENER_ID,)).fetchone()
    if not row:
        current = now_iso()
        conn.execute(
            """
            INSERT INTO intake_listener_state (
                id, enabled, interval_seconds, status, created_at, updated_at
            ) VALUES (?, 0, 60, 'stopped', ?, ?)
            """,
            (LISTENER_ID, current, current),
        )
        row = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (LISTENER_ID,)).fetchone()
    state = row_to_dict(row)
    state["enabled"] = bool(state["enabled"])
    return state


def update_listener_state(conn: Any, enabled: bool | None = None, interval_seconds: int | None = None) -> dict[str, Any]:
    current = now_iso()
    state = listener_state(conn)
    next_enabled = state["enabled"] if enabled is None else enabled
    next_interval = state["interval_seconds"] if interval_seconds is None else max(30, min(interval_seconds, 3600))
    status = "waiting" if next_enabled else "stopped"
    next_scan_at = due_time(next_interval) if next_enabled else None
    conn.execute(
        """
        UPDATE intake_listener_state
        SET enabled = ?, interval_seconds = ?, status = ?, next_scan_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (int(next_enabled), next_interval, status, next_scan_at, current, LISTENER_ID),
    )
    return listener_state(conn)


def list_intake_runs(conn: Any, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM intake_runs ORDER BY started_at DESC LIMIT ?",
        (min(max(limit, 1), 200),),
    ).fetchall()
    return [intake_run_dict(conn, row) for row in rows]


def intake_run_dict(conn: Any, row: Any) -> dict[str, Any]:
    result = row_to_dict(row)
    result["input"] = from_json(result.pop("input_summary"), {})
    result["output"] = from_json(result.pop("output_summary"), {})
    records = conn.execute(
        """
        SELECT remote_record_id, filename, submitted_by, note, workflow_run_id, status, error_message, created_at
        FROM intake_record_results
        WHERE intake_run_id = ?
        ORDER BY id ASC
        """,
        (result["id"],),
    ).fetchall()
    result["records"] = [row_to_dict(record) for record in records]
    return result


def scan_intake_once(trigger_type: str = "manual", limit: int = 10) -> dict[str, Any]:
    with get_conn() as conn:
        return scan_intake_once_with_conn(conn, trigger_type=trigger_type, limit=limit)


def scan_intake_once_with_conn(conn: Any, trigger_type: str = "manual", limit: int = 10) -> dict[str, Any]:
    run_id = f"intake_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    conn.execute(
        """
        INSERT INTO intake_runs (
            id, listener_id, trigger_type, status, input_summary, started_at
        ) VALUES (?, ?, ?, 'running', ?, ?)
        """,
        (run_id, LISTENER_ID, trigger_type, summarize({"limit": limit}), started_at),
    )
    conn.execute(
        """
        UPDATE intake_listener_state
        SET status = 'scanning', last_scan_at = ?, last_error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (started_at, started_at, LISTENER_ID),
    )
    conn.commit()

    try:
        config = intake_config(conn)
        missing = [key for key in ("appId", "appSecret", "appToken", "intakeTableId") if not config.get(key)]
        if missing:
            raise RuntimeError(f"飞书监听配置缺失：{', '.join(missing)}")

        client = FeishuClient(config["appId"], config["appSecret"])
        pending_records = fetch_pending_records(client, config, limit)
        counters = {
            "scanned_count": len(pending_records),
            "processed_count": 0,
            "success_count": 0,
            "partial_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
        }

        for record in pending_records:
            result = process_intake_record(conn, client, config, run_id, record)
            counters["processed_count"] += 1
            if result["status"] == "success":
                counters["success_count"] += 1
            elif result["status"] == "partial_success":
                counters["partial_count"] += 1
            elif result["status"] == "skipped":
                counters["skipped_count"] += 1
            else:
                counters["failed_count"] += 1

        ended_at = now_iso()
        final_status = "success"
        if counters["failed_count"]:
            final_status = "partial_success" if counters["success_count"] or counters["partial_count"] else "failed"
        elif counters["partial_count"] or counters["skipped_count"]:
            final_status = "partial_success"
        conn.execute(
            """
            UPDATE intake_runs
            SET status = ?, scanned_count = ?, processed_count = ?, success_count = ?,
                partial_count = ?, failed_count = ?, skipped_count = ?, output_summary = ?,
                ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (
                final_status,
                counters["scanned_count"],
                counters["processed_count"],
                counters["success_count"],
                counters["partial_count"],
                counters["failed_count"],
                counters["skipped_count"],
                summarize(counters),
                ended_at,
                elapsed_ms(started),
                run_id,
            ),
        )
        finish_listener_scan(conn, None)
        conn.commit()
        return {"id": run_id, "status": final_status, **counters}
    except Exception as exc:
        ended_at = now_iso()
        error = str(exc)
        conn.execute(
            """
            UPDATE intake_runs
            SET status = 'failed', error_message = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (error, ended_at, elapsed_ms(started), run_id),
        )
        finish_listener_scan(conn, error)
        conn.commit()
        return {"id": run_id, "status": "failed", "error_message": error}


def process_intake_record(conn: Any, client: FeishuClient, config: dict[str, str], intake_run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    record_id = record.get("record_id", "")
    fields = record.get("fields", {})
    filename = attachment_filename(fields.get(config["fileField"])) or "feishu-form.csv"
    submitted_by = field_text(fields.get(config["submitterField"]))
    note = field_text(fields.get(config["noteField"]))
    current = now_iso()

    try:
        update_intake_record_status(client, config, record_id, DEFAULT_PROCESSING_STATUS, "", "", "")
        content = download_csv_content(client, fields.get(config["fileField"]))
        workflow = run_lead_import(
            conn,
            filename,
            content,
            submitted_by=submitted_by,
            note=note,
            submission_channel="feishu-form",
        )
        workflow_status = workflow.get("status", "success")
        final_status = "success" if workflow_status == "success" else "partial_success"
        feishu_status = DEFAULT_SUCCESS_STATUS if final_status == "success" else DEFAULT_PARTIAL_STATUS
        error_message = ""
        if final_status == "partial_success":
            error_message = "本地处理完成，但存在外部同步跳过或失败，请查看后台任务日志。"
        update_intake_record_status(
            client,
            config,
            record_id,
            feishu_status,
            workflow.get("workflow_run_id", ""),
            workflow_status,
            error_message,
        )
        save_intake_record_result(
            conn,
            intake_run_id,
            record_id,
            filename,
            submitted_by,
            note,
            workflow.get("workflow_run_id", ""),
            final_status,
            error_message,
        )
        conn.commit()
        return {"status": final_status, "workflow_run_id": workflow.get("workflow_run_id")}
    except Exception as exc:
        error_message = str(exc)
        try:
            update_intake_record_status(client, config, record_id, DEFAULT_FAILED_STATUS, "", "failed", error_message)
        except Exception:
            pass
        save_intake_record_result(conn, intake_run_id, record_id, filename, submitted_by, note, "", "failed", error_message)
        conn.commit()
        return {"status": "failed", "error_message": error_message}


def intake_config(conn: Any) -> dict[str, str]:
    config = get_module_config(conn, "feishu-sync")
    defaults = {
        "statusField": "处理状态",
        "fileField": "CSV 文件",
        "submitterField": "提交人",
        "noteField": "提交说明",
        "resultField": "处理结果",
        "runIdField": "工作流ID",
        "errorField": "错误信息",
        "processedAtField": "处理时间",
    }
    aliases = {
        "statusField": "intakeStatusField",
        "fileField": "intakeFileField",
        "submitterField": "intakeSubmitterField",
        "noteField": "intakeNoteField",
        "resultField": "intakeResultField",
        "runIdField": "intakeRunIdField",
        "errorField": "intakeErrorField",
    }
    for key, default in defaults.items():
        config[key] = config.get(aliases.get(key, ""), "") or default
    return config


def fetch_pending_records(client: FeishuClient, config: dict[str, str], limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_token = ""
    while len(records) < limit:
        page = client.list_records(config["appToken"], config["intakeTableId"], page_size=min(100, max(limit, 10)), page_token=page_token)
        for record in page["items"]:
            fields = record.get("fields", {})
            if field_text(fields.get(config["statusField"])) == DEFAULT_PENDING_STATUS:
                records.append(record)
                if len(records) >= limit:
                    break
        if len(records) >= limit or not page.get("has_more"):
            break
        page_token = page.get("page_token", "")
        if not page_token:
            break
    return records


def update_intake_record_status(
    client: FeishuClient,
    config: dict[str, str],
    record_id: str,
    status: str,
    workflow_run_id: str,
    result: str,
    error_message: str,
) -> None:
    fields: dict[str, Any] = {
        config["statusField"]: status,
        config["processedAtField"]: int(time.time() * 1000),
        config["runIdField"]: workflow_run_id,
        config["resultField"]: result,
        config["errorField"]: error_message[:1000] if error_message else "",
    }
    client.update_record(config["appToken"], config["intakeTableId"], record_id, fields)


def save_intake_record_result(
    conn: Any,
    intake_run_id: str,
    remote_record_id: str,
    filename: str,
    submitted_by: str,
    note: str,
    workflow_run_id: str,
    status: str,
    error_message: str,
) -> None:
    stored_workflow_run_id = workflow_run_id or None
    conn.execute(
        """
        INSERT INTO intake_record_results (
            intake_run_id, remote_record_id, filename, submitted_by, note,
            workflow_run_id, status, error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            intake_run_id,
            remote_record_id,
            filename,
            submitted_by,
            note,
            stored_workflow_run_id,
            status,
            error_message,
            now_iso(),
        ),
    )


def download_csv_content(client: FeishuClient, value: Any) -> str:
    if isinstance(value, str):
        return value
    attachment = first_attachment(value)
    if not attachment:
        raise RuntimeError("CSV 文件字段为空")
    if attachment.get("file_token"):
        data = client.download_file(attachment["file_token"])
    elif attachment.get("url") or attachment.get("tmp_url"):
        data = download_url(attachment.get("url") or attachment.get("tmp_url"))
    else:
        raise RuntimeError("CSV 附件缺少可下载地址或 file_token")
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def download_url(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FeishuApiError(f"附件下载 HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise FeishuApiError(f"附件下载网络错误: {exc.reason}") from exc


def first_attachment(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    if isinstance(value, dict):
        return value
    return None


def attachment_filename(value: Any) -> str:
    attachment = first_attachment(value)
    if not attachment:
        return ""
    return str(attachment.get("name") or attachment.get("file_name") or attachment.get("filename") or "")


def field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "name", "value"):
            if value.get(key):
                return str(value[key]).strip()
        return to_json(value)
    if isinstance(value, list):
        return " ".join(field_text(item) for item in value if field_text(item)).strip()
    return str(value).strip()


def finish_listener_scan(conn: Any, error: str | None) -> None:
    state = listener_state(conn)
    current = now_iso()
    if state["enabled"]:
        conn.execute(
            """
            UPDATE intake_listener_state
            SET status = 'waiting', next_scan_at = ?, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (due_time(state["interval_seconds"]), error, current, LISTENER_ID),
        )
    else:
        conn.execute(
            """
            UPDATE intake_listener_state
            SET status = 'stopped', next_scan_at = NULL, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, current, LISTENER_ID),
        )


def due_time(interval_seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)).isoformat(timespec="seconds")


def start_intake_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        thread = threading.Thread(target=worker_loop, name="intake-listener", daemon=True)
        thread.start()


def worker_loop() -> None:
    while True:
        try:
            with get_conn() as conn:
                state = listener_state(conn)
                if state["enabled"] and is_due(state.get("next_scan_at")):
                    scan_intake_once_with_conn(conn, trigger_type="auto", limit=10)
        except Exception:
            pass
        time.sleep(5)


def is_due(value: str | None) -> bool:
    if not value:
        return True
    try:
        due = datetime.fromisoformat(value)
    except ValueError:
        return True
    return due <= datetime.now(timezone.utc)
