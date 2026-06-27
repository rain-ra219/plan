from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..database import get_conn
from ..workflow_registry import WorkflowRegistryError, call_tool_entrypoint, ensure_workflow_available, run_workflow

PRODUCT_MAIN_IMAGE_TOOL_ID = "product-main-image"
PRODUCT_MAIN_IMAGE_WORKFLOW_ID = "product-main-image"

router = APIRouter()

def product_tool_entrypoint(entrypoint_name: str, *args: Any, **kwargs: Any) -> Any:
    try:
        return call_tool_entrypoint(PRODUCT_MAIN_IMAGE_TOOL_ID, entrypoint_name, *args, **kwargs)
    except WorkflowRegistryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

class ProductMainImageRequest(BaseModel):
    product_name: str
    product_category: str = ""
    prompt: str = ""
    main_image_ratio: str = "1:1"
    product_image: str = ""
    reference_image: str = ""

@router.get("/api/product-tasks")
def get_product_tasks(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        try:
            return call_tool_entrypoint(PRODUCT_MAIN_IMAGE_TOOL_ID, "listTasks", conn, limit)
        except WorkflowRegistryError:
            return []

@router.post("/api/product-tasks/main-image")
def create_and_run_main_image(payload: ProductMainImageRequest) -> dict[str, Any]:
    if not payload.product_name.strip():
        raise HTTPException(status_code=400, detail="请填写商品名称")
    with get_conn() as conn:
        workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", (PRODUCT_MAIN_IMAGE_WORKFLOW_ID,)).fetchone()
        if not workflow or not workflow["enabled"]:
            raise HTTPException(status_code=409, detail="商品主图工作流未启用")
        try:
            ensure_workflow_available(conn, PRODUCT_MAIN_IMAGE_WORKFLOW_ID)
        except WorkflowRegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        task = product_tool_entrypoint(
            "createTask",
            conn,
            product_name=payload.product_name,
            product_category=payload.product_category,
            prompt=payload.prompt,
            main_image_ratio=payload.main_image_ratio,
            product_image=payload.product_image,
            reference_image=payload.reference_image,
        )
        try:
            result = run_workflow(
                conn,
                PRODUCT_MAIN_IMAGE_WORKFLOW_ID,
                task["id"],
                workflow_id=PRODUCT_MAIN_IMAGE_WORKFLOW_ID,
            )
        except WorkflowRegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "task": product_tool_entrypoint("getTask", conn, task["id"]),
            "workflow": result,
        }

@router.post("/api/product-tasks/{task_id}/generate-main-image")
def rerun_main_image(task_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        try:
            result = run_workflow(
                conn,
                PRODUCT_MAIN_IMAGE_WORKFLOW_ID,
                task_id,
                workflow_id=PRODUCT_MAIN_IMAGE_WORKFLOW_ID,
            )
        except WorkflowRegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "task": product_tool_entrypoint("getTask", conn, task_id),
            "workflow": result,
        }

@router.delete("/api/product-tasks/{task_id}")
def delete_main_image_task(task_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        try:
            return product_tool_entrypoint("deleteTask", conn, task_id)
        except WorkflowRegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/api/generated-assets/{asset_id}/file")
def get_generated_asset_file(asset_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute("SELECT path FROM generated_assets WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="生成资产不存在")
        path = Path(row["path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="生成资产文件不存在")
        return FileResponse(path)
