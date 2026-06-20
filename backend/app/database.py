from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_ROOT / "data"
STORAGE_DIR = BACKEND_ROOT / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DB_PATH = DATA_DIR / "platform.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS modules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                last_error TEXT,
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                manifest_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                provider_module_id TEXT NOT NULL,
                fallback_module_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(provider_module_id) REFERENCES modules(id),
                FOREIGN KEY(fallback_module_id) REFERENCES modules(id)
            );

            CREATE TABLE IF NOT EXISTS module_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                is_secret INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(module_id, key),
                FOREIGN KEY(module_id) REFERENCES modules(id)
            );

            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                definition_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT NOT NULL,
                input_summary TEXT,
                output_summary TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_ms INTEGER,
                error_message TEXT,
                FOREIGN KEY(workflow_id) REFERENCES workflows(id)
            );

            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                workflow_run_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                input_summary TEXT,
                output_summary TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(workflow_id) REFERENCES workflows(id),
                FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(id),
                FOREIGN KEY(module_id) REFERENCES modules(id)
            );

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                lead_key TEXT NOT NULL UNIQUE,
                source_platform TEXT,
                inquiry_time TEXT,
                customer_name TEXT,
                contact_person TEXT,
                region TEXT,
                contact TEXT,
                product_title TEXT,
                raw_content TEXT,
                product TEXT,
                quantity TEXT,
                demand TEXT,
                missing_info TEXT,
                intent_level TEXT,
                suggested_reply TEXT,
                customer_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '待处理',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                customer_name TEXT,
                contact_person TEXT,
                region TEXT,
                contact TEXT,
                source_platform TEXT,
                lead_count INTEGER NOT NULL DEFAULT 0,
                pending_count INTEGER NOT NULL DEFAULT 0,
                latest_inquiry_time TEXT,
                latest_raw_content TEXT,
                customer_status TEXT,
                key_reason TEXT,
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_tasks (
                id TEXT PRIMARY KEY,
                product_name TEXT,
                product_category TEXT,
                product_image TEXT,
                reference_image TEXT,
                prompt TEXT,
                main_image_ratio TEXT,
                detail_page_ratio TEXT,
                main_image_status TEXT,
                detail_page_status TEXT,
                copy_status TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generated_assets (
                id TEXT PRIMARY KEY,
                product_task_id TEXT,
                asset_type TEXT NOT NULL,
                path TEXT NOT NULL,
                prompt TEXT,
                module_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(product_task_id) REFERENCES product_tasks(id),
                FOREIGN KEY(module_id) REFERENCES modules(id)
            );
            """
        )
        migrate_db(conn)
        seed_defaults(conn)


def migrate_db(conn: sqlite3.Connection) -> None:
    ensure_columns(
        conn,
        "leads",
        {
            "contact_person": "TEXT",
        },
    )
    ensure_columns(
        conn,
        "customers",
        {
            "contact_person": "TEXT",
            "source_platform": "TEXT",
            "latest_raw_content": "TEXT",
            "customer_status": "TEXT",
            "key_reason": "TEXT",
        },
    )


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, column_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def seed_defaults(conn: sqlite3.Connection) -> None:
    current = now_iso()
    modules = [
        {
            "id": "local-database",
            "name": "本地数据库",
            "version": "1.0.0",
            "enabled": True,
            "status": "healthy",
            "capabilities": ["table.read", "table.write", "table.update"],
            "configSchema": {},
        },
        {
            "id": "local-file-store",
            "name": "本地文件存储",
            "version": "1.0.0",
            "enabled": True,
            "status": "healthy",
            "capabilities": ["file.upload", "file.download"],
            "configSchema": {"storagePath": "string"},
        },
        {
            "id": "lead-cleaner",
            "name": "线索清洗",
            "version": "1.0.0",
            "enabled": True,
            "status": "healthy",
            "capabilities": ["lead.normalize"],
            "configSchema": {},
        },
        {
            "id": "customer-merge",
            "name": "客户归并",
            "version": "1.0.0",
            "enabled": True,
            "status": "healthy",
            "capabilities": ["customer.merge"],
            "configSchema": {},
        },
        {
            "id": "feishu-sync",
            "name": "飞书同步",
            "version": "1.0.0",
            "enabled": True,
            "status": "needs_config",
            "capabilities": ["table.read", "table.write", "table.update", "file.upload"],
            "configSchema": {
                "appId": "string",
                "appSecret": "secret",
                "appToken": "string",
                "leadTableId": "string",
                "customerTableId": "string",
            },
        },
        {
            "id": "image-generator",
            "name": "图片生成",
            "version": "0.1.0",
            "enabled": False,
            "status": "disabled",
            "capabilities": ["image.generate"],
            "configSchema": {"apiKey": "secret", "model": "string"},
        },
        {
            "id": "text-generator",
            "name": "文案生成",
            "version": "0.1.0",
            "enabled": False,
            "status": "disabled",
            "capabilities": ["text.generate"],
            "configSchema": {"apiKey": "secret", "model": "string"},
        },
        {
            "id": "page-generator",
            "name": "详情页生成",
            "version": "0.1.0",
            "enabled": False,
            "status": "disabled",
            "capabilities": ["page.generate"],
            "configSchema": {"template": "string"},
        },
        {
            "id": "message-notifier",
            "name": "消息通知",
            "version": "0.1.0",
            "enabled": False,
            "status": "disabled",
            "capabilities": ["message.send"],
            "configSchema": {"webhookUrl": "secret"},
        },
    ]

    for module in modules:
        manifest = {
            "id": module["id"],
            "name": module["name"],
            "version": module["version"],
            "enabled": module["enabled"],
            "capabilities": module["capabilities"],
            "configSchema": module["configSchema"],
        }
        conn.execute(
            """
            INSERT OR IGNORE INTO modules (
                id, name, version, enabled, status, capabilities_json, manifest_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                module["id"],
                module["name"],
                module["version"],
                int(module["enabled"]),
                module["status"],
                to_json(module["capabilities"]),
                to_json(manifest),
                current,
                current,
            ),
        )

    capabilities = [
        ("table.read", "读取表格型数据", "feishu-sync", "local-database"),
        ("table.write", "写入表格型数据", "feishu-sync", "local-database"),
        ("table.update", "更新表格型数据", "feishu-sync", "local-database"),
        ("file.upload", "上传文件", "local-file-store", None),
        ("file.download", "下载文件", "local-file-store", None),
        ("message.send", "发送消息通知", "message-notifier", None),
        ("image.generate", "生成图片", "image-generator", None),
        ("text.generate", "生成文案", "text-generator", None),
        ("lead.normalize", "清洗并标准化线索", "lead-cleaner", None),
        ("customer.merge", "按客户身份归并客户", "customer-merge", None),
        ("page.generate", "生成商品详情页", "page-generator", None),
    ]
    for name, description, provider, fallback in capabilities:
        conn.execute(
            """
            INSERT OR IGNORE INTO capabilities (
                name, description, provider_module_id, fallback_module_id, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (name, description, provider, fallback, current, current),
        )

    definition = {
        "steps": [
            {"capability": "file.upload", "module": "local-file-store"},
            {"capability": "lead.normalize", "module": "lead-cleaner"},
            {"capability": "customer.merge", "module": "customer-merge"},
            {"capability": "table.write", "module": "feishu-sync", "target": "线索明细表"},
            {"capability": "table.write", "module": "feishu-sync", "target": "客户表"},
        ]
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO workflows (
            id, name, description, definition_json, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (
            "lead-import-to-feishu",
            "CSV 线索清洗与飞书同步",
            "上传 CSV，清洗线索，归并客户，并通过 table.write 能力同步到飞书表格。",
            to_json(definition),
            current,
            current,
        ),
    )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def module_manifest(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    result["capabilities"] = from_json(result.pop("capabilities_json"), [])
    result["manifest"] = from_json(result.pop("manifest_json"), {})
    return result


def capability_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    return result


def workflow_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    result["definition"] = from_json(result.pop("definition_json"), {})
    return result
