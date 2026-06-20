from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .database import UPLOAD_DIR, now_iso, to_json


WORKFLOW_ID = "lead-import-to-feishu"


FIELD_ALIASES = {
    "source_platform": ["来源平台", "source_platform", "platform", "平台", "来源"],
    "inquiry_time": ["询盘时间", "inquiry_time", "time", "咨询时间", "创建时间"],
    "customer_name": ["客户名称", "customer_name", "客户", "客户昵称", "客户名", "公司名称", "姓名", "买家名称"],
    "contact_person": ["联系人", "contact_person", "contact_name", "联系人姓名"],
    "region": ["地区", "region", "国家", "国家/地区", "所在地"],
    "contact": ["联系方式", "contact", "手机", "电话", "邮箱", "email", "whatsapp", "WhatsApp"],
    "product_title": ["商品标题", "product_title", "商品名称", "产品标题", "产品名称", "product"],
    "raw_content": ["原始咨询内容", "raw_content", "咨询内容", "message", "需求内容", "留言"],
    "quantity": ["数量", "quantity", "qty", "采购数量"],
    "status": ["状态", "status", "当前状态", "线索状态"],
}

PENDING_STATUSES = {"待处理", "新线索", "新询盘", "已认领", "已联系", "待报价", "已报价", "跟进中"}


def run_lead_import(conn: sqlite3.Connection, filename: str, content: str) -> dict[str, Any]:
    workflow_run_id = f"run_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    conn.execute(
        """
        INSERT INTO workflow_runs (
            id, workflow_id, status, input_summary, started_at
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (workflow_run_id, WORKFLOW_ID, summarize({"filename": filename, "bytes": len(content.encode("utf-8"))}), started_at),
    )
    conn.commit()

    try:
        file_record = save_uploaded_file(conn, workflow_run_id, filename, content)
        rows = parse_csv(content)
        normalized = normalize_rows(rows)
        lead_result = upsert_leads(conn, workflow_run_id, normalized)
        customer_result = merge_customers(conn, workflow_run_id, lead_result["customer_ids"])
        lead_sync = sync_table(conn, workflow_run_id, "线索明细表", lead_result["affected_count"])
        customer_sync = sync_table(conn, workflow_run_id, "客户表", customer_result["affected_count"])

        output = {
            "file_id": file_record["id"],
            "rows": len(rows),
            "leads": lead_result,
            "customers": customer_result,
            "feishu": {"leads": lead_sync, "customers": customer_sync},
        }
        ended_at = now_iso()
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = 'success', output_summary = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (summarize(output), ended_at, elapsed_ms(started), workflow_run_id),
        )
        conn.commit()
        return {"workflow_run_id": workflow_run_id, "status": "success", **output}
    except Exception as exc:
        ended_at = now_iso()
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = 'failed', error_message = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (str(exc), ended_at, elapsed_ms(started), workflow_run_id),
        )
        log_task(
            conn,
            workflow_run_id=workflow_run_id,
            module_id="workflow-engine",
            capability="workflow.run",
            input_summary=summarize({"filename": filename}),
            output_summary="",
            status="failed",
            error_message=str(exc),
            started_at=started_at,
            started_perf=started,
        )
        conn.commit()
        raise


def save_uploaded_file(conn: sqlite3.Connection, workflow_run_id: str, filename: str, content: str) -> dict[str, Any]:
    start = time.perf_counter()
    started_at = now_iso()
    safe_name = Path(filename).name or "upload.csv"
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    path = UPLOAD_DIR / f"{file_id}_{safe_name}"
    path.write_text(content, encoding="utf-8")
    record = {
        "id": file_id,
        "filename": safe_name,
        "content_type": "text/csv",
        "size_bytes": len(content.encode("utf-8")),
        "path": str(path),
    }
    conn.execute(
        """
        INSERT INTO files (id, filename, content_type, size_bytes, path, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (record["id"], record["filename"], record["content_type"], record["size_bytes"], record["path"], now_iso()),
    )
    log_task(
        conn,
        workflow_run_id=workflow_run_id,
        module_id="local-file-store",
        capability="file.upload",
        input_summary=summarize({"filename": safe_name, "bytes": record["size_bytes"]}),
        output_summary=summarize({"file_id": file_id}),
        status="success",
        started_at=started_at,
        started_perf=start,
    )
    conn.commit()
    return record


def parse_csv(content: str) -> list[dict[str, str]]:
    text = content.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("CSV 内容为空")

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV 缺少表头")

    rows = []
    for row in reader:
        normalized = {clean_key(key): clean_value(value) for key, value in row.items() if key is not None}
        if any(normalized.values()):
            rows.append(normalized)
    if not rows:
        raise ValueError("CSV 没有可处理的数据行")
    return rows


def normalize_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [normalize_row(row) for row in rows]


def normalize_row(row: dict[str, str]) -> dict[str, Any]:
    source_platform = pick(row, "source_platform") or "未知平台"
    inquiry_time = pick(row, "inquiry_time") or now_iso()
    contact_person = pick(row, "contact_person")
    customer_name = pick(row, "customer_name") or contact_person or "未知客户"
    region = pick(row, "region")
    contact = normalize_contact(pick(row, "contact"))
    product_title = pick(row, "product_title")
    raw_content = pick(row, "raw_content")

    product = detect_product(product_title, raw_content)
    quantity = normalize_quantity(pick(row, "quantity")) or detect_quantity(raw_content)
    missing_info = detect_missing_info(contact, region, product, quantity, raw_content)
    intent_level = detect_intent(raw_content, quantity)
    suggested_reply = build_suggested_reply(customer_name, missing_info, intent_level)
    customer_id = build_customer_id(contact, customer_name, region)
    lead_key = build_lead_key(source_platform, inquiry_time, customer_name, product_title, raw_content)
    status = pick(row, "status") or "新线索"

    return {
        "id": f"lead_{hash_text(lead_key)[:12]}",
        "lead_key": lead_key,
        "source_platform": source_platform,
        "inquiry_time": inquiry_time,
        "customer_name": customer_name,
        "contact_person": contact_person,
        "region": region,
        "contact": contact,
        "product_title": product_title,
        "raw_content": raw_content,
        "product": product,
        "quantity": quantity,
        "demand": detect_demand(raw_content),
        "missing_info": "、".join(missing_info),
        "intent_level": intent_level,
        "suggested_reply": suggested_reply,
        "customer_id": customer_id,
        "status": status,
    }


def upsert_leads(conn: sqlite3.Connection, workflow_run_id: str, leads: list[dict[str, Any]]) -> dict[str, Any]:
    start = time.perf_counter()
    started_at = now_iso()
    inserted = 0
    updated = 0
    customer_ids: set[str] = set()

    for lead in leads:
        customer_ids.add(lead["customer_id"])
        existing = conn.execute("SELECT id FROM leads WHERE lead_key = ?", (lead["lead_key"],)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE leads
                SET source_platform = ?, inquiry_time = ?, customer_name = ?, contact_person = ?, region = ?, contact = ?,
                    product_title = ?, raw_content = ?, product = ?, quantity = ?, demand = ?,
                    missing_info = ?, intent_level = ?, suggested_reply = ?, customer_id = ?, status = ?, updated_at = ?
                WHERE lead_key = ?
                """,
                (
                    lead["source_platform"],
                    lead["inquiry_time"],
                    lead["customer_name"],
                    lead["contact_person"],
                    lead["region"],
                    lead["contact"],
                    lead["product_title"],
                    lead["raw_content"],
                    lead["product"],
                    lead["quantity"],
                    lead["demand"],
                    lead["missing_info"],
                    lead["intent_level"],
                    lead["suggested_reply"],
                    lead["customer_id"],
                    lead["status"],
                    now_iso(),
                    lead["lead_key"],
                ),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO leads (
                    id, lead_key, source_platform, inquiry_time, customer_name, contact_person, region, contact,
                    product_title, raw_content, product, quantity, demand, missing_info,
                    intent_level, suggested_reply, customer_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead["id"],
                    lead["lead_key"],
                    lead["source_platform"],
                    lead["inquiry_time"],
                    lead["customer_name"],
                    lead["contact_person"],
                    lead["region"],
                    lead["contact"],
                    lead["product_title"],
                    lead["raw_content"],
                    lead["product"],
                    lead["quantity"],
                    lead["demand"],
                    lead["missing_info"],
                    lead["intent_level"],
                    lead["suggested_reply"],
                    lead["customer_id"],
                    lead["status"],
                    now_iso(),
                    now_iso(),
                ),
            )
            inserted += 1

    result = {"inserted": inserted, "updated": updated, "affected_count": inserted + updated, "customer_ids": sorted(customer_ids)}
    log_task(
        conn,
        workflow_run_id=workflow_run_id,
        module_id="lead-cleaner",
        capability="lead.normalize",
        input_summary=summarize({"rows": len(leads)}),
        output_summary=summarize({k: v for k, v in result.items() if k != "customer_ids"}),
        status="success",
        started_at=started_at,
        started_perf=start,
    )
    conn.commit()
    return result


def merge_customers(conn: sqlite3.Connection, workflow_run_id: str, customer_ids: list[str]) -> dict[str, Any]:
    start = time.perf_counter()
    started_at = now_iso()
    affected = 0
    for customer_id in customer_ids:
        rows = conn.execute(
            """
            SELECT customer_name, contact_person, region, contact, source_platform, inquiry_time, product_title, raw_content, status
            FROM leads
            WHERE customer_id = ?
            ORDER BY inquiry_time DESC
            """,
            (customer_id,),
        ).fetchall()
        if not rows:
            continue
        first = rows[0]
        earliest = rows[-1]
        lead_count = len(rows)
        pending_count = sum(1 for row in rows if is_pending_status(row["status"]))
        latest_inquiry_time = first["inquiry_time"]
        latest_raw_content = first["raw_content"]
        products = []
        for row in rows[:5]:
            title = row["product_title"]
            if title and title not in products:
                products.append(title)
        customer_status = "已处理"
        if pending_count > 1:
            customer_status = "多线索待处理"
        elif pending_count == 1:
            customer_status = "待处理"
        key_reason = "多线索客户" if lead_count > 1 else ""
        summary = f"{lead_count} 条线索，{pending_count} 条待处理"
        if products:
            summary += f"，关注商品：{'、'.join(products)}"

        existing = conn.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE customers
                SET customer_name = ?, contact_person = ?, region = ?, contact = ?, source_platform = ?,
                    lead_count = ?, pending_count = ?, latest_inquiry_time = ?, latest_raw_content = ?,
                    customer_status = ?, key_reason = ?, summary = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    first["customer_name"],
                    first["contact_person"],
                    first["region"],
                    first["contact"],
                    earliest["source_platform"],
                    lead_count,
                    pending_count,
                    latest_inquiry_time,
                    latest_raw_content,
                    customer_status,
                    key_reason,
                    summary,
                    now_iso(),
                    customer_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO customers (
                    id, customer_name, contact_person, region, contact, source_platform, lead_count, pending_count,
                    latest_inquiry_time, latest_raw_content, customer_status, key_reason, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_id,
                    first["customer_name"],
                    first["contact_person"],
                    first["region"],
                    first["contact"],
                    earliest["source_platform"],
                    lead_count,
                    pending_count,
                    latest_inquiry_time,
                    latest_raw_content,
                    customer_status,
                    key_reason,
                    summary,
                    now_iso(),
                    now_iso(),
                ),
            )
        affected += 1

    result = {"affected_count": affected}
    log_task(
        conn,
        workflow_run_id=workflow_run_id,
        module_id="customer-merge",
        capability="customer.merge",
        input_summary=summarize({"customer_ids": len(customer_ids)}),
        output_summary=summarize(result),
        status="success",
        started_at=started_at,
        started_perf=start,
    )
    conn.commit()
    return result


def sync_table(conn: sqlite3.Connection, workflow_run_id: str, table_name: str, row_count: int) -> dict[str, Any]:
    start = time.perf_counter()
    started_at = now_iso()
    module = conn.execute("SELECT * FROM modules WHERE id = 'feishu-sync'").fetchone()
    config = get_module_config(conn, "feishu-sync")
    required = ["appId", "appSecret", "appToken"]
    missing = [key for key in required if not config.get(key)]

    if not module or not module["enabled"]:
        status = "skipped"
        output = {"target": table_name, "rows": row_count, "reason": "飞书同步模块已停用，数据保留在本地数据库"}
    elif missing:
        status = "skipped"
        output = {"target": table_name, "rows": row_count, "reason": f"飞书配置缺失：{', '.join(missing)}，数据保留在本地数据库"}
    else:
        status = "skipped"
        output = {"target": table_name, "rows": row_count, "reason": "飞书 API 适配器尚未实现，数据保留在本地数据库"}

    log_task(
        conn,
        workflow_run_id=workflow_run_id,
        module_id="feishu-sync",
        capability="table.write",
        input_summary=summarize({"target": table_name, "rows": row_count}),
        output_summary=summarize(output),
        status=status,
        started_at=started_at,
        started_perf=start,
    )
    conn.commit()
    return {"status": status, **output}


def log_task(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    module_id: str,
    capability: str,
    input_summary: str,
    output_summary: str,
    status: str,
    started_at: str,
    started_perf: float,
    error_message: str | None = None,
    retry_count: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO task_logs (
            task_id, workflow_id, workflow_run_id, module_id, capability, input_summary,
            output_summary, started_at, ended_at, duration_ms, status, error_message, retry_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"task_{uuid.uuid4().hex[:12]}",
            WORKFLOW_ID,
            workflow_run_id,
            module_id,
            capability,
            input_summary,
            output_summary,
            started_at,
            now_iso(),
            elapsed_ms(started_perf),
            status,
            error_message,
            retry_count,
        ),
    )


def get_module_config(conn: sqlite3.Connection, module_id: str) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM module_configs WHERE module_id = ?", (module_id,)).fetchall()
    return {row["key"]: row["value"] for row in rows}


def summarize(value: Any, max_chars: int = 700) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = to_json(value)
    return text if len(text) <= max_chars else f"{text[:max_chars]}..."


def elapsed_ms(started_perf: float) -> int:
    return int((time.perf_counter() - started_perf) * 1000)


def pick(row: dict[str, str], field: str) -> str:
    for alias in FIELD_ALIASES[field]:
        key = clean_key(alias)
        if key in row and row[key]:
            return row[key].strip()
    lowered = {key.lower(): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field]:
        key = clean_key(alias).lower()
        if key in lowered and lowered[key]:
            return lowered[key].strip()
    return ""


def clean_key(value: str) -> str:
    return str(value or "").strip().replace("\ufeff", "")


def clean_value(value: Any) -> str:
    return str(value or "").strip()


def normalize_contact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def normalize_quantity(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value


def detect_product(product_title: str, raw_content: str) -> str:
    if product_title:
        return product_title[:120]
    content = raw_content or ""
    match = re.search(r"(?:产品|商品|product)[:：]?\s*([\w\u4e00-\u9fff\- ]{2,60})", content, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def detect_quantity(raw_content: str) -> str:
    content = raw_content or ""
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(pcs|pieces|units|sets|kg|g|tons|件|个|套|台|箱|公斤|千克|吨)",
        content,
        flags=re.IGNORECASE,
    )
    return match.group(0) if match else ""


def detect_demand(raw_content: str) -> str:
    content = (raw_content or "").strip()
    if not content:
        return ""
    return content[:180]


def detect_missing_info(contact: str, region: str, product: str, quantity: str, raw_content: str) -> list[str]:
    missing = []
    if not contact:
        missing.append("联系方式")
    if not region:
        missing.append("地区")
    if not product:
        missing.append("产品")
    if not quantity:
        missing.append("数量")
    if not raw_content:
        missing.append("原始咨询内容")
    return missing


def detect_intent(raw_content: str, quantity: str) -> str:
    content = (raw_content or "").lower()
    high_words = ["报价", "价格", "采购", "批量", "下单", "quote", "price", "order", "urgent", "buy"]
    middle_words = ["样品", "规格", "参数", "库存", "sample", "spec", "catalog"]
    if quantity or any(word in content for word in high_words):
        return "高"
    if any(word in content for word in middle_words):
        return "中"
    return "低"


def is_pending_status(status: str) -> bool:
    return (status or "").strip() in PENDING_STATUSES


def build_suggested_reply(customer_name: str, missing_info: list[str], intent_level: str) -> str:
    prefix = f"{customer_name}您好，" if customer_name and customer_name != "未知客户" else "您好，"
    if missing_info:
        return f"{prefix}已收到您的咨询。为便于准确报价，请补充{'、'.join(missing_info)}。"
    if intent_level == "高":
        return f"{prefix}已收到您的需求，我们将尽快确认价格、交期和可选方案。"
    return f"{prefix}已收到您的咨询，我们会进一步确认需求并提供匹配方案。"


def build_customer_id(contact: str, customer_name: str, region: str) -> str:
    if contact:
        basis = f"contact:{contact.lower()}"
    else:
        basis = f"name-region:{customer_name.lower()}:{region.lower()}"
    return f"cus_{hash_text(basis)[:12]}"


def build_lead_key(source_platform: str, inquiry_time: str, customer_name: str, product_title: str, raw_content: str) -> str:
    return "|".join(
        [
            normalize_key_part(source_platform),
            normalize_key_part(inquiry_time),
            normalize_key_part(customer_name),
            normalize_key_part(product_title),
            normalize_key_part(raw_content),
        ]
    )


def normalize_key_part(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()
