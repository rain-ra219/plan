from __future__ import annotations

import json
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.database import (
    capability_dict,
    from_json,
    get_conn,
    init_db,
    module_manifest,
    now_iso,
    row_to_dict,
    workflow_dict,
)
from app.lead_workflow import run_lead_import


ROOT = Path(__file__).resolve().parents[1]
STATIC_INDEX = ROOT / "static" / "index.html"


class DevHandler(BaseHTTPRequestHandler):
    server_version = "AutomationConsoleDev/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in ("/", "/index.html"):
                self.send_html(STATIC_INDEX.read_text(encoding="utf-8"))
            elif path == "/api/health":
                self.send_json({"status": "ok"})
            elif path == "/api/dashboard":
                self.send_json(get_dashboard())
            elif path == "/api/modules":
                self.send_json(list_modules())
            elif path.startswith("/api/modules/") and path.endswith("/config"):
                module_id = path.split("/")[3]
                self.send_json(get_module_config(module_id))
            elif path == "/api/capabilities":
                self.send_json(list_capabilities())
            elif path == "/api/workflows":
                self.send_json(list_workflows())
            elif path == "/api/workflow-runs":
                self.send_json(list_workflow_runs(limit_from(parsed.query, 50)))
            elif path == "/api/task-logs":
                self.send_json(list_task_logs(limit_from(parsed.query, 100)))
            elif path == "/api/leads":
                self.send_json(list_leads(limit_from(parsed.query, 100)))
            elif path == "/api/customers":
                self.send_json(list_customers(limit_from(parsed.query, 100)))
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "路径不存在")
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/workflows/lead-import/run":
                payload = self.read_json()
                with get_conn() as conn:
                    workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", ("lead-import-to-feishu",)).fetchone()
                    if not workflow or not workflow["enabled"]:
                        self.send_error_json(HTTPStatus.CONFLICT, "工作流未启用")
                        return
                    self.send_json(run_lead_import(conn, payload.get("filename", "leads.csv"), payload.get("content", "")))
            elif path.startswith("/api/modules/") and path.endswith("/test"):
                module_id = path.split("/")[3]
                self.send_json(test_module(module_id))
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "路径不存在")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/modules/"):
                module_id = path.split("/")[3]
                payload = self.read_json()
                self.send_json(toggle_module(module_id, bool(payload.get("enabled"))))
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "路径不存在")
        except KeyError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/modules/") and path.endswith("/config"):
                module_id = path.split("/")[3]
                payload = self.read_json()
                self.send_json(update_module_config(module_id, payload.get("values", {})))
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "路径不存在")
        except KeyError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_common_headers(content_type="text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, body: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_error_json(self, status: HTTPStatus, detail: str) -> None:
        self.send_json({"detail": detail}, status=status)

    def send_common_headers(self, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: object) -> None:
        return


def get_dashboard() -> dict:
    with get_conn() as conn:
        today = now_iso()[:10]
        run_counts = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                AVG(duration_ms) AS avg_duration
            FROM workflow_runs
            WHERE started_at LIKE ?
            """,
            (f"{today}%",),
        ).fetchone()
        abnormal_modules = conn.execute(
            """
            SELECT id, name, status, enabled, last_error
            FROM modules
            WHERE enabled = 0 OR status NOT IN ('healthy')
            ORDER BY enabled ASC, name ASC
            """
        ).fetchall()
        recent_runs = conn.execute("SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT 5").fetchall()
        recent_logs = conn.execute("SELECT * FROM task_logs ORDER BY started_at DESC LIMIT 6").fetchall()
        return {
            "todayTasks": run_counts["total"] or 0,
            "todaySuccess": run_counts["success"] or 0,
            "todayFailed": run_counts["failed"] or 0,
            "avgDurationMs": int(run_counts["avg_duration"] or 0),
            "abnormalModules": [row_to_dict(row) for row in abnormal_modules],
            "recentRuns": [row_to_dict(row) for row in recent_runs],
            "recentLogs": [row_to_dict(row) for row in recent_logs],
        }


def list_modules() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM modules ORDER BY enabled DESC, name ASC").fetchall()
        return [module_manifest(row) for row in rows]


def toggle_module(module_id: str, enabled: bool) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise KeyError("模块不存在")
        status = "healthy" if enabled else "disabled"
        if enabled and module_requires_config(row) and missing_config_keys(conn, module_id):
            status = "needs_config"
        conn.execute(
            "UPDATE modules SET enabled = ?, status = ?, updated_at = ? WHERE id = ?",
            (int(enabled), status, now_iso(), module_id),
        )
        conn.commit()
        return module_manifest(conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone())


def test_module(module_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise KeyError("模块不存在")
        if not row["enabled"]:
            status = "disabled"
            error = "模块已停用"
        else:
            missing = missing_config_keys(conn, module_id)
            if missing:
                status = "needs_config"
                error = f"缺少配置：{', '.join(missing)}"
            else:
                status = "healthy"
                error = None
        conn.execute(
            "UPDATE modules SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (status, error, now_iso(), module_id),
        )
        conn.commit()
        return {"moduleId": module_id, "status": status, "message": error or "连接检查通过"}


def get_module_config(module_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise KeyError("模块不存在")
        manifest = from_json(row["manifest_json"], {})
        configs = conn.execute(
            "SELECT key, value, is_secret FROM module_configs WHERE module_id = ? ORDER BY key",
            (module_id,),
        ).fetchall()
        values = {item["key"]: ("********" if item["is_secret"] else item["value"]) for item in configs}
        return {"module": module_manifest(row), "schema": manifest.get("configSchema", {}), "values": values}


def update_module_config(module_id: str, values: dict[str, str]) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if not row:
            raise KeyError("模块不存在")
        manifest = from_json(row["manifest_json"], {})
        schema = manifest.get("configSchema", {})
        for key, value in values.items():
            if key not in schema:
                continue
            if schema.get(key) == "secret" and value == "********":
                continue
            conn.execute(
                """
                INSERT INTO module_configs (module_id, key, value, is_secret, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id, key)
                DO UPDATE SET value = excluded.value, is_secret = excluded.is_secret, updated_at = excluded.updated_at
                """,
                (module_id, key, value, int(schema.get(key) == "secret"), now_iso(), now_iso()),
            )
        status = "healthy" if not missing_config_keys(conn, module_id) and row["enabled"] else row["status"]
        conn.execute("UPDATE modules SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), module_id))
        conn.commit()
    return get_module_config(module_id)


def list_capabilities() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM capabilities ORDER BY name ASC").fetchall()
        return [capability_dict(row) for row in rows]


def list_workflows() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY name ASC").fetchall()
        return [workflow_dict(row) for row in rows]


def list_workflow_runs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (min(max(limit, 1), 200),)).fetchall()
        return [row_to_dict(row) for row in rows]


def list_task_logs(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM task_logs ORDER BY started_at DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
        return [row_to_dict(row) for row in rows]


def list_leads(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY updated_at DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
        return [row_to_dict(row) for row in rows]


def list_customers(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM customers ORDER BY updated_at DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
        return [row_to_dict(row) for row in rows]


def module_requires_config(row: sqlite3.Row) -> bool:
    manifest = from_json(row["manifest_json"], {})
    return bool(manifest.get("configSchema"))


def missing_config_keys(conn: sqlite3.Connection, module_id: str) -> list[str]:
    row = conn.execute("SELECT manifest_json FROM modules WHERE id = ?", (module_id,)).fetchone()
    if not row:
        return []
    schema = from_json(row["manifest_json"], {}).get("configSchema", {})
    if not schema:
        return []
    existing = {
        item["key"]: item["value"]
        for item in conn.execute("SELECT key, value FROM module_configs WHERE module_id = ?", (module_id,)).fetchall()
    }
    required = [key for key, kind in schema.items() if kind in ("string", "secret")]
    return [key for key in required if not existing.get(key)]


def limit_from(query: str, default: int) -> int:
    values = parse_qs(query).get("limit", [])
    if not values:
        return default
    try:
        return int(values[0])
    except ValueError:
        return default


def main() -> None:
    init_db()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), DevHandler)
    print(f"AI automation console dev server: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
