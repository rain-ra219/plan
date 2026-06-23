from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import from_json, get_conn, intake_listener_dict, now_iso, row_to_dict, to_json
from tools.feishu_sync.client import FeishuApiError, FeishuClient
from tools.lead_import.workflow import WORKFLOW_ID, elapsed_ms, get_module_config, run_lead_import, summarize


LISTENER_ID = "feishu-form-csv"
DEFAULT_LIMIT = 10

_worker_started = False
_worker_lock = threading.Lock()


def listener_state(conn: Any) -> dict[str, Any]:
    ensure_default_listener(conn)
    row = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (LISTENER_ID,)).fetchone()
    return listener_row_dict(conn, row)


def list_intake_listeners(conn: Any) -> list[dict[str, Any]]:
    ensure_default_listener(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM intake_listener_state
        ORDER BY enabled DESC, updated_at DESC
        """
    ).fetchall()
    return [listener_row_dict(conn, row) for row in rows]


def listener_row_dict(conn: Any, row: Any) -> dict[str, Any]:
    result = intake_listener_dict(row)
    table = None
    base = None
    if result.get("table_config_id"):
        table = conn.execute(
            """
            SELECT t.*, b.name AS base_name, b.app_token
            FROM feishu_tables t
            LEFT JOIN feishu_bases b ON b.id = t.base_id
            WHERE t.id = ?
            """,
            (result["table_config_id"],),
        ).fetchone()
    if result.get("base_id"):
        base = conn.execute("SELECT * FROM feishu_bases WHERE id = ?", (result["base_id"],)).fetchone()
    result["table_name"] = table["name"] if table else ""
    result["table_id"] = table["table_id"] if table else ""
    result["base_name"] = base["name"] if base else (table["base_name"] if table else "")
    result["app_token"] = table["app_token"] if table else (base["app_token"] if base else "")
    return result


def update_listener_state(conn: Any, enabled: bool | None = None, interval_seconds: int | None = None) -> dict[str, Any]:
    ensure_default_listener(conn)
    values: dict[str, Any] = {}
    if enabled is not None:
        values["enabled"] = int(enabled)
        values["status"] = "waiting" if enabled else "stopped"
        values["next_scan_at"] = due_time(current_interval(conn, LISTENER_ID)) if enabled else None
    if interval_seconds is not None:
        values["interval_seconds"] = normalized_interval(interval_seconds)
        if enabled is not False:
            values["next_scan_at"] = due_time(values["interval_seconds"])
    if not values:
        return listener_state(conn)
    update_listener_columns(conn, LISTENER_ID, values)
    return listener_state(conn)


def create_intake_listener_config(conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    validate_listener_refs(conn, payload.get("base_id", ""), payload.get("table_config_id", ""), payload.get("workflow_id", ""))
    listener_id = f"listener_{uuid.uuid4().hex[:10]}"
    current = now_iso()
    conn.execute(
        """
        INSERT INTO intake_listener_state (
            id, name, base_id, table_config_id, workflow_id, enabled, interval_seconds,
            status, status_field, file_field, submitter_field, note_field, result_field,
            run_id_field, error_field, processed_at_field, pending_value, processing_value,
            success_value, partial_value, failed_value, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            listener_id,
            payload.get("name", "").strip() or "飞书监听器",
            payload.get("base_id", ""),
            payload.get("table_config_id", ""),
            payload.get("workflow_id", WORKFLOW_ID),
            int(payload.get("enabled", False)),
            normalized_interval(payload.get("interval_seconds", 60)),
            "waiting" if payload.get("enabled", False) else "stopped",
            payload.get("status_field") or "处理状态",
            payload.get("file_field") or "CSV 文件",
            payload.get("submitter_field") or "提交人",
            payload.get("note_field") or "提交说明",
            payload.get("result_field") or "处理结果",
            payload.get("run_id_field") or "工作流ID",
            payload.get("error_field") or "错误信息",
            payload.get("processed_at_field") or "处理时间",
            payload.get("pending_value") or "待处理",
            payload.get("processing_value") or "处理中",
            payload.get("success_value") or "处理成功",
            payload.get("partial_value") or "部分成功",
            payload.get("failed_value") or "处理失败",
            current,
            current,
        ),
    )
    if payload.get("enabled", False):
        update_listener_columns(conn, listener_id, {"next_scan_at": due_time(normalized_interval(payload.get("interval_seconds", 60)))})
    row = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
    return listener_row_dict(conn, row)


def update_intake_listener_config(conn: Any, listener_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
    if not row:
        raise ValueError("飞书监听器不存在")
    base_id = payload.get("base_id", row["base_id"] or "")
    table_config_id = payload.get("table_config_id", row["table_config_id"] or "")
    workflow_id = payload.get("workflow_id", row["workflow_id"] or WORKFLOW_ID)
    validate_listener_refs(conn, base_id, table_config_id, workflow_id)

    values: dict[str, Any] = {}
    for key in (
        "name",
        "base_id",
        "table_config_id",
        "workflow_id",
        "status_field",
        "file_field",
        "submitter_field",
        "note_field",
        "result_field",
        "run_id_field",
        "error_field",
        "processed_at_field",
        "pending_value",
        "processing_value",
        "success_value",
        "partial_value",
        "failed_value",
    ):
        if key in payload:
            values[key] = str(payload[key]).strip()
    if "interval_seconds" in payload:
        values["interval_seconds"] = normalized_interval(payload["interval_seconds"])
    if "enabled" in payload:
        values["enabled"] = int(bool(payload["enabled"]))
        values["status"] = "waiting" if payload["enabled"] else "stopped"
        interval = values.get("interval_seconds", row["interval_seconds"])
        values["next_scan_at"] = due_time(interval) if payload["enabled"] else None
    if values:
        update_listener_columns(conn, listener_id, values)
    updated = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
    return listener_row_dict(conn, updated)


def delete_intake_listener_config(conn: Any, listener_id: str) -> None:
    if listener_id == LISTENER_ID:
        raise ValueError("默认监听器不能删除，可以停用")
    runs = conn.execute("SELECT COUNT(*) AS count FROM intake_runs WHERE listener_id = ?", (listener_id,)).fetchone()
    if runs["count"]:
        raise ValueError("该监听器已有历史记录，请停用而不是删除")
    conn.execute("DELETE FROM intake_listener_state WHERE id = ?", (listener_id,))


def update_listener_columns(conn: Any, listener_id: str, values: dict[str, Any]) -> None:
    values["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in values)
    conn.execute(
        f"UPDATE intake_listener_state SET {assignments} WHERE id = ?",
        [*values.values(), listener_id],
    )


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
    listener = conn.execute("SELECT name FROM intake_listener_state WHERE id = ?", (result["listener_id"],)).fetchone()
    result["listener_name"] = listener["name"] if listener else result["listener_id"]
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


def scan_intake_once(trigger_type: str = "manual", limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    with get_conn() as conn:
        return scan_intake_once_with_conn(conn, trigger_type=trigger_type, limit=limit)


def scan_intake_listener_once(listener_id: str, trigger_type: str = "manual", limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    with get_conn() as conn:
        listener = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
        if not listener:
            return {"id": "", "listener_id": listener_id, "status": "failed", "error_message": "飞书监听器不存在"}
        return scan_one_listener_with_conn(conn, listener, trigger_type=trigger_type, limit=limit)


def scan_intake_once_with_conn(conn: Any, trigger_type: str = "manual", limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    ensure_default_listener(conn)
    listeners = conn.execute(
        "SELECT * FROM intake_listener_state WHERE enabled = 1 ORDER BY updated_at DESC"
    ).fetchall()
    if not listeners:
        default = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (LISTENER_ID,)).fetchone()
        listeners = [default] if default else []

    results = [scan_one_listener_with_conn(conn, listener, trigger_type=trigger_type, limit=limit) for listener in listeners]
    counters = {
        "scanned_count": sum(item.get("scanned_count", 0) for item in results),
        "processed_count": sum(item.get("processed_count", 0) for item in results),
        "success_count": sum(item.get("success_count", 0) for item in results),
        "partial_count": sum(item.get("partial_count", 0) for item in results),
        "failed_count": sum(item.get("failed_count", 0) for item in results),
        "skipped_count": sum(item.get("skipped_count", 0) for item in results),
    }
    status = aggregate_status(results)
    return {"id": f"scan_{uuid.uuid4().hex[:8]}", "status": status, "listeners": results, **counters}


def scan_one_listener_with_conn(conn: Any, listener: Any, trigger_type: str = "manual", limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    listener_id = listener["id"]
    run_id = f"intake_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    conn.execute(
        """
        INSERT INTO intake_runs (
            id, listener_id, trigger_type, status, input_summary, started_at
        ) VALUES (?, ?, ?, 'running', ?, ?)
        """,
        (run_id, listener_id, trigger_type, summarize({"limit": limit, "listener": listener["name"]}), started_at),
    )
    update_listener_columns(conn, listener_id, {"status": "scanning", "last_scan_at": started_at, "last_error": None})
    conn.commit()

    try:
        config = listener_runtime_config(conn, listener)
        missing = [key for key in ("appId", "appSecret", "appToken", "tableId") if not config.get(key)]
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
        final_status = counters_status(counters)
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
        finish_listener_scan(conn, listener_id, None)
        conn.commit()
        return {"id": run_id, "listener_id": listener_id, "listener_name": listener["name"], "status": final_status, **counters}
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
        finish_listener_scan(conn, listener_id, error)
        conn.commit()
        return {"id": run_id, "listener_id": listener_id, "listener_name": listener["name"], "status": "failed", "error_message": error}


def process_intake_record(conn: Any, client: FeishuClient, config: dict[str, Any], intake_run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    if config["workflowId"] != WORKFLOW_ID:
        raise RuntimeError(f"当前监听器暂不支持工作流：{config['workflowId']}")

    record_id = record.get("record_id", "")
    fields = record.get("fields", {})
    filename = attachment_filename(fields.get(config["fileField"])) or "feishu-form.csv"
    submitted_by = field_text(fields.get(config["submitterField"]))
    note = field_text(fields.get(config["noteField"]))

    try:
        update_intake_record_status(client, config, record_id, config["processingValue"], "", "", "")
        content = download_csv_content(client, fields.get(config["fileField"]))
        workflow = run_lead_import(
            conn,
            filename,
            content,
            submitted_by=submitted_by,
            note=note,
            submission_channel=f"feishu-listener:{config['listenerId']}",
        )
        workflow_status = workflow.get("status", "success")
        final_status = "success" if workflow_status == "success" else "partial_success"
        feishu_status = config["successValue"] if final_status == "success" else config["partialValue"]
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
            update_intake_record_status(client, config, record_id, config["failedValue"], "", "failed", error_message)
        except Exception:
            pass
        save_intake_record_result(conn, intake_run_id, record_id, filename, submitted_by, note, "", "failed", error_message)
        conn.commit()
        return {"status": "failed", "error_message": error_message}


def listener_runtime_config(conn: Any, listener: Any) -> dict[str, Any]:
    config = get_module_config(conn, "feishu-sync")
    base = None
    table = None
    if listener["table_config_id"]:
        table = conn.execute(
            """
            SELECT t.*, b.app_token
            FROM feishu_tables t
            LEFT JOIN feishu_bases b ON b.id = t.base_id
            WHERE t.id = ?
            """,
            (listener["table_config_id"],),
        ).fetchone()
    if listener["base_id"]:
        base = conn.execute("SELECT * FROM feishu_bases WHERE id = ?", (listener["base_id"],)).fetchone()
    app_token = table["app_token"] if table else (base["app_token"] if base else config.get("appToken", ""))
    table_id = table["table_id"] if table else config.get("intakeTableId", "")
    return {
        "listenerId": listener["id"],
        "workflowId": listener["workflow_id"] or WORKFLOW_ID,
        "appId": config.get("appId", ""),
        "appSecret": config.get("appSecret", ""),
        "appToken": app_token,
        "tableId": table_id,
        "statusField": listener["status_field"] or "处理状态",
        "fileField": listener["file_field"] or "CSV 文件",
        "submitterField": listener["submitter_field"] or "提交人",
        "noteField": listener["note_field"] or "提交说明",
        "resultField": listener["result_field"] or "处理结果",
        "runIdField": listener["run_id_field"] or "工作流ID",
        "errorField": listener["error_field"] or "错误信息",
        "processedAtField": listener["processed_at_field"] or "处理时间",
        "pendingValue": listener["pending_value"] or "待处理",
        "processingValue": listener["processing_value"] or "处理中",
        "successValue": listener["success_value"] or "处理成功",
        "partialValue": listener["partial_value"] or "部分成功",
        "failedValue": listener["failed_value"] or "处理失败",
    }


def fetch_pending_records(client: FeishuClient, config: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_token = ""
    while len(records) < limit:
        page = client.list_records(config["appToken"], config["tableId"], page_size=min(100, max(limit, 10)), page_token=page_token)
        for record in page["items"]:
            fields = record.get("fields", {})
            if field_text(fields.get(config["statusField"])) == config["pendingValue"]:
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
    config: dict[str, Any],
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
    client.update_record(config["appToken"], config["tableId"], record_id, fields)


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
            workflow_run_id or None,
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


def finish_listener_scan(conn: Any, listener_id: str, error: str | None) -> None:
    row = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
    if not row:
        return
    current = now_iso()
    if row["enabled"]:
        conn.execute(
            """
            UPDATE intake_listener_state
            SET status = 'waiting', next_scan_at = ?, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (due_time(row["interval_seconds"]), error, current, listener_id),
        )
    else:
        conn.execute(
            """
            UPDATE intake_listener_state
            SET status = 'stopped', next_scan_at = NULL, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, current, listener_id),
        )


def counters_status(counters: dict[str, int]) -> str:
    if counters["failed_count"]:
        return "partial_success" if counters["success_count"] or counters["partial_count"] else "failed"
    if counters["partial_count"] or counters["skipped_count"]:
        return "partial_success"
    return "success"


def aggregate_status(results: list[dict[str, Any]]) -> str:
    if not results:
        return "skipped"
    if all(item["status"] == "success" for item in results):
        return "success"
    if any(item["status"] in ("success", "partial_success") for item in results):
        return "partial_success"
    return "failed"


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
                ensure_default_listener(conn)
                rows = conn.execute(
                    "SELECT * FROM intake_listener_state WHERE enabled = 1 ORDER BY updated_at DESC"
                ).fetchall()
                for row in rows:
                    if is_due(row["next_scan_at"]):
                        scan_one_listener_with_conn(conn, row, trigger_type="auto", limit=DEFAULT_LIMIT)
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


def ensure_default_listener(conn: Any) -> None:
    row = conn.execute("SELECT id FROM intake_listener_state WHERE id = ?", (LISTENER_ID,)).fetchone()
    if row:
        return
    current = now_iso()
    conn.execute(
        """
        INSERT INTO intake_listener_state (
            id, name, workflow_id, enabled, interval_seconds, status, created_at, updated_at
        ) VALUES (?, 'CSV 线索导入监听', ?, 0, 60, 'stopped', ?, ?)
        """,
        (LISTENER_ID, WORKFLOW_ID, current, current),
    )


def current_interval(conn: Any, listener_id: str) -> int:
    row = conn.execute("SELECT interval_seconds FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
    return int(row["interval_seconds"]) if row else 60


def normalized_interval(value: Any) -> int:
    try:
        return max(30, min(int(value), 3600))
    except (TypeError, ValueError):
        return 60


def validate_listener_refs(conn: Any, base_id: str, table_config_id: str, workflow_id: str) -> None:
    if base_id and not conn.execute("SELECT id FROM feishu_bases WHERE id = ?", (base_id,)).fetchone():
        raise ValueError("飞书 Base 不存在")
    table = None
    if table_config_id:
        table = conn.execute("SELECT id, base_id FROM feishu_tables WHERE id = ?", (table_config_id,)).fetchone()
    if table_config_id and not table:
        raise ValueError("飞书表配置不存在")
    if base_id and table and table["base_id"] != base_id:
        raise ValueError("飞书表不属于所选 Base")
    if workflow_id and not conn.execute("SELECT id FROM workflows WHERE id = ?", (workflow_id,)).fetchone():
        raise ValueError("工作流不存在")
