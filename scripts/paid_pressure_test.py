from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tools.feishu_sync.client import FeishuApiError, FeishuClient  # noqa: E402


API_BASE = "http://127.0.0.1:8000"
TERMINAL_STATUSES = {"success", "partial_success", "failed", "skipped"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a paid multi-workflow pressure test through Feishu listeners.")
    parser.add_argument("--keyword", default="压力测试", help="Label written into test records.")
    parser.add_argument("--xhs-link", action="append", default=[], help="Xiaohongshu link. Pass twice to avoid auto-detect.")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds to wait for queue tasks.")
    parser.add_argument("--dry-run", action="store_true", help="Only check configuration. Do not create Feishu records.")
    args = parser.parse_args()

    health = api_get("/api/health")
    if health.get("status") != "ok":
        raise RuntimeError("Backend is not healthy")

    feishu_config = api_get("/api/modules/feishu-sync/config?reveal=1")["values"]
    listeners = api_get("/api/intake/listeners")
    by_workflow = {item.get("workflow_id"): item for item in listeners}

    required_listeners = ["xhs-link-analysis", "lead-import-to-feishu", "product-main-image"]
    missing_listeners = [item for item in required_listeners if item not in by_workflow]
    if missing_listeners:
        raise RuntimeError(f"Missing listeners: {', '.join(missing_listeners)}")
    unbound = [item for item in required_listeners if not by_workflow[item].get("app_token") or not by_workflow[item].get("table_id")]
    if unbound:
        raise RuntimeError(f"Listeners are not bound to Feishu tables: {', '.join(unbound)}")

    print("Backend OK")
    print("Listeners:")
    for workflow_id in required_listeners:
        listener = by_workflow[workflow_id]
        print(f"  - {workflow_id}: {listener['name']} / {listener.get('table_name')} / enabled={listener.get('enabled')}")

    if args.dry_run:
        print("Dry run complete. No paid task was created.")
        return 0

    client = FeishuClient(feishu_config["appId"], feishu_config["appSecret"], timeout=30)
    started_at = datetime.now().isoformat(timespec="seconds")
    created_record_ids: list[str] = []

    xhs_links = normalize_links(args.xhs_link)
    if len(xhs_links) < 2:
        xhs_links.extend(find_existing_xhs_links(client, by_workflow["xhs-link-analysis"]))
    xhs_links = normalize_links(xhs_links)[:2]
    if len(xhs_links) < 2:
        raise RuntimeError("Need two Xiaohongshu links. Re-run with --xhs-link <url> --xhs-link <url>.")

    print("Creating paid pressure-test records...")
    created_record_ids.extend(create_xhs_records(client, by_workflow["xhs-link-analysis"], xhs_links, args.keyword))
    created_record_ids.extend(create_csv_record(client, by_workflow["lead-import-to-feishu"], args.keyword))
    created_record_ids.extend(create_image_records(client, by_workflow["product-main-image"], args.keyword))

    print(f"Created records: {created_record_ids}")
    print("Triggering listener scans...")
    for workflow_id in required_listeners:
        listener_id = by_workflow[workflow_id]["id"]
        result = api_post(f"/api/intake/listeners/{listener_id}/scan", {})
        print(f"  - scan {workflow_id}: {result.get('status')} queued={result.get('queued_count')}")

    print("Waiting for queue tasks...")
    tasks = wait_for_records(created_record_ids, timeout_seconds=args.timeout)
    print_summary(tasks, started_at)
    return 0 if all(task.get("status") in {"success", "partial_success"} for task in tasks) else 2


def create_xhs_records(client: FeishuClient, listener: dict[str, Any], links: list[str], label: str) -> list[str]:
    full_fields_list = []
    minimal_fields_list = []
    for index, link in enumerate(links, start=1):
        minimal = compact(
            {
                listener["status_field"]: listener["pending_value"],
                listener["prompt_field"]: link,
            }
        )
        full_fields_list.append(
            compact(
                {
                    **minimal,
                    listener["note_field"]: f"{label} 小红书压力测试 {index}",
                }
            )
        )
        minimal_fields_list.append(minimal)
    result = batch_create_with_fallback(client, listener, full_fields_list, minimal_fields_list, "xhs-link-analysis")
    return result.get("record_ids", [])


def create_csv_record(client: FeishuClient, listener: dict[str, Any], label: str) -> list[str]:
    csv_path = PROJECT_ROOT / "samples" / "sample_leads.csv"
    if not csv_path.exists():
        raise RuntimeError(f"CSV sample not found: {csv_path}")
    upload = client.upload_bitable_file(listener["app_token"], str(csv_path), parent_type="bitable_file")
    full_fields = compact(
        {
            listener["status_field"]: listener["pending_value"],
            listener["file_field"]: [{"file_token": upload["file_token"]}],
            listener["submitter_field"]: "pressure-test",
            listener["note_field"]: f"{label} CSV 压力测试",
        }
    )
    minimal_fields = compact(
        {
            listener["status_field"]: listener["pending_value"],
            listener["file_field"]: [{"file_token": upload["file_token"]}],
        }
    )
    result = batch_create_with_fallback(client, listener, [full_fields], [minimal_fields], "lead-import-to-feishu")
    return result.get("record_ids", [])


def create_image_records(client: FeishuClient, listener: dict[str, Any], label: str) -> list[str]:
    prompts = [
        "Create a clean commercial product poster for a premium shampoo bottle on a fresh bathroom shelf, natural light, no watermark.",
        "Create a clean ecommerce main image for a skincare bottle, white background, soft shadow, premium minimal style, no watermark.",
    ]
    full_fields_list = []
    minimal_fields_list = []
    for index, prompt in enumerate(prompts, start=1):
        minimal = compact(
            {
                listener["status_field"]: listener["pending_value"],
                listener["product_name_field"]: f"{label}-image-{index}",
                listener["prompt_field"]: prompt,
            }
        )
        full_fields_list.append(
            compact(
                {
                    **minimal,
                    listener["product_category_field"]: "压力测试",
                    listener["aspect_ratio_field"]: "1:1",
                }
            )
        )
        minimal_fields_list.append(minimal)
    result = batch_create_with_fallback(client, listener, full_fields_list, minimal_fields_list, "product-main-image")
    return result.get("record_ids", [])


def batch_create_with_fallback(
    client: FeishuClient,
    listener: dict[str, Any],
    full_fields_list: list[dict[str, Any]],
    minimal_fields_list: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    try:
        return client.batch_create_records(listener["app_token"], listener["table_id"], full_fields_list)
    except FeishuApiError as exc:
        if "FieldNameNotFound" not in str(exc) and "1254045" not in str(exc):
            raise
        print(f"{label}: optional field missing in Feishu table, retrying with minimal fields.")
        return client.batch_create_records(listener["app_token"], listener["table_id"], minimal_fields_list)


def find_existing_xhs_links(client: FeishuClient, listener: dict[str, Any]) -> list[str]:
    page = client.list_records(listener["app_token"], listener["table_id"], page_size=50)
    links: list[str] = []
    field_name = listener["prompt_field"]
    for record in page.get("items", []):
        link = field_text((record.get("fields") or {}).get(field_name))
        if "xiaohongshu.com" in link:
            links.append(link)
    return links


def wait_for_records(record_ids: list[str], timeout_seconds: int) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    latest: list[dict[str, Any]] = []
    while time.time() < deadline:
        queue = api_get("/api/task-queue")
        latest = [
            task for task in queue
            if task.get("remote_record_id") in record_ids
        ]
        statuses = {task.get("status") for task in latest}
        print(f"  queue matched={len(latest)}/{len(record_ids)} statuses={sorted(statuses)}")
        if len(latest) >= len(record_ids) and all(task.get("status") in TERMINAL_STATUSES for task in latest):
            return latest
        time.sleep(10)
    return latest


def print_summary(tasks: list[dict[str, Any]], started_at: str) -> None:
    print("\nPressure test summary")
    print(f"Started at: {started_at}")
    for task in sorted(tasks, key=lambda item: item.get("created_at", "")):
        print(
            f"- {task.get('workflow_id')} / {task.get('remote_record_id')} / "
            f"{task.get('status')} / attempts={task.get('attempt_count')} / "
            f"error={task.get('error_message') or ''}"
        )


def api_get(path: str) -> Any:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(path: str, body: dict[str, Any]) -> Any:
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Local API HTTP {exc.code}: {detail}") from exc


def compact(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key and value not in ("", None, [], {})}


def normalize_links(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("link", "url", "text", "name", "value"):
            if value.get(key):
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return " ".join(field_text(item) for item in value if field_text(item)).strip()
    return str(value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
