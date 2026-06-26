from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_ROOT / "data"
STORAGE_DIR = BACKEND_ROOT / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DB_PATH = DATA_DIR / "platform.db"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
                main_image_asset_id TEXT,
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

            CREATE TABLE IF NOT EXISTS feishu_bases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                app_token TEXT NOT NULL UNIQUE,
                description TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feishu_tables (
                id TEXT PRIMARY KEY,
                base_id TEXT NOT NULL,
                name TEXT NOT NULL,
                table_id TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT '',
                field_mapping_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(base_id, table_id),
                FOREIGN KEY(base_id) REFERENCES feishu_bases(id)
            );

            CREATE TABLE IF NOT EXISTS external_record_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT NOT NULL,
                source_table TEXT NOT NULL,
                local_record_id TEXT NOT NULL,
                remote_app_token TEXT,
                remote_table_id TEXT NOT NULL,
                remote_record_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(module_id, source_table, local_record_id),
                FOREIGN KEY(module_id) REFERENCES modules(id)
            );

            CREATE TABLE IF NOT EXISTS intake_listener_state (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '飞书 CSV 监听',
                base_id TEXT,
                table_config_id TEXT,
                workflow_id TEXT NOT NULL DEFAULT 'lead-import-to-feishu',
                enabled INTEGER NOT NULL DEFAULT 0,
                interval_seconds INTEGER NOT NULL DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'stopped',
                last_scan_at TEXT,
                next_scan_at TEXT,
                last_error TEXT,
                status_field TEXT NOT NULL DEFAULT '处理状态',
                file_field TEXT NOT NULL DEFAULT 'CSV 文件',
                submitter_field TEXT NOT NULL DEFAULT '提交人',
                note_field TEXT NOT NULL DEFAULT '提交说明',
                product_name_field TEXT NOT NULL DEFAULT '商品名称',
                product_category_field TEXT NOT NULL DEFAULT '商品分类',
                product_image_field TEXT NOT NULL DEFAULT '产品图',
                prompt_field TEXT NOT NULL DEFAULT '图片提示词',
                aspect_ratio_field TEXT NOT NULL DEFAULT '生成比例',
                reference_image_field TEXT NOT NULL DEFAULT '参考图片',
                product_description_field TEXT NOT NULL DEFAULT '产品图描述',
                reference_style_field TEXT NOT NULL DEFAULT '参考图风格描述',
                final_prompt_field TEXT NOT NULL DEFAULT '最终提示词',
                result_field TEXT NOT NULL DEFAULT '处理结果',
                run_id_field TEXT NOT NULL DEFAULT '工作流ID',
                error_field TEXT NOT NULL DEFAULT '错误信息',
                processed_at_field TEXT NOT NULL DEFAULT '处理时间',
                pending_value TEXT NOT NULL DEFAULT '待处理',
                processing_value TEXT NOT NULL DEFAULT '处理中',
                success_value TEXT NOT NULL DEFAULT '处理成功',
                partial_value TEXT NOT NULL DEFAULT '部分成功',
                failed_value TEXT NOT NULL DEFAULT '处理失败',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(base_id) REFERENCES feishu_bases(id),
                FOREIGN KEY(table_config_id) REFERENCES feishu_tables(id),
                FOREIGN KEY(workflow_id) REFERENCES workflows(id)
            );

            CREATE TABLE IF NOT EXISTS intake_runs (
                id TEXT PRIMARY KEY,
                listener_id TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                status TEXT NOT NULL,
                scanned_count INTEGER NOT NULL DEFAULT 0,
                processed_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                partial_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                input_summary TEXT,
                output_summary TEXT,
                error_message TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_ms INTEGER,
                FOREIGN KEY(listener_id) REFERENCES intake_listener_state(id)
            );

            CREATE TABLE IF NOT EXISTS intake_record_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intake_run_id TEXT NOT NULL,
                remote_record_id TEXT NOT NULL,
                filename TEXT,
                submitted_by TEXT,
                note TEXT,
                workflow_run_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(intake_run_id) REFERENCES intake_runs(id),
                FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(id)
            );

            CREATE TABLE IF NOT EXISTS mcp_servers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                transport TEXT NOT NULL DEFAULT 'http',
                endpoint_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                last_error TEXT,
                last_connected_at TEXT,
                tools_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mcp_tool_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                capability TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(server_id, tool_name, capability),
                FOREIGN KEY(server_id) REFERENCES mcp_servers(id)
            );

            CREATE TABLE IF NOT EXISTS mcp_call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                capability TEXT,
                input_summary TEXT,
                output_summary TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                FOREIGN KEY(server_id) REFERENCES mcp_servers(id)
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
    ensure_columns(
        conn,
        "mcp_servers",
        {
            "last_connected_at": "TEXT",
            "tools_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    )
    ensure_columns(
        conn,
        "product_tasks",
        {
            "main_image_asset_id": "TEXT",
        },
    )
    ensure_columns(
        conn,
        "intake_listener_state",
        {
            "name": "TEXT NOT NULL DEFAULT '飞书 CSV 监听'",
            "base_id": "TEXT",
            "table_config_id": "TEXT",
            "workflow_id": "TEXT NOT NULL DEFAULT 'lead-import-to-feishu'",
            "status_field": "TEXT NOT NULL DEFAULT '处理状态'",
            "file_field": "TEXT NOT NULL DEFAULT 'CSV 文件'",
            "submitter_field": "TEXT NOT NULL DEFAULT '提交人'",
            "note_field": "TEXT NOT NULL DEFAULT '提交说明'",
            "product_name_field": "TEXT NOT NULL DEFAULT '商品名称'",
            "product_category_field": "TEXT NOT NULL DEFAULT '商品分类'",
            "product_image_field": "TEXT NOT NULL DEFAULT '产品图'",
            "prompt_field": "TEXT NOT NULL DEFAULT '图片提示词'",
            "aspect_ratio_field": "TEXT NOT NULL DEFAULT '生成比例'",
            "reference_image_field": "TEXT NOT NULL DEFAULT '参考图片'",
            "product_description_field": "TEXT NOT NULL DEFAULT '产品图描述'",
            "reference_style_field": "TEXT NOT NULL DEFAULT '参考图风格描述'",
            "final_prompt_field": "TEXT NOT NULL DEFAULT '最终提示词'",
            "result_field": "TEXT NOT NULL DEFAULT '处理结果'",
            "run_id_field": "TEXT NOT NULL DEFAULT '工作流ID'",
            "error_field": "TEXT NOT NULL DEFAULT '错误信息'",
            "processed_at_field": "TEXT NOT NULL DEFAULT '处理时间'",
            "pending_value": "TEXT NOT NULL DEFAULT '待处理'",
            "processing_value": "TEXT NOT NULL DEFAULT '处理中'",
            "success_value": "TEXT NOT NULL DEFAULT '处理成功'",
            "partial_value": "TEXT NOT NULL DEFAULT '部分成功'",
            "failed_value": "TEXT NOT NULL DEFAULT '处理失败'",
        },
    )


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, column_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def seed_feishu_registry(conn: sqlite3.Connection, current: str) -> None:
    config = {
        item["key"]: item["value"]
        for item in conn.execute(
            "SELECT key, value FROM module_configs WHERE module_id = 'feishu-sync'"
        ).fetchall()
    }
    config.setdefault("appToken", os.getenv("FEISHU_BITABLE_APP_TOKEN", ""))
    config.setdefault("leadTableId", os.getenv("FEISHU_BITABLE_TABLE_ID", ""))
    config.setdefault("customerTableId", os.getenv("FEISHU_CUSTOMER_TABLE_ID", ""))
    config.setdefault("intakeTableId", os.getenv("FEISHU_INTAKE_TABLE_ID", ""))

    app_token = config.get("appToken", "").strip()
    if not app_token:
        return

    base_id = stable_id("base", app_token)
    conn.execute(
        """
        INSERT INTO feishu_bases (
            id, name, app_token, description, enabled, created_at, updated_at
        ) VALUES (?, '默认销售自动化 Base', ?, '从旧飞书同步配置自动迁移', 1, ?, ?)
        ON CONFLICT(app_token) DO UPDATE SET updated_at = excluded.updated_at
        """,
        (base_id, app_token, current, current),
    )
    base_row = conn.execute("SELECT id FROM feishu_bases WHERE app_token = ?", (app_token,)).fetchone()
    if base_row:
        base_id = base_row["id"]

    legacy_tables = [
        ("线索明细表", config.get("leadTableId", ""), "lead_detail"),
        ("客户表", config.get("customerTableId", ""), "customer"),
        ("CSV 提交任务表", config.get("intakeTableId", ""), "csv_intake"),
    ]
    created_tables: dict[str, str] = {}
    for name, table_id, purpose in legacy_tables:
        table_id = table_id.strip()
        if not table_id:
            continue
        table_config_id = stable_id("tblcfg", f"{base_id}:{table_id}")
        conn.execute(
            """
            INSERT INTO feishu_tables (
                id, base_id, name, table_id, purpose, field_mapping_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?)
            ON CONFLICT(base_id, table_id) DO UPDATE SET
                name = excluded.name,
                purpose = excluded.purpose,
                updated_at = excluded.updated_at
            """,
            (table_config_id, base_id, name, table_id, purpose, current, current),
        )
        row = conn.execute(
            "SELECT id FROM feishu_tables WHERE base_id = ? AND table_id = ?",
            (base_id, table_id),
        ).fetchone()
        if row:
            created_tables[purpose] = row["id"]

    intake_table_id = created_tables.get("csv_intake")
    if intake_table_id:
        conn.execute(
            """
            UPDATE intake_listener_state
            SET base_id = COALESCE(base_id, ?),
                table_config_id = COALESCE(table_config_id, ?),
                workflow_id = COALESCE(workflow_id, 'lead-import-to-feishu'),
                updated_at = ?
            WHERE id = 'feishu-form-csv'
            """,
            (base_id, intake_table_id, current),
        )


def stable_id(prefix: str, value: str) -> str:
    import hashlib

    return f"{prefix}_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


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
            },
        },
        {
            "id": "image-generator",
            "name": "图片生成",
            "version": "0.1.0",
            "enabled": False,
            "status": "disabled",
            "capabilities": ["image.generate"],
            "configSchema": {
                "apiKey": "secret",
                "baseUrl": "optional",
                "model": "string",
                "authMode": "optional",
                "providerMode": "optional",
            },
        },
        {
            "id": "model-provider",
            "name": "模型",
            "version": "0.1.0",
            "enabled": False,
            "status": "disabled",
            "capabilities": ["image.describe", "text.generate", "prompt.compose"],
            "configSchema": {
                "apiKey": "secret",
                "baseUrl": "string",
                "model": "string",
                "authMode": "optional",
                "providerMode": "optional",
            },
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
        {
            "id": "mcp-bridge",
            "name": "MCP 能力桥接",
            "version": "0.1.0",
            "enabled": True,
            "status": "healthy",
            "capabilities": ["mcp.server.manage", "mcp.tools.discover", "mcp.tool.call"],
            "configSchema": {},
        },
        {
            "id": "product-main-image",
            "name": "商品主图生成",
            "version": "0.1.0",
            "enabled": True,
            "status": "healthy",
            "capabilities": ["workflow.product_main_image.run", "workflow.product_main_detail.run"],
            "configSchema": {},
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
        conn.execute(
            """
            UPDATE modules
            SET name = ?, version = ?, capabilities_json = ?, manifest_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                module["name"],
                module["version"],
                to_json(module["capabilities"]),
                to_json(manifest),
                current,
                module["id"],
            ),
        )

    capabilities = [
        ("table.read", "读取表格型数据", "feishu-sync", "local-database"),
        ("table.write", "写入表格型数据", "feishu-sync", "local-database"),
        ("table.update", "更新表格型数据", "feishu-sync", "local-database"),
        ("file.upload", "上传文件", "local-file-store", None),
        ("file.download", "下载文件", "local-file-store", None),
        ("message.send", "发送消息通知", "message-notifier", None),
        ("image.describe", "理解图片并生成结构化描述", "model-provider", None),
        ("image.generate", "生成图片", "image-generator", None),
        ("prompt.compose", "组合并增强提示词", "model-provider", None),
        ("text.generate", "生成文案", "model-provider", "text-generator"),
        ("lead.normalize", "清洗并标准化线索", "lead-cleaner", None),
        ("customer.merge", "按客户身份归并客户", "customer-merge", None),
        ("page.generate", "生成商品详情页", "page-generator", None),
        ("mcp.server.manage", "管理 MCP 服务连接", "mcp-bridge", None),
        ("mcp.tools.discover", "发现 MCP 服务提供的工具", "mcp-bridge", None),
        ("mcp.tool.call", "调用 MCP 工具并记录日志", "mcp-bridge", None),
        ("workflow.product_main_image.run", "运行商品主图生成工作流", "product-main-image", None),
        ("workflow.product_main_detail.run", "运行主图详情页生成工作流", "product-main-image", None),
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
        conn.execute(
            """
            UPDATE capabilities
            SET description = ?, provider_module_id = ?, fallback_module_id = ?, updated_at = ?
            WHERE name = ?
            """,
            (description, provider, fallback, current, name),
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
    product_definition = {
        "steps": [
            {"capability": "image.generate", "module": "image-generator"},
            {"capability": "file.upload", "module": "local-file-store", "target": "generated_assets"},
        ]
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO workflows (
            id, name, description, definition_json, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (
            "product-main-image",
            "商品主图一键生成",
            "创建商品任务，调用 image.generate 能力生成主图，并保存到本地资产库。",
            to_json(product_definition),
            current,
            current,
        ),
    )
    detail_product_definition = {
        "steps": [
            {"capability": "image.describe", "module": "model-provider", "target": "产品图"},
            {"capability": "image.describe", "module": "model-provider", "target": "参考图"},
            {"capability": "prompt.compose", "module": "model-provider", "target": "最终提示词"},
            {"capability": "image.generate", "module": "image-generator", "target": "主图结果"},
            {"capability": "file.upload", "module": "local-file-store", "target": "generated_assets"},
        ]
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO workflows (
            id, name, description, definition_json, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (
            "product-main-detail",
            "主图详情页生成",
            "读取产品图、参考图和主图提示词，先通过模型反推产品与风格描述，再调用 image.generate 生成主图并回写飞书主图结果字段。",
            to_json(detail_product_definition),
            current,
            current,
        ),
    )
    conn.execute(
        """
        UPDATE workflows
        SET description = ?, definition_json = ?, updated_at = ?
        WHERE id = 'product-main-detail'
        """,
        (
            "读取产品图、参考图和主图提示词，先通过模型反推产品与风格描述，再调用 image.generate 生成主图并回写飞书主图结果字段。",
            to_json(detail_product_definition),
            current,
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO intake_listener_state (
            id, name, workflow_id, enabled, interval_seconds, status, created_at, updated_at
        ) VALUES ('feishu-form-csv', 'CSV 线索导入监听', 'lead-import-to-feishu', 0, 60, 'stopped', ?, ?)
        """,
        (current, current),
    )
    seed_feishu_registry(conn, current)


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


def feishu_base_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    return result


def feishu_table_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["field_mapping"] = from_json(result.pop("field_mapping_json"), {})
    return result


def intake_listener_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    return result


def mcp_server_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    result["tools"] = from_json(result.pop("tools_json"), [])
    return result


def mcp_mapping_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["enabled"] = bool(result["enabled"])
    return result


def mcp_call_log_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = row_to_dict(row)
    result["input"] = from_json(result.pop("input_summary"), {})
    result["output"] = from_json(result.pop("output_summary"), {})
    return result
