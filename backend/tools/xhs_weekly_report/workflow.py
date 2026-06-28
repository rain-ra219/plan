from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from typing import Any

from app.database import UPLOAD_DIR, get_model_profile_config, now_iso, to_json
from tools.feishu_sync.client import FeishuClient
from tools.model_provider.service import generate_text
from .feishu_output import (
    DETAIL_FIELDS,
    compact_fields,
    resolve_weekly_output_tables,
    stringify_value,
    write_detail_records,
    write_link_output_record,
    write_report_record,
)
from .prompts import NOTE_ANALYSIS_SYSTEM, REPORT_SYSTEM, prompt_config
from .tikhub_client import (
    DEFAULT_COMMENTS_PATH,
    DEFAULT_SEARCH_PATH,
    comments_query_from_link,
    comments_query_from_note_id,
    comments_response_items,
    config_path,
    extract_comments,
    extract_note_id,
    get_note_id,
    note_comment_count,
    note_payload,
    search_response_items,
    tikhub_get,
)


WORKFLOW_ID = "xhs-weekly-report"
LINK_WORKFLOW_ID = "xhs-link-analysis"
MODULE_ID = "xhs-weekly-report"
DEFAULT_MAX_NOTES = 20
DEFAULT_MAX_COMMENTS_PER_NOTE = 100

def run_xhs_weekly_report(
    conn: sqlite3.Connection,
    keyword: str = "",
    max_notes: int | None = None,
    sort_type: str = "",
    time_filter: str = "",
    note_type: str = "",
) -> dict[str, Any]:
    workflow_run_id = f"run_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    config = get_module_config(conn, MODULE_ID)
    keyword = (keyword or config.get("defaultKeyword") or "洗头").strip()
    max_notes = normalize_limit(max_notes or config.get("maxNotes") or DEFAULT_MAX_NOTES)
    sort_type = normalize_option(sort_type or config.get("sortType"), "comment_descending")
    time_filter = normalize_option(time_filter or config.get("timeFilter"), "一周内")
    note_type = normalize_option(note_type or config.get("noteType"), "不限")
    max_comments_per_note = normalize_limit(
        config.get("maxCommentsPerNote") or DEFAULT_MAX_COMMENTS_PER_NOTE,
        default=DEFAULT_MAX_COMMENTS_PER_NOTE,
        maximum=500,
    )
    input_summary = {
        "keyword": keyword,
        "max_notes": max_notes,
        "sort_type": sort_type,
        "time_filter": time_filter,
        "note_type": note_type,
    }

    conn.execute(
        """
        INSERT INTO workflow_runs (
            id, workflow_id, status, input_summary, started_at
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (workflow_run_id, WORKFLOW_ID, summarize(input_summary), started_at),
    )
    conn.commit()

    try:
        validate_config(config)
        config = {**config, **resolve_weekly_output_tables(conn, config)}
        feishu_config = get_module_config(conn, "feishu-sync")
        feishu = FeishuClient(feishu_config.get("appId", ""), feishu_config.get("appSecret", ""))
        model_config = get_model_profile_config(conn, "text")
        note_analysis_system = prompt_config(config, "noteAnalysisSystemPrompt", NOTE_ANALYSIS_SYSTEM)
        report_system = prompt_config(config, "reportSystemPrompt", REPORT_SYSTEM)

        notes = search_notes(conn, workflow_run_id, config, keyword, max_notes, sort_type, time_filter, note_type)
        analyses: list[dict[str, Any]] = []
        total_comments = 0

        for note in notes:
            comments = fetch_comments(conn, workflow_run_id, config, note, max_comments_per_note)
            total_comments += len(comments)
            if not comments:
                continue
            analysis = analyze_note(conn, workflow_run_id, model_config, note, comments, note_analysis_system)
            analyses.append({"note": note, "comments": comments, "analysis": analysis})

        detail_sync = write_detail_records(conn, workflow_run_id, feishu, config, keyword, analyses, log_task_fn=log_task)
        report_text = generate_report(conn, workflow_run_id, model_config, keyword, analyses, report_system)
        report_file = save_report_file(conn, workflow_run_id, keyword, report_text)
        report_sync = write_report_record(conn, workflow_run_id, feishu, config, keyword, report_text, report_file, len(notes), total_comments, log_task_fn=log_task)

        output = {
            "keyword": keyword,
            "notes": len(notes),
            "analyzed_notes": len(analyses),
            "comments": total_comments,
            "detail_sync": detail_sync,
            "report_sync": report_sync,
            "file_id": report_file["id"],
        }
        status = "success" if detail_sync["status"] == "success" and report_sync["status"] == "success" else "partial_success"
        error_message = "; ".join(
            item.get("error_message", "")
            for item in [detail_sync, report_sync]
            if item.get("status") != "success" and item.get("error_message")
        )
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = ?, output_summary = ?, ended_at = ?, duration_ms = ?, error_message = ?
            WHERE id = ?
            """,
            (status, summarize(output), now_iso(), elapsed_ms(started), error_message, workflow_run_id),
        )
        conn.commit()
        return {"workflow_run_id": workflow_run_id, "status": status, **output}
    except Exception as exc:
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = 'failed', error_message = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (str(exc), now_iso(), elapsed_ms(started), workflow_run_id),
        )
        log_task(
            conn,
            workflow_run_id,
            MODULE_ID,
            "workflow.run",
            input_summary,
            {},
            "failed",
            started_at,
            started,
            str(exc),
        )
        conn.commit()
        raise


def run_xhs_link_analysis(
    conn: sqlite3.Connection,
    *,
    link: str,
    output_app_token: str,
    output_table_id: str,
    submitted_by: str = "",
    note: str = "",
    max_comments_per_note: int | None = None,
) -> dict[str, Any]:
    workflow_run_id = f"run_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    clean_link = str(link or "").strip()
    config = get_module_config(conn, MODULE_ID)
    model_config = get_model_profile_config(conn, "text")
    input_summary = {"link": shorten(clean_link), "submitted_by": submitted_by, "note": note}

    conn.execute(
        """
        INSERT INTO workflow_runs (
            id, workflow_id, status, input_summary, started_at
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (workflow_run_id, LINK_WORKFLOW_ID, summarize(input_summary), started_at),
    )
    conn.commit()

    try:
        validate_link_config(config, clean_link, output_app_token, output_table_id)
        note_analysis_system = prompt_config(config, "noteAnalysisSystemPrompt", NOTE_ANALYSIS_SYSTEM)
        comment_limit = normalize_limit(
            max_comments_per_note or config.get("maxCommentsPerNote") or DEFAULT_MAX_COMMENTS_PER_NOTE,
            default=DEFAULT_MAX_COMMENTS_PER_NOTE,
            maximum=500,
        )
        feishu_config = get_module_config(conn, "feishu-sync")
        feishu = FeishuClient(feishu_config.get("appId", ""), feishu_config.get("appSecret", ""))

        comments = fetch_link_comments(conn, workflow_run_id, config, clean_link, comment_limit)
        if not comments:
            raise ValueError("未抓取到有效评论")
        analysis = analyze_link_comments(conn, workflow_run_id, model_config, clean_link, comments, note_analysis_system)
        output_sync = write_link_output_record(
            conn,
            workflow_run_id,
            feishu,
            output_app_token,
            output_table_id,
            clean_link,
            comments,
            analysis,
            log_task_fn=log_task,
        )
        output = {"link": shorten(clean_link), "comments": len(comments), "output_sync": output_sync}
        status = "success" if output_sync["status"] == "success" else "failed"
        error_message = output_sync.get("error_message", "") if status != "success" else ""
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = ?, output_summary = ?, ended_at = ?, duration_ms = ?, error_message = ?
            WHERE id = ?
            """,
            (status, summarize(output), now_iso(), elapsed_ms(started), error_message, workflow_run_id),
        )
        conn.commit()
        return {"workflow_run_id": workflow_run_id, "status": status, **output}
    except Exception as exc:
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = 'failed', error_message = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (str(exc), now_iso(), elapsed_ms(started), workflow_run_id),
        )
        log_task(
            conn,
            workflow_run_id,
            MODULE_ID,
            "workflow.run",
            input_summary,
            {},
            "failed",
            started_at,
            started,
            str(exc),
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        raise


def search_notes(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    config: dict[str, str],
    keyword: str,
    max_notes: int,
    sort_type: str = "comment_descending",
    time_filter: str = "一周内",
    note_type: str = "不限",
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    started_at = now_iso()
    try:
        result = tikhub_get(
            config,
            config_path(config, "searchPath", DEFAULT_SEARCH_PATH),
            {
                "keyword": keyword,
                "page": "1",
                "sort_type": sort_type,
                "note_type": note_type,
                "time_filter": time_filter,
                "source": config.get("source") or "explore_feed",
                "ai_mode": normalize_ai_mode(config.get("aiMode")),
            },
        )
        items = search_response_items(result)
        notes = [item for item in items if isinstance(item, dict) and note_payload(item)]
        if sort_type == "comment_descending":
            notes.sort(key=note_comment_count, reverse=True)
        notes = notes[:max_notes]
        log_task(
            conn,
            workflow_run_id,
            MODULE_ID,
            "xhs.search",
            {"keyword": keyword, "max_notes": max_notes, "sort_type": sort_type, "time_filter": time_filter, "note_type": note_type},
            {"notes": len(notes)},
            "success",
            started_at,
            started,
        )
        conn.commit()
        return notes
    except Exception as exc:
        log_task(conn, workflow_run_id, MODULE_ID, "xhs.search", {"keyword": keyword}, {}, "failed", started_at, started, str(exc))
        conn.commit()
        raise


def fetch_comments(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    config: dict[str, str],
    note_item: dict[str, Any],
    comment_limit: int,
) -> list[dict[str, Any]]:
    note_id = get_note_id(note_item)
    started = time.perf_counter()
    started_at = now_iso()
    if not note_id:
        return []
    try:
        result = tikhub_get(
            config,
            config_path(config, "commentsPath", DEFAULT_COMMENTS_PATH),
            comments_query_from_note_id(note_id, config),
        )
        comments = extract_comments(comments_response_items(result))[:comment_limit]
        log_task(
            conn,
            workflow_run_id,
            MODULE_ID,
            "xhs.comments",
            {"note_id": note_id, "comment_limit": comment_limit},
            {"comments": len(comments)},
            "success",
            started_at,
            started,
        )
        conn.commit()
        return comments
    except Exception as exc:
        log_task(conn, workflow_run_id, MODULE_ID, "xhs.comments", {"note_id": note_id}, {}, "failed", started_at, started, str(exc))
        conn.commit()
        return []


def fetch_link_comments(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    config: dict[str, str],
    link: str,
    comment_limit: int,
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    started_at = now_iso()
    query = comments_query_from_link(link, config)
    try:
        result = tikhub_get(config, config_path(config, "commentsPath", DEFAULT_COMMENTS_PATH), query)
        comments = extract_comments(comments_response_items(result))[:comment_limit]
        log_task(
            conn,
            workflow_run_id,
            MODULE_ID,
            "xhs.link.comments",
            {"link": shorten(link), "comment_limit": comment_limit},
            {"comments": len(comments)},
            "success",
            started_at,
            started,
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        return comments
    except Exception as exc:
        log_task(
            conn,
            workflow_run_id,
            MODULE_ID,
            "xhs.link.comments",
            {"link": shorten(link)},
            {},
            "failed",
            started_at,
            started,
            str(exc),
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        raise


def analyze_note(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    model_config: dict[str, str],
    note_item: dict[str, Any],
    comments: list[dict[str, Any]],
    system_prompt: str,
) -> dict[str, Any]:
    note_id = get_note_id(note_item)
    started = time.perf_counter()
    started_at = now_iso()
    prompt = "\n".join(
        [
            build_note_context(note_item),
            "",
            "评论：",
            "\n".join(f"[赞{item['like_count']}] {item['author']}: {item['content']}" for item in comments),
        ]
    )
    try:
        raw = generate_text(prompt, config=model_config, system=system_prompt)
        analysis = parse_model_json(raw)
        log_task(conn, workflow_run_id, "model-provider", "text.generate", {"note_id": note_id, "comments": len(comments)}, compact_analysis(analysis), "success", started_at, started)
        conn.commit()
        return analysis
    except Exception as exc:
        log_task(conn, workflow_run_id, "model-provider", "text.generate", {"note_id": note_id, "comments": len(comments)}, {}, "failed", started_at, started, str(exc))
        conn.commit()
        raise


def analyze_link_comments(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    model_config: dict[str, str],
    link: str,
    comments: list[dict[str, Any]],
    system_prompt: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = now_iso()
    prompt = "\n".join(f"[赞{item['like_count']}] {item['author']}: {item['content']}" for item in comments)
    try:
        raw = generate_text(prompt, config=model_config, system=system_prompt)
        analysis = parse_model_json(raw)
        log_task(
            conn,
            workflow_run_id,
            "model-provider",
            "text.generate",
            {"link": shorten(link), "comments": len(comments)},
            compact_analysis(analysis),
            "success",
            started_at,
            started,
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        return analysis
    except Exception as exc:
        log_task(
            conn,
            workflow_run_id,
            "model-provider",
            "text.generate",
            {"link": shorten(link), "comments": len(comments)},
            {},
            "failed",
            started_at,
            started,
            str(exc),
            workflow_id=LINK_WORKFLOW_ID,
        )
        conn.commit()
        raise


def generate_report(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    model_config: dict[str, str],
    keyword: str,
    analyses: list[dict[str, Any]],
    system_prompt: str,
) -> str:
    started = time.perf_counter()
    started_at = now_iso()
    clean_text = build_report_input(analyses)
    if not clean_text.strip():
        clean_text = f"关键词：{keyword}\n本次没有可分析评论。"
    try:
        report = generate_text(clean_text, config=model_config, system=system_prompt)
        log_task(conn, workflow_run_id, "model-provider", "report.generate", {"keyword": keyword, "items": len(analyses)}, {"chars": len(report)}, "success", started_at, started)
        conn.commit()
        return report
    except Exception as exc:
        log_task(conn, workflow_run_id, "model-provider", "report.generate", {"keyword": keyword}, {}, "failed", started_at, started, str(exc))
        conn.commit()
        raise


def save_report_file(conn: sqlite3.Connection, workflow_run_id: str, keyword: str, report_text: str) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = now_iso()
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    safe_keyword = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", keyword).strip("_") or "xhs"
    filename = f"xhs_weekly_report_{safe_keyword}_{now_iso()[:10]}.md"
    path = UPLOAD_DIR / f"{file_id}_{filename}"
    path.write_text(report_text, encoding="utf-8")
    record = {
        "id": file_id,
        "filename": filename,
        "content_type": "text/markdown",
        "size_bytes": len(report_text.encode("utf-8")),
        "path": str(path),
    }
    conn.execute(
        """
        INSERT INTO files (id, filename, content_type, size_bytes, path, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (record["id"], record["filename"], record["content_type"], record["size_bytes"], record["path"], now_iso()),
    )
    log_task(conn, workflow_run_id, "local-file-store", "file.upload", {"filename": filename}, {"file_id": file_id, "bytes": record["size_bytes"]}, "success", started_at, started)
    conn.commit()
    return record


def build_note_context(note_item: dict[str, Any]) -> str:
    note = note_payload(note_item)
    title = note.get("title") or note.get("display_title") or note.get("desc") or ""
    content = note.get("desc") or note.get("content") or ""
    fields = compact_fields(
        {
            "笔记ID": get_note_id(note_item),
            "标题": title,
            "正文": content,
            "评论数": note_comment_count(note_item),
        }
    )
    return "\n".join(f"{key}：{value}" for key, value in fields.items())


def normalize_option(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def normalize_ai_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "是", "启用"}:
        return "1"
    return "0"


def build_report_input(analyses: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, item in enumerate(analyses, start=1):
        note = note_payload(item["note"])
        analysis = item["analysis"]
        lines.append(
            "\n".join(
                [
                    f"【笔记{index}】",
                    f"笔记ID：{get_note_id(item['note'])}",
                    f"评论数：{len(item['comments'])}",
                    f"痛点摘要：{stringify_value(analysis.get('痛点摘要', '未涉及'))}",
                    f"功效期望：{stringify_value(analysis.get('功效期望', '未涉及'))}",
                    f"成分态度：{stringify_value(analysis.get('成分态度', '未涉及'))}",
                    f"竞品情报：{stringify_value(analysis.get('竞品情报', '未涉及'))}",
                    f"研发建议：{stringify_value(analysis.get('研发建议', '未涉及'))}",
                    f"备注：{stringify_value(analysis.get('备注', ''))}",
                ]
            )
        )
    return "\n\n".join(lines)


def parse_model_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?", "", clean).strip()
    clean = re.sub(r"```$", "", clean).strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("模型返回不是 JSON 对象")
    return parsed



def get_module_config(conn: sqlite3.Connection, module_id: str) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM module_configs WHERE module_id = ?", (module_id,)).fetchall()
    config = {row["key"]: row["value"] for row in rows}
    if module_id == MODULE_ID:
        env_fallbacks = {
            "tikhubToken": "XHS_TIKHUB_TOKEN",
            "tikhubBaseUrl": "XHS_TIKHUB_BASE_URL",
            "searchPath": "XHS_SEARCH_PATH",
            "commentsPath": "XHS_COMMENTS_PATH",
            "cursor": "XHS_COMMENT_CURSOR",
            "index": "XHS_COMMENT_INDEX",
            "pageArea": "XHS_COMMENT_PAGE_AREA",
            "sort_strategy": "XHS_COMMENT_SORT_STRATEGY",
            "detailAppToken": "XHS_DETAIL_APP_TOKEN",
            "detailTableId": "XHS_DETAIL_TABLE_ID",
            "reportAppToken": "XHS_REPORT_APP_TOKEN",
            "reportTableId": "XHS_REPORT_TABLE_ID",
            "defaultKeyword": "XHS_DEFAULT_KEYWORD",
            "maxNotes": "XHS_MAX_NOTES",
            "sortType": "XHS_SORT_TYPE",
            "timeFilter": "XHS_TIME_FILTER",
            "noteType": "XHS_NOTE_TYPE",
            "source": "XHS_SOURCE",
            "aiMode": "XHS_AI_MODE",
            "maxCommentsPerNote": "XHS_MAX_COMMENTS_PER_NOTE",
        }
        for key, env_name in env_fallbacks.items():
            config.setdefault(key, os.getenv(env_name, ""))
    if module_id == "feishu-sync":
        config.setdefault("appId", os.getenv("FEISHU_APP_ID", ""))
        config.setdefault("appSecret", os.getenv("FEISHU_APP_SECRET", ""))
    return config


def validate_config(config: dict[str, str]) -> None:
    missing = [key for key in ("tikhubToken",) if not config.get(key)]
    if missing:
        raise ValueError(f"TikHub config missing: {', '.join(missing)}")


def validate_link_config(config: dict[str, str], link: str, output_app_token: str, output_table_id: str) -> None:
    missing = []
    if not config.get("tikhubToken"):
        missing.append("tikhubToken")
    if not link:
        missing.append("小红书链接")
    if not output_app_token:
        missing.append("输出表 appToken")
    if not output_table_id:
        missing.append("输出表 tableId")
    if missing:
        raise ValueError(f"小红书链接分析配置缺失：{', '.join(missing)}")


def log_task(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    module_id: str,
    capability: str,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    status: str,
    started_at: str,
    started_perf: float,
    error_message: str | None = None,
    workflow_id: str = WORKFLOW_ID,
) -> None:
    conn.execute(
        """
        INSERT INTO task_logs (
            task_id, workflow_id, workflow_run_id, module_id, capability, input_summary,
            output_summary, started_at, ended_at, duration_ms, status, error_message, retry_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            f"task_{uuid.uuid4().hex[:12]}",
            workflow_id,
            workflow_run_id,
            module_id,
            capability,
            summarize(input_summary),
            summarize(output_summary),
            started_at,
            now_iso(),
            elapsed_ms(started_perf),
            status,
            error_message,
        ),
    )


def normalize_limit(value: Any, default: int = 5, maximum: int = 50) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def compact_analysis(value: dict[str, Any]) -> dict[str, Any]:
    return {key: stringify_value(value.get(key, ""))[:300] for key in DETAIL_FIELDS}


def summarize(value: Any) -> str:
    return to_json(value)


def elapsed_ms(started_perf: float) -> int:
    return int((time.perf_counter() - started_perf) * 1000)


def shorten(value: str, limit: int = 120) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
