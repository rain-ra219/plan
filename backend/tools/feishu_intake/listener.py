from __future__ import annotations

import base64
import mimetypes
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import from_json, get_conn, intake_listener_dict, now_iso, row_to_dict, to_json
from app.task_queue import (
    TERMINAL_STATUSES,
    claim_next_task,
    complete_task,
    enqueue_task,
    queue_worker_count,
    retry_delay_seconds,
    retry_task,
)
from app.workflow_registry import (
    WorkflowDefinition,
    WorkflowRegistryError,
    call_tool_entrypoint,
    ensure_workflow_available,
    get_workflow_definition,
    run_workflow,
)
from tools.feishu_sync.client import FeishuApiError, FeishuClient


LISTENER_ID = "feishu-form-csv"
DEFAULT_LIMIT = 10
DEFAULT_WORKFLOW_ID = "lead-import-to-feishu"

_worker_started = False
_worker_lock = threading.Lock()


def get_module_config(conn: Any, module_id: str) -> dict[str, str]:
    return {
        item["key"]: item["value"]
        for item in conn.execute(
            "SELECT key, value FROM module_configs WHERE module_id = ?",
            (module_id,),
        ).fetchall()
    }


def summarize(value: Any, limit: int = 700) -> str:
    text = to_json(value)
    return text if len(text) <= limit else text[:limit] + "..."


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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
    validate_registered_workflow(payload.get("workflow_id") or DEFAULT_WORKFLOW_ID)
    listener_id = f"listener_{uuid.uuid4().hex[:10]}"
    current = now_iso()
    conn.execute(
        """
        INSERT INTO intake_listener_state (
            id, name, base_id, table_config_id, workflow_id, enabled, interval_seconds,
            status, status_field, file_field, submitter_field, note_field,
            product_name_field, product_category_field, product_image_field,
            prompt_field, aspect_ratio_field, reference_image_field,
            product_description_field, reference_style_field, final_prompt_field,
            result_field, run_id_field, error_field, processed_at_field,
            pending_value, processing_value, success_value, partial_value, failed_value,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            listener_id,
            payload.get("name", "").strip() or "飞书监听器",
            payload.get("base_id", ""),
            payload.get("table_config_id", ""),
            payload.get("workflow_id", DEFAULT_WORKFLOW_ID),
            int(payload.get("enabled", False)),
            normalized_interval(payload.get("interval_seconds", 60)),
            "waiting" if payload.get("enabled", False) else "stopped",
            payload.get("status_field") or "处理状态",
            payload.get("file_field") or "CSV 文件",
            payload.get("submitter_field") or "提交人",
            payload.get("note_field") or "提交说明",
            payload.get("product_name_field") or "商品名称",
            payload.get("product_category_field") or "商品分类",
            payload.get("product_image_field") or "产品图",
            payload.get("prompt_field") or "图片提示词",
            payload.get("aspect_ratio_field") or "生成比例",
            payload.get("reference_image_field") or "参考图片",
            payload.get("product_description_field") or "产品图描述",
            payload.get("reference_style_field") or "参考图风格描述",
            payload.get("final_prompt_field") or "最终提示词",
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
    workflow_id = payload.get("workflow_id", row["workflow_id"] or DEFAULT_WORKFLOW_ID)
    validate_listener_refs(conn, base_id, table_config_id, workflow_id)
    validate_registered_workflow(workflow_id)

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
        "product_name_field",
        "product_category_field",
        "product_image_field",
        "prompt_field",
        "aspect_ratio_field",
        "reference_image_field",
        "product_description_field",
        "reference_style_field",
        "final_prompt_field",
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
        queued_count = 0

        for record in pending_records:
            try:
                result = enqueue_intake_record(conn, client, config, run_id, record)
            except Exception as exc:
                result = {"status": "failed", "error_message": str(exc)}
            if result["status"] == "queued":
                queued_count += 1
            elif result["status"] == "skipped":
                counters["skipped_count"] += 1
            else:
                counters["failed_count"] += 1

        ended_at = now_iso()
        final_status = scan_status(counters, queued_count)
        run_ended_at = None if final_status == "queued" else ended_at
        run_duration_ms = None if final_status == "queued" else elapsed_ms(started)
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
                summarize({**counters, "queued_count": queued_count}),
                run_ended_at,
                run_duration_ms,
                run_id,
            ),
        )
        finish_listener_scan(conn, listener_id, None)
        conn.commit()
        return {
            "id": run_id,
            "listener_id": listener_id,
            "listener_name": listener["name"],
            "status": final_status,
            "queued_count": queued_count,
            **counters,
        }
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


def enqueue_intake_record(conn: Any, client: FeishuClient, config: dict[str, Any], intake_run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    definition = ensure_workflow_available(conn, config["workflowId"])
    if definition.intake_kind not in {"csv_upload", "product_image"}:
        return {"status": "failed", "error_message": f"当前监听器暂不支持工作流：{config['workflowId']}"}
    record_id = record.get("record_id", "")
    if not record_id:
        return {"status": "failed", "error_message": "飞书记录缺少 record_id"}

    existing_queue = latest_queue_task(conn, config, record_id)
    if existing_queue and existing_queue["status"] not in TERMINAL_STATUSES:
        queue = existing_queue
        created = False
    else:
        queue = enqueue_task(
            conn,
            source="feishu_intake",
            source_key=queue_source_key(config, record_id, rerun=bool(existing_queue)),
            workflow_id=config["workflowId"],
            listener_id=config["listenerId"],
            intake_run_id=intake_run_id,
            remote_record_id=record_id,
            payload={
                "listener_id": config["listenerId"],
                "intake_run_id": intake_run_id,
                "workflow_id": config["workflowId"],
                "record": record,
            },
            max_attempts=3,
        )
        created = bool(queue.get("created"))
    conn.commit()

    if definition.intake_kind == "csv_upload":
        update_intake_record_status(client, config, record_id, config["processingValue"], queue["id"], "queued", "")
    else:
        update_product_image_record_status(client, config, record_id, config["processingValue"], queue["id"], "", None)

    return {
        "status": "queued" if created else "skipped",
        "queue_task_id": queue["id"],
    }


def latest_queue_task(conn: Any, config: dict[str, Any], record_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, status
        FROM task_queue
        WHERE source = 'feishu_intake'
          AND listener_id = ?
          AND workflow_id = ?
          AND remote_record_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (config["listenerId"], config["workflowId"], record_id),
    ).fetchone()
    return row_to_dict(row) if row else None


def queue_source_key(config: dict[str, Any], record_id: str, rerun: bool = False) -> str:
    parts = [
        "feishu_intake",
        config.get("listenerId", ""),
        config.get("appToken", ""),
        config.get("tableId", ""),
        config.get("workflowId", ""),
        record_id,
    ]
    if rerun:
        parts.extend(["rerun", uuid.uuid4().hex[:10]])
    return ":".join(parts)


def process_intake_record(conn: Any, client: FeishuClient, config: dict[str, Any], intake_run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    definition = ensure_workflow_available(conn, config["workflowId"])
    if definition.intake_kind == "csv_upload":
        return process_csv_intake_record(conn, client, config, intake_run_id, record)
    if definition.intake_kind == "product_image":
        return process_product_image_record(conn, client, config, intake_run_id, record, definition)
    raise RuntimeError(f"当前监听器暂不支持工作流：{config['workflowId']}")


def process_csv_intake_record(conn: Any, client: FeishuClient, config: dict[str, Any], intake_run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    record_id = record.get("record_id", "")
    fields = record.get("fields", {})
    filename = attachment_filename(fields.get(config["fileField"])) or "feishu-form.csv"
    submitted_by = field_text(fields.get(config["submitterField"]))
    note = field_text(fields.get(config["noteField"]))

    try:
        update_intake_record_status(client, config, record_id, config["processingValue"], config.get("queueTaskId", ""), "running", "")
        content = download_csv_content(client, fields.get(config["fileField"]))
        workflow = run_workflow(
            conn,
            config["workflowId"],
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


def process_product_image_record(
    conn: Any,
    client: FeishuClient,
    config: dict[str, Any],
    intake_run_id: str,
    record: dict[str, Any],
    definition: WorkflowDefinition,
) -> dict[str, Any]:
    record_id = record.get("record_id", "")
    fields = record.get("fields", {})
    product_name = field_text(fields.get(config["productNameField"])) or "飞书图片生成任务"
    product_category = field_text(fields.get(config["productCategoryField"]))
    prompt = field_text(fields.get(config["promptField"])) or product_name
    aspect_ratio = field_text(fields.get(config["aspectRatioField"])) or "1:1"
    note = f"{product_name} / {prompt}"

    try:
        update_product_image_record_status(client, config, record_id, config["processingValue"], config.get("queueTaskId", ""), "", None)
        product_images = []
        if definition.option("requiresProductImage", False):
            product_images = download_reference_image_data_uris(client, fields.get(config["productImageField"]))
            if not product_images:
                raise RuntimeError(f"{config['productImageField']}字段为空，主图详情页生成需要上传产品图")
        reference_images = download_reference_image_data_uris(client, fields.get(config["referenceImageField"]))
        task = call_tool_entrypoint(
            definition.tool_id,
            "createTask",
            conn,
            product_name=product_name,
            product_category=product_category,
            prompt=prompt,
            main_image_ratio=aspect_ratio,
            product_image=product_images[0] if product_images else "",
            reference_image=reference_images,
        )
        workflow = run_workflow(conn, config["workflowId"], task["id"], workflow_id=config["workflowId"])
        task_after = call_tool_entrypoint(definition.tool_id, "getTask", conn, task["id"])
        asset_path = workflow.get("asset_path") or (task_after.get("main_image_asset") or {}).get("path")
        if not asset_path:
            raise RuntimeError("图片生成完成，但没有找到生成资产文件")
        upload = client.upload_bitable_image(config["appToken"], asset_path)
        file_token = upload.get("file_token", "")
        if not file_token:
            raise RuntimeError("图片上传飞书成功响应中缺少 file_token")

        workflow_status = workflow.get("status", "success")
        final_status = "success" if workflow_status == "success" else "partial_success"
        feishu_status = config["successValue"] if final_status == "success" else config["partialValue"]
        error_message = "" if final_status == "success" else "图片已生成并回写，但工作流存在降级或部分成功。"
        update_product_image_record_status(
            client,
            config,
            record_id,
            feishu_status,
            workflow.get("workflow_run_id", ""),
            error_message,
            file_token,
        )
        trace_error = ""
        if definition.option("writesTraceFields", False):
            trace_error = update_product_trace_fields(client, config, record_id, workflow)
        if trace_error and final_status == "success":
            final_status = "partial_success"
            error_message = trace_error
            update_product_image_record_status(
                client,
                config,
                record_id,
                config["partialValue"],
                workflow.get("workflow_run_id", ""),
                error_message,
                file_token,
            )
        save_intake_record_result(
            conn,
            intake_run_id,
            record_id,
            product_name,
            "",
            note,
            workflow.get("workflow_run_id", ""),
            final_status,
            error_message,
        )
        conn.commit()
        return {"status": final_status, "workflow_run_id": workflow.get("workflow_run_id"), "file_token": file_token}
    except Exception as exc:
        error_message = str(exc)
        try:
            update_product_image_record_status(client, config, record_id, config["failedValue"], "", error_message, None)
        except Exception:
            pass
        save_intake_record_result(conn, intake_run_id, record_id, product_name, "", note, "", "failed", error_message)
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
        "workflowId": listener["workflow_id"] or DEFAULT_WORKFLOW_ID,
        "appId": config.get("appId", ""),
        "appSecret": config.get("appSecret", ""),
        "appToken": app_token,
        "tableId": table_id,
        "statusField": listener["status_field"] or "处理状态",
        "fileField": listener["file_field"] or "CSV 文件",
        "submitterField": listener["submitter_field"] or "提交人",
        "noteField": listener["note_field"] or "提交说明",
        "productNameField": listener["product_name_field"] or "商品名称",
        "productCategoryField": listener["product_category_field"] or "商品分类",
        "productImageField": listener["product_image_field"] or "产品图",
        "promptField": listener["prompt_field"] or "图片提示词",
        "aspectRatioField": listener["aspect_ratio_field"] or "生成比例",
        "referenceImageField": listener["reference_image_field"] or "参考图片",
        "productDescriptionField": listener["product_description_field"] or "产品图描述",
        "referenceStyleField": listener["reference_style_field"] or "参考图风格描述",
        "finalPromptField": listener["final_prompt_field"] or "最终提示词",
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


def update_product_image_record_status(
    client: FeishuClient,
    config: dict[str, Any],
    record_id: str,
    status: str,
    workflow_run_id: str,
    error_message: str,
    file_token: str | None,
) -> None:
    fields: dict[str, Any] = {
        config["statusField"]: status,
        config["processedAtField"]: int(time.time() * 1000),
        config["runIdField"]: workflow_run_id,
        config["errorField"]: error_message[:1000] if error_message else "",
    }
    if file_token:
        fields[config["resultField"]] = [{"file_token": file_token}]
    client.update_record(config["appToken"], config["tableId"], record_id, fields)


def update_product_trace_fields(
    client: FeishuClient,
    config: dict[str, Any],
    record_id: str,
    workflow: dict[str, Any],
) -> str:
    fields: dict[str, Any] = {}
    trace_values = (
        (config.get("productDescriptionField"), workflow.get("product_description", "")),
        (config.get("referenceStyleField"), workflow.get("reference_style", "")),
        (config.get("finalPromptField"), workflow.get("final_prompt", "")),
    )
    for field_name, value in trace_values:
        if field_name and value:
            fields[field_name] = str(value)[:5000]
    if not fields:
        return ""
    try:
        client.update_record(config["appToken"], config["tableId"], record_id, fields)
        return ""
    except FeishuApiError as exc:
        return f"追溯字段回写失败：{exc}"


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


def download_reference_image_data_uris(client: FeishuClient, value: Any) -> list[str]:
    images: list[str] = []
    for attachment in attachments(value):
        data = download_attachment_bytes(client, attachment, "参考图片")
        mime_type = attachment_mime_type(attachment)
        encoded = base64.b64encode(data).decode("ascii")
        images.append(f"data:{mime_type};base64,{encoded}")
    return images


def download_attachment_bytes(client: FeishuClient, attachment: dict[str, Any], label: str) -> bytes:
    if attachment.get("file_token"):
        return client.download_file(attachment["file_token"])
    url = attachment.get("url") or attachment.get("tmp_url")
    if url:
        return download_url(str(url))
    raise RuntimeError(f"{label}附件缺少可下载地址或 file_token")


def attachment_mime_type(attachment: dict[str, Any]) -> str:
    for key in ("mime_type", "mimeType", "type"):
        value = attachment.get(key)
        if isinstance(value, str) and value.startswith("image/"):
            return value
    filename = str(
        attachment.get("name")
        or attachment.get("file_name")
        or attachment.get("filename")
        or ""
    )
    guessed = mimetypes.guess_type(filename)[0] if filename else ""
    return guessed if guessed and guessed.startswith("image/") else "image/png"


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


def attachments(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


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


def scan_status(counters: dict[str, int], queued_count: int) -> str:
    if queued_count and counters["failed_count"]:
        return "partial_success"
    if queued_count:
        return "queued"
    return counters_status(counters)


def aggregate_status(results: list[dict[str, Any]]) -> str:
    if not results:
        return "skipped"
    if all(item["status"] == "success" for item in results):
        return "success"
    if any(item["status"] == "queued" for item in results):
        return "partial_success" if any(item["status"] == "failed" for item in results) else "queued"
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
        scanner = threading.Thread(target=worker_loop, name="intake-listener-scan", daemon=True)
        scanner.start()
        for index in range(queue_worker_count()):
            queue_worker = threading.Thread(
                target=queue_worker_loop,
                name=f"intake-task-queue-{index + 1}",
                daemon=True,
            )
            queue_worker.start()


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


def queue_worker_loop() -> None:
    while True:
        processed = False
        try:
            processed = process_next_queue_task()
        except Exception:
            pass
        time.sleep(1 if processed else 3)


def process_next_queue_task() -> bool:
    with get_conn() as conn:
        task = claim_next_task(conn, source="feishu_intake")
        if not task:
            return False
        conn.commit()
        process_queue_task(conn, task)
        return True


def process_queue_task(conn: Any, task: dict[str, Any]) -> None:
    payload = task.get("payload") or {}
    listener_id = payload.get("listener_id") or task.get("listener_id") or ""
    intake_run_id = payload.get("intake_run_id") or task.get("intake_run_id") or ""
    record = payload.get("record") or {}
    workflow_run_id = ""
    output: dict[str, Any] = {}
    status = "failed"
    error_message = ""
    client: FeishuClient | None = None
    config: dict[str, Any] = {}

    try:
        listener = conn.execute("SELECT * FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
        if not listener:
            raise RuntimeError("飞书监听器不存在，队列任务无法执行")
        config = listener_runtime_config(conn, listener)
        config["queueTaskId"] = task["id"]
        client = FeishuClient(config["appId"], config["appSecret"])
        result = process_intake_record(conn, client, config, intake_run_id, record)
        workflow_run_id = str(result.get("workflow_run_id") or "")
        status = result.get("status", "failed")
        output = result
        error_message = result.get("error_message", "")
    except Exception as exc:
        error_message = str(exc)
        output = {"error_message": error_message}
        status = "failed"

    final_status = status if status in {"success", "partial_success", "failed", "skipped"} else "failed"
    if should_retry_queue_task(task, final_status, error_message):
        if client is not None and config:
            mark_remote_record_retrying(client, config, record, task["id"], error_message)
        retry_task(
            conn,
            task["id"],
            error_message=error_message,
            delay_seconds=retry_delay_seconds(int(task.get("attempt_count") or 1)),
            output=output,
        )
    else:
        complete_task(
            conn,
            task["id"],
            status=final_status,
            output=output,
            workflow_run_id=workflow_run_id,
            error_message=error_message,
        )
    if intake_run_id:
        refresh_intake_run_counts(conn, intake_run_id)
    conn.commit()


def should_retry_queue_task(task: dict[str, Any], status: str, error_message: str) -> bool:
    if status != "failed":
        return False
    if int(task.get("attempt_count") or 0) >= int(task.get("max_attempts") or 1):
        return False
    return is_retryable_error(error_message)


def mark_remote_record_retrying(client: FeishuClient, config: dict[str, Any], record: dict[str, Any], queue_task_id: str, error_message: str) -> None:
    record_id = record.get("record_id", "")
    if not record_id:
        return
    message = f"临时错误，稍后自动重试：{error_message[:800]}"
    try:
        definition = get_workflow_definition(config["workflowId"])
        if definition.intake_kind == "csv_upload":
            update_intake_record_status(client, config, record_id, config["processingValue"], queue_task_id, "retrying", message)
        elif definition.intake_kind == "product_image":
            update_product_image_record_status(client, config, record_id, config["processingValue"], queue_task_id, message, None)
    except Exception:
        pass


def is_retryable_error(error_message: str) -> bool:
    text = (error_message or "").lower()
    if not text:
        return False
    retry_markers = (
        "http 408",
        "http 409",
        "http 425",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "timeout",
        "timed out",
        "connection reset",
        "remote end closed",
        "unexpected_eof",
        "eof occurred",
        "temporarily unavailable",
        "network error",
        "ssl",
        "请求超时",
        "连接失败",
        "网络错误",
        "断开",
    )
    return any(marker in text for marker in retry_markers)


def refresh_intake_run_counts(conn: Any, intake_run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM task_queue
        WHERE intake_run_id = ?
        GROUP BY status
        """,
        (intake_run_id,),
    ).fetchall()
    counts = {row["status"]: row["count"] for row in rows}
    pending_count = counts.get("pending", 0)
    running_count = counts.get("running", 0)
    success_count = counts.get("success", 0)
    partial_count = counts.get("partial_success", 0)
    failed_count = counts.get("failed", 0)
    skipped_count = counts.get("skipped", 0)
    processed_count = success_count + partial_count + failed_count + skipped_count
    unfinished_count = pending_count + running_count
    current = now_iso()

    if unfinished_count:
        status = "running" if running_count else "queued"
        ended_at = None
        duration_ms = None
    else:
        status = counters_status(
            {
                "success_count": success_count,
                "partial_count": partial_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
            }
        )
        ended_at = current
        started = conn.execute("SELECT started_at FROM intake_runs WHERE id = ?", (intake_run_id,)).fetchone()
        duration_ms = elapsed_since_iso(started["started_at"]) if started and started["started_at"] else None

    conn.execute(
        """
        UPDATE intake_runs
        SET status = ?, processed_count = ?, success_count = ?, partial_count = ?,
            failed_count = ?, skipped_count = ?, output_summary = ?,
            ended_at = COALESCE(?, ended_at), duration_ms = COALESCE(?, duration_ms)
        WHERE id = ?
        """,
        (
            status,
            processed_count,
            success_count,
            partial_count,
            failed_count,
            skipped_count,
            summarize({"queue": counts}),
            ended_at,
            duration_ms,
            intake_run_id,
        ),
    )


def elapsed_since_iso(started_at: str) -> int:
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return int((datetime.now(started.tzinfo) - started).total_seconds() * 1000)


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
        (LISTENER_ID, DEFAULT_WORKFLOW_ID, current, current),
    )


def current_interval(conn: Any, listener_id: str) -> int:
    row = conn.execute("SELECT interval_seconds FROM intake_listener_state WHERE id = ?", (listener_id,)).fetchone()
    return int(row["interval_seconds"]) if row else 60


def normalized_interval(value: Any) -> int:
    try:
        return max(30, min(int(value), 3600))
    except (TypeError, ValueError):
        return 60


def validate_registered_workflow(workflow_id: str) -> None:
    if not workflow_id:
        return
    try:
        get_workflow_definition(workflow_id)
    except WorkflowRegistryError as exc:
        raise ValueError(str(exc)) from exc


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
