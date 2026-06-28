from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from app import database as db
from app.capability_registry import call_capability, capability_module_id
from app.database import from_json, get_model_profile_config, now_iso, row_to_dict, to_json


WORKFLOW_ID = "product-main-image"
DETAIL_WORKFLOW_ID = "product-main-detail"
PRODUCT_DESCRIPTION_QUERY = (
    "请分析这张产品图，只描述产品本身。"
    "输出产品名称或品类、颜色、材质、外形结构、关键设计细节、可见卖点。"
    "不要描述背景，不要编造看不见的信息，控制在 200 字以内。"
)
REFERENCE_STYLE_QUERY = (
    "请分析参考图的广告视觉风格。重点描述色调、背景场景、构图、镜头角度、光线、"
    "质感、空间层次、主体与环境关系、是否有文字以及文字和主体的位置关系。"
    "不要把参考图里的产品当成要生成的产品，控制在 300 字以内。"
)


def create_product_task(
    conn: sqlite3.Connection,
    product_name: str,
    product_category: str = "",
    prompt: str = "",
    main_image_ratio: str = "1:1",
    product_image: str = "",
    reference_image: str | list[str] = "",
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
            serialize_reference_images(reference_image),
            prompt.strip(),
            main_image_ratio.strip() or "1:1",
            current,
            current,
        ),
    )
    return product_task_dict(conn, task_id)


def run_main_image_workflow(
    conn: sqlite3.Connection,
    product_task_id: str,
    workflow_id: str = WORKFLOW_ID,
) -> dict[str, Any]:
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
        "product_image_count": 1 if task["product_image"] else 0,
        "image_input_count": len(parse_reference_images(task["reference_image"])),
    }
    conn.execute(
        """
        INSERT INTO workflow_runs (
            id, workflow_id, status, input_summary, started_at
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (workflow_run_id, workflow_id, summarize(input_summary), started_at),
    )
    conn.execute(
        "UPDATE product_tasks SET main_image_status = 'running', error_message = NULL, updated_at = ? WHERE id = ?",
        (now_iso(), product_task_id),
    )
    conn.commit()

    try:
        task_data = row_to_dict(task)
        reference_images = parse_reference_images(task["reference_image"])
        prompt_plan = prepare_main_image_prompt(
            conn,
            workflow_run_id,
            product_task_id,
            task_data,
            reference_images,
            workflow_id,
        )
        prompt = prompt_plan["prompt"]
        image_config = get_capability_config(conn, "image.generate", "image-generator")
        image_result = run_image_step(
            conn,
            workflow_run_id,
            product_task_id,
            prompt,
            task["main_image_ratio"],
            image_config,
            prompt_plan["generation_references"],
            workflow_id,
        )
        asset_id = save_generated_asset(conn, product_task_id, image_result, prompt)
        degraded = bool(prompt_plan.get("degraded"))
        status = "success" if image_result["source"] == "api" and not degraded else "partial_success"
        error_message = prompt_plan.get("degraded_reason") if degraded else None
        if image_result["source"] != "api":
            error_message = "图片生成 API 未配置，已生成本地占位主图"
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
            "product_description": prompt_plan.get("product_description", ""),
            "reference_style": prompt_plan.get("reference_style", ""),
            "final_prompt": prompt,
            "prompt_degraded": degraded,
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
    reference_images: list[str] | None = None,
    workflow_id: str = WORKFLOW_ID,
) -> dict[str, Any]:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    input_summary = {
        "product_task_id": product_task_id,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "reference_image_count": len(reference_images or []),
    }
    module_id = capability_module_id(conn, "image.generate", "image-generator")
    try:
        result = call_capability(
            conn,
            "image.generate",
            prompt=prompt,
            aspect_ratio=aspect_ratio or "1:1",
            config=image_config,
            filename_prefix=product_task_id,
            reference_images=reference_images,
        )
        status = "success" if result["source"] == "api" else "partial_success"
        error = None if status == "success" else "图片生成 API 未配置，使用本地占位图"
        result["provider_module_id"] = module_id
    except Exception as exc:
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
        ) VALUES (?, ?, ?, ?, 'image.generate', ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            task_id,
            workflow_id,
            workflow_run_id,
            module_id,
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
        raise RuntimeError(error or "图片生成失败")
    return result


def save_generated_asset(conn: sqlite3.Connection, product_task_id: str, image_result: dict[str, Any], prompt: str) -> str:
    asset_id = f"asset_{uuid.uuid4().hex[:12]}"
    module_id = image_result.get("provider_module_id") or capability_module_id(conn, "image.generate", "image-generator")
    conn.execute(
        """
        INSERT INTO generated_assets (
            id, product_task_id, asset_type, path, prompt, module_id, created_at
        ) VALUES (?, ?, 'main_image', ?, ?, ?, ?)
        """,
        (asset_id, product_task_id, image_result["path"], prompt, module_id, now_iso()),
    )
    conn.execute(
        "UPDATE product_tasks SET main_image_asset_id = ?, updated_at = ? WHERE id = ?",
        (asset_id, now_iso(), product_task_id),
    )
    return asset_id


def prepare_main_image_prompt(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    product_task_id: str,
    task: dict[str, Any],
    reference_images: list[str],
    workflow_id: str,
) -> dict[str, Any]:
    if workflow_id != DETAIL_WORKFLOW_ID or not task.get("product_image"):
        return {
            "prompt": build_main_image_prompt(task, workflow_id),
            "generation_references": reference_images,
            "product_description": "",
            "reference_style": "",
            "degraded": False,
            "degraded_reason": "",
        }

    describe_config = get_model_profile_config(conn, "vision")
    compose_config = get_model_profile_config(conn, "prompt")
    product_image = str(task.get("product_image") or "")
    style_images = remove_product_image(reference_images, product_image)
    degraded_reasons: list[str] = []

    product_description = run_model_text_step(
        conn,
        workflow_run_id,
        workflow_id,
        product_task_id,
        "image.describe",
        "product-image-description",
        PRODUCT_DESCRIPTION_QUERY,
        describe_config,
        images=[product_image],
        input_summary={
            "target": "product_image",
            "product_task_id": product_task_id,
            "image_count": 1,
        },
    )
    if not product_description:
        degraded_reasons.append("product image description failed")

    reference_style = ""
    if style_images:
        reference_style = run_model_text_step(
            conn,
            workflow_run_id,
            workflow_id,
            product_task_id,
            "image.describe",
            "reference-style-description",
            REFERENCE_STYLE_QUERY,
            describe_config,
            images=style_images[:3],
            input_summary={
                "target": "reference_image",
                "product_task_id": product_task_id,
                "image_count": len(style_images[:3]),
            },
        )
        if not reference_style:
            degraded_reasons.append("reference style description failed")
    else:
        degraded_reasons.append("reference image missing")

    compose_prompt = build_prompt_compose_request(task, product_description, reference_style)
    composed_prompt = run_model_text_step(
        conn,
        workflow_run_id,
        workflow_id,
        product_task_id,
        "prompt.compose",
        "compose-final-prompt",
        compose_prompt,
        compose_config,
        images=None,
        input_summary={
            "target": "final_prompt",
            "product_task_id": product_task_id,
            "has_product_description": bool(product_description),
            "has_reference_style": bool(reference_style),
            "user_prompt": task.get("prompt", ""),
        },
    )
    if not composed_prompt:
        degraded_reasons.append("final prompt compose failed")

    final_prompt = build_detail_generation_prompt(task, product_description, reference_style, composed_prompt)

    return {
        "prompt": final_prompt,
        "generation_references": [product_image],
        "product_description": product_description,
        "reference_style": reference_style,
        "degraded": bool(degraded_reasons),
        "degraded_reason": "; ".join(degraded_reasons),
    }

def run_model_text_step(
    conn: sqlite3.Connection,
    workflow_run_id: str,
    workflow_id: str,
    product_task_id: str,
    capability: str,
    action: str,
    prompt: str,
    model_config: dict[str, str],
    images: list[str] | None,
    input_summary: dict[str, Any],
) -> str:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = now_iso()
    output: dict[str, Any] = {}
    error: str | None = None
    status = "success"
    module_id = capability_module_id(conn, capability, "model-provider")

    try:
        if not model_config_ready(model_config):
            status = "partial_success"
            error = "模型 API 未配置，跳过该模型节点"
            text = ""
        elif capability == "image.describe" and images:
            text = call_capability(conn, capability, images=images, question=prompt, config=model_config)
        else:
            text = call_capability(conn, capability, prompt, config=model_config)
        output = {"action": action, "text": text, "model": model_config.get("model", "")}
    except Exception as exc:
        status = "failed"
        error = str(exc)
        text = ""
        output = {"action": action, "model": model_config.get("model", "")}

    ended_at = now_iso()
    conn.execute(
        """
        INSERT INTO task_logs (
            task_id, workflow_id, workflow_run_id, module_id, capability,
            input_summary, output_summary, started_at, ended_at, duration_ms,
            status, error_message, retry_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            task_id,
            workflow_id,
            workflow_run_id,
            module_id,
            capability,
            summarize({**input_summary, "action": action, "prompt": prompt}),
            summarize(output),
            started_at,
            ended_at,
            elapsed_ms(started),
            status,
            error,
        ),
    )
    return text.strip()


def model_config_ready(config: dict[str, str]) -> bool:
    return bool(config.get("apiKey") and config.get("baseUrl") and config.get("model"))


def remove_product_image(reference_images: list[str], product_image: str) -> list[str]:
    if not product_image:
        return reference_images
    return [image for image in reference_images if image != product_image]


def build_prompt_compose_request(task: dict[str, Any], product_description: str, reference_style: str) -> str:
    user_prompt = str(task.get("prompt") or "").strip()
    return f"""
Combine the product image description, reference image style description, and user prompt into one final image-generation prompt.

Rules:
1. The user prompt is the highest-priority requirement.
2. Use the product image description only to preserve the target product identity.
3. Use the reference image style description to borrow layout, scene, lighting, composition, color mood, and commercial visual style.
4. Do not include internal record IDs, table IDs, product codes, workflow IDs, or field names.
5. Output only the final prompt. Do not explain.

Product image description:
{product_description}

Reference image style description:
{reference_style}

User prompt:
{user_prompt}
""".strip()


def build_detail_generation_prompt(
    task: dict[str, Any],
    product_description: str,
    reference_style: str,
    composed_prompt: str,
) -> str:
    if composed_prompt.strip():
        return composed_prompt.strip()

    parts = []
    if product_description.strip():
        parts.append(f"Product image description: {product_description.strip()}")
    if reference_style.strip():
        parts.append(f"Reference image style description: {reference_style.strip()}")
    if str(task.get("prompt") or "").strip():
        parts.append(f"User prompt: {str(task.get('prompt') or '').strip()}")
    return "\n\n".join(parts).strip()


def build_main_image_prompt(task: dict[str, Any], workflow_id: str = WORKFLOW_ID) -> str:
    return str(task.get("prompt") or "").strip()


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


def get_capability_config(conn: sqlite3.Connection, capability: str, default_module_id: str) -> dict[str, str]:
    module_id = capability_module_id(conn, capability, default_module_id)
    return get_module_config(conn, module_id)


def serialize_reference_images(value: str | list[str]) -> str:
    if isinstance(value, list):
        images = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return to_json(images) if images else ""
    return str(value or "").strip()


def parse_reference_images(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            parsed = from_json(text, [])
            if isinstance(parsed, list):
                return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
        return [text]
    return []


def summarize(value: Any, limit: int = 600) -> str:
    text = to_json(value)
    return text if len(text) <= limit else text[:limit] + "..."


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
