from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable

from app.database import now_iso
from tools.feishu_sync.client import FeishuClient

from .tikhub_client import get_note_id, note_payload


LINK_WORKFLOW_ID = "xhs-link-analysis"

DETAIL_FIELDS = {
    "可参考性": "参考性",
    "痛点摘要": "痛点摘要",
    "功效期望": "功效期望",
    "成分态度": "成分态度",
    "竞品情报": "竞品情报",
    "价格信号": "价格信号",
    "研发建议": "研发建议",
    "备注": "备注",
}

LogTask = Callable[..., None]


def write_detail_records(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    feishu: FeishuClient,
    config: dict[str, str],
    keyword: str,
    analyses: list[dict[str, Any]],
    *,
    log_task_fn: LogTask,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = now_iso()
    include_trace_fields = truthy(config.get("writeTraceFields"))
    fields_list = [
        build_detail_fields(
            workflow_run_id,
            keyword,
            item["note"],
            item["comments"],
            item["analysis"],
            include_trace_fields=include_trace_fields,
        )
        for item in analyses
    ]
    try:
        if not config.get("detailAppToken") or not config.get("detailTableId"):
            raise ValueError("TikHub weekly detail Feishu table is not configured")
        result = feishu.batch_create_records(config["detailAppToken"], config["detailTableId"], fields_list)
        output = {"rows": len(fields_list), "created": result.get("created", 0), "target": "小红书单篇分析明细表"}
        log_task_fn(conn, workflow_run_id, "feishu-sync", "table.write", {"target": "xhs_detail", "rows": len(fields_list)}, output, "success", started_at, started)
        conn.commit()
        return {"status": "success", **output}
    except Exception as exc:
        output = {"rows": len(fields_list), "target": "小红书单篇分析明细表"}
        log_task_fn(conn, workflow_run_id, "feishu-sync", "table.write", {"target": "xhs_detail", "rows": len(fields_list)}, output, "failed", started_at, started, str(exc))
        conn.commit()
        return {"status": "failed", "error_message": str(exc), **output}


def write_link_output_record(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    feishu: FeishuClient,
    output_app_token: str,
    output_table_id: str,
    link: str,
    comments: list[dict[str, Any]],
    analysis: dict[str, Any],
    *,
    log_task_fn: LogTask,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = now_iso()
    fields = build_link_output_fields(link, analysis)
    try:
        result = feishu.batch_create_records(output_app_token, output_table_id, [fields])
        output = {"rows": 1, "created": result.get("created", 0), "target": "小红书链接分析输出表"}
        log_task_fn(
            conn,
            workflow_run_id,
            "feishu-sync",
            "table.write",
            {"target": "xhs_link_output", "link": shorten(link), "comments": len(comments)},
            output,
            "success",
            started_at,
            started,
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        return {"status": "success", **output}
    except Exception as exc:
        output = {"rows": 1, "target": "小红书链接分析输出表"}
        log_task_fn(
            conn,
            workflow_run_id,
            "feishu-sync",
            "table.write",
            {"target": "xhs_link_output", "link": shorten(link)},
            output,
            "failed",
            started_at,
            started,
            str(exc),
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        return {"status": "failed", "error_message": str(exc), **output}


def write_report_record(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    feishu: FeishuClient,
    config: dict[str, str],
    keyword: str,
    report_text: str,
    report_file: dict[str, Any],
    note_count: int,
    comment_count: int,
    *,
    log_task_fn: LogTask,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = now_iso()
    try:
        report_app_token = config.get("reportAppToken") or config.get("detailAppToken", "")
        if not report_app_token or not config.get("reportTableId"):
            raise ValueError("TikHub weekly report Feishu table is not configured")
        upload = feishu.upload_bitable_file(report_app_token, report_file["path"], parent_type="bitable_file")
        fields = {
            "标题": report_file["filename"],
            "报告正文": [{"file_token": upload["file_token"]}],
        }
        if truthy(config.get("writeReportMetaFields")):
            fields.update(
                {
                    "关键词": keyword,
                    "笔记数": note_count,
                    "评论数": comment_count,
                    "工作流ID": workflow_run_id,
                }
            )
        result = feishu.batch_create_records(report_app_token, config["reportTableId"], [compact_fields(fields)])
        output = {"rows": 1, "created": result.get("created", 0), "file_token": upload["file_token"], "target": "小红书周报表"}
        log_task_fn(conn, workflow_run_id, "feishu-sync", "table.write", {"target": "xhs_report", "chars": len(report_text)}, output, "success", started_at, started)
        conn.commit()
        return {"status": "success", **output}
    except Exception as exc:
        output = {"rows": 1, "target": "小红书周报表"}
        log_task_fn(conn, workflow_run_id, "feishu-sync", "table.write", {"target": "xhs_report"}, output, "failed", started_at, started, str(exc))
        conn.commit()
        return {"status": "failed", "error_message": str(exc), **output}


def build_detail_fields(
    workflow_run_id: str,
    keyword: str,
    note_item: dict[str, Any],
    comments: list[dict[str, Any]],
    analysis: dict[str, Any],
    include_trace_fields: bool = False,
) -> dict[str, Any]:
    note = note_payload(note_item)
    note_id = get_note_id(note_item)
    xsec_token = str(note.get("xsec_token") or "")
    fields = {
        "原帖链接": f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search" if note_id else "",
    }
    if include_trace_fields:
        fields.update(
            {
                "笔记ID": note_id,
                "评论数": len(comments),
                "关键词": keyword,
                "工作流ID": workflow_run_id,
            }
        )
    for source, target in DETAIL_FIELDS.items():
        fields[target] = stringify_value(analysis.get(source, "未涉及"))
    return compact_fields(fields)


def build_link_output_fields(link: str, analysis: dict[str, Any]) -> dict[str, Any]:
    fields = {"原帖链接": link}
    for source, target in DETAIL_FIELDS.items():
        fields[target] = stringify_value(analysis.get(source, "未涉及"))
    return compact_fields(fields)


def resolve_weekly_output_tables(conn: sqlite3.Connection, config: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    if config.get("detailAppToken") and config.get("detailTableId"):
        resolved["detailAppToken"] = config["detailAppToken"]
        resolved["detailTableId"] = config["detailTableId"]
    else:
        detail_table = find_feishu_table(
            conn,
            purposes=("xhs_weekly_detail", "xhs_detail", "xhs_ai_detail"),
            names=("ai数据输出表", "ai数据输出", "ai表格", "AI表格", "小红书单篇分析明细表"),
        )
        if detail_table:
            resolved["detailAppToken"] = detail_table["app_token"] or ""
            resolved["detailTableId"] = detail_table["table_id"] or ""

    if config.get("reportAppToken") and config.get("reportTableId"):
        resolved["reportAppToken"] = config["reportAppToken"]
        resolved["reportTableId"] = config["reportTableId"]
    elif config.get("reportTableId") and (resolved.get("detailAppToken") or config.get("detailAppToken")):
        resolved["reportAppToken"] = resolved.get("detailAppToken") or config.get("detailAppToken", "")
        resolved["reportTableId"] = config["reportTableId"]
    else:
        report_table = find_feishu_table(
            conn,
            purposes=("xhs_weekly_report", "xhs_report"),
            names=("ai总结报告表", "ai总结报告", "每周更新总结报告", "小红书周报表"),
        )
        if report_table:
            resolved["reportAppToken"] = report_table["app_token"] or ""
            resolved["reportTableId"] = report_table["table_id"] or ""
    return resolved


def find_feishu_table(
    conn: sqlite3.Connection,
    *,
    purposes: tuple[str, ...],
    names: tuple[str, ...],
) -> sqlite3.Row | None:
    purpose_placeholders = ", ".join("?" for _ in purposes)
    name_placeholders = ", ".join("?" for _ in names)
    return conn.execute(
        f"""
        SELECT t.table_id, b.app_token
        FROM feishu_tables t
        LEFT JOIN feishu_bases b ON b.id = t.base_id
        WHERE (t.purpose IN ({purpose_placeholders}) OR t.name IN ({name_placeholders}))
          AND COALESCE(b.enabled, 1) = 1
        ORDER BY
          CASE WHEN t.purpose IN ({purpose_placeholders}) THEN 0 ELSE 1 END,
          t.updated_at DESC
        LIMIT 1
        """,
        (*purposes, *names, *purposes),
    ).fetchone()


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "是", "启用"}


def stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(stringify_value(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {stringify_value(item)}" for key, item in value.items())
    return str(value)


def compact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in ("", None, [], {})}


def shorten(value: str, limit: int = 120) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
