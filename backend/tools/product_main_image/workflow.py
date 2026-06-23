from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from app import database as db
from app.database import from_json, now_iso, row_to_dict, to_json
from tools.image_generate.service import ImageGenerateError, generate_image


WORKFLOW_ID = "product-main-image"


def create_product_task(
    conn: sqlite3.Connection,
    product_name: str,
    product_category: str = "",
    prompt: str = "",
    main_image_ratio: str = "1:1",
    product_image: str = "",
    reference_image: str = "",
) -> dict[str, Any]:
    current = now_iso()
    task_id = f"prod_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO product_tasks (
            id, product_name, product_category, product_image, reference_image,
            prompt, main_image_ratio, detail_page_ratio, main_image_status,
            detail_page_status, copy_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '', 'pending', 'pending', 'pending', ?, ?)
        """,
        (
            task_id,
            product_name.strip(),
            product_category.strip(),
            product_image.strip(),
            reference_image.strip(),
            prompt.strip(),
            main_image_ratio.strip() or "1:1",
            current,
            current,
        ),
    )
    return product_task_dict(conn, task_id)


def run_main_image_workflow(conn: sqlite3.Connection, product_task_id: str) -> dict[str, Any]:
    task = conn.execute("SELECT * FROM product_tasks WHERE id = ?", (product_task_id,)).fetchone()
    if not task:
        raise ValueError("商品任务不存在")

    workflow_run_id = f"run_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    input_summary = {
        "product_task_id": product_task_id,
        "product_name": task["product_name"],
        "main_image_ratio": task["main_image_ratio"],
    }
    conn.execute(
        """
        INSERT INTO workflow_runs (
            id, workflow_id, status, input_summary, started_at
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (workflow_run_id, WORKFLOW_ID, summarize(input_summary), started_at),
    )
    conn.execute(
        "UPDATE product_tasks SET main_image_status = 'running', error_message = NULL, updated_at = ? WHERE id = ?",
        (now_iso(), product_task_id),
    )
    conn.commit()

    try:
        prompt = build_main_image_prompt(row_to_dict(task))
        image_config = get_module_config(conn, "image-generator")
        image_result = run_image_step(conn, workflow_run_id, product_task_id, prompt, task["main_image_ratio"], image_config)
        asset_id = save_generated_asset(conn, product_task_id, image_result, prompt)
        status = "success" if image_result["source"] == "api" else "partial_success"
        error_message = None if status == "success" else "图片生成 API 未配置，已生成本地占位主图"
        conn.execute(
            """
            UPDATE product_tasks
            SET main_image_status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error_message, now_iso(), product_task_id),
        )
        output = {
            "product_task_id": product_task_id,
            "asset_id": asset_id,
            "asset_path": image_result["path"],
            "source": image_result["source"],
            "model": image_result.get("model"),
        }
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = ?, output_summary = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (status, summarize(output), now_iso(), elapsed_ms(started), workflow_run_id),
        )
        conn.commit()
        return {
            "workflow_run_id": workflow_run_id,
            "status": status,
            **output,
        }
    except Exception as exc:
        error = str(exc)
        current = now_iso()
        conn.execute(
            "UPDATE product_tasks SET main_image_status = 'failed', error_message = ?, updated_at = ? WHERE id = ?",
            (error, current, product_task_id),
        )
        conn.execute(
            """
            UPDATE workflow_runs
            SET status = 'failed', error_message = ?, ended_at = ?, duration_ms = ?
            WHERE id = ?
            """,
            (error, current, elapsed_ms(started), workflow_run_id),
        )
        conn.commit()
        raise


def run_image_step(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    product_task_id: str,
    prompt: str,
    aspect_ratio: str,
    image_config: dict[str, str],
) -> dict[str, Any]:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    input_summary = {
        "product_task_id": product_task_id,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }
    try:
        result = generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio or "1:1",
            config=image_config,
            filename_prefix=product_task_id,
        )
        status = "success" if result["source"] == "api" else "partial_success"
        error = None if status == "success" else "图片生成 API 未配置，使用本地占位图"
    except ImageGenerateError as exc:
        result = {}
        status = "failed"
        error = str(exc)
    ended_at = now_iso()
    conn.execute(
        """
        INSERT INTO task_logs (
            task_id, workflow_id, workflow_run_id, module_id, capability,
            input_summary, output_summary, started_at, ended_at, duration_ms,
            status, error_message, retry_count
        ) VALUES (?, ?, ?, 'image-generator', 'image.generate', ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            task_id,
            WORKFLOW_ID,
            workflow_run_id,
            summarize(input_summary),
            summarize(result),
            started_at,
            ended_at,
            elapsed_ms(started),
            status,
            error,
        ),
    )
    if status == "failed":
        raise ImageGenerateError(error or "图片生成失败")
    return result


def save_generated_asset(conn: sqlite3.Connection, product_task_id: str, image_result: dict[str, Any], prompt: str) -> str:
    asset_id = f"asset_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO generated_assets (
            id, product_task_id, asset_type, path, prompt, module_id, created_at
        ) VALUES (?, ?, 'main_image', ?, ?, 'image-generator', ?)
        """,
        (asset_id, product_task_id, image_result["path"], prompt, now_iso()),
    )
    conn.execute(
        "UPDATE product_tasks SET main_image_asset_id = ?, updated_at = ? WHERE id = ?",
        (asset_id, now_iso(), product_task_id),
    )
    return asset_id


def build_main_image_prompt(task: dict[str, Any]) -> str:
    parts = [
        "Generate a clean commercial product main image.",
        "Use a professional e-commerce style with clear product focus.",
    ]
    if task.get("product_name"):
        parts.append(f"Product name: {task['product_name']}.")
    if task.get("product_category"):
        parts.append(f"Category: {task['product_category']}.")
    if task.get("prompt"):
        parts.append(f"User requirements: {task['prompt']}.")
    parts.append("Avoid text overlays, watermarks, distorted logos, and cluttered backgrounds.")
    return " ".join(parts)


def product_task_dict(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise ValueError("商品任务不存在")
    result = row_to_dict(row)
    asset = conn.execute(
        """
        SELECT id, path, asset_type, created_at
        FROM generated_assets
        WHERE product_task_id = ? AND asset_type = 'main_image'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    if asset:
        result["main_image_asset"] = row_to_dict(asset)
        result["main_image_url"] = f"/api/generated-assets/{asset['id']}/file"
    else:
        result["main_image_asset"] = None
        result["main_image_url"] = ""
    return result


def list_product_tasks(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id FROM product_tasks ORDER BY updated_at DESC LIMIT ?",
        (min(max(limit, 1), 300),),
    ).fetchall()
    return [product_task_dict(conn, row["id"]) for row in rows]


def delete_product_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT id FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise ValueError("商品主图任务不存在")

    assets = conn.execute(
        "SELECT id, path FROM generated_assets WHERE product_task_id = ?",
        (task_id,),
    ).fetchall()
    deleted_files = 0
    for asset in assets:
        if delete_asset_file(asset["path"]):
            deleted_files += 1

    conn.execute("DELETE FROM generated_assets WHERE product_task_id = ?", (task_id,))
    conn.execute("DELETE FROM product_tasks WHERE id = ?", (task_id,))
    conn.commit()
    return {
        "status": "deleted",
        "task_id": task_id,
        "deleted_assets": len(assets),
        "deleted_files": deleted_files,
    }


def delete_asset_file(path_value: str) -> bool:
    if not path_value:
        return False
    try:
        path = Path(path_value).resolve()
        storage_root = db.STORAGE_DIR.resolve()
        if not path.is_file() or not path.is_relative_to(storage_root):
            return False
        path.unlink()
        return True
    except OSError:
        return False


def get_module_config(conn: sqlite3.Connection, module_id: str) -> dict[str, str]:
    values = {
        item["key"]: item["value"]
        for item in conn.execute(
            "SELECT key, value FROM module_configs WHERE module_id = ?",
            (module_id,),
        ).fetchall()
    }
    return values


def summarize(value: Any, limit: int = 600) -> str:
    text = to_json(value)
    return text if len(text) <= limit else text[:limit] + "..."


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
