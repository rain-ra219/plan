from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_conn
from tools.feishu_intake.listener import (
    create_intake_listener_config,
    delete_intake_listener_config,
    list_intake_runs,
    list_intake_listeners,
    listener_state,
    scan_intake_listener_once,
    scan_intake_once,
    update_intake_listener_config,
    update_listener_state,
)

router = APIRouter()

class IntakeListenerRequest(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None

class FeishuListenerRequest(BaseModel):
    name: str
    base_id: str
    table_config_id: str
    workflow_id: str = "lead-import-to-feishu"
    enabled: bool = False
    interval_seconds: int = 60
    status_field: str = "处理状态"
    file_field: str = "CSV 文件"
    submitter_field: str = "提交人"
    note_field: str = "提交说明"
    product_name_field: str = "商品名称"
    product_category_field: str = "商品分类"
    product_image_field: str = "产品图"
    prompt_field: str = "图片提示词"
    aspect_ratio_field: str = "生成比例"
    reference_image_field: str = "参考图片"
    product_description_field: str = "产品图描述"
    reference_style_field: str = "参考图风格描述"
    final_prompt_field: str = "最终提示词"
    result_field: str = "处理结果"
    run_id_field: str = "工作流ID"
    error_field: str = "错误信息"
    processed_at_field: str = "处理时间"
    pending_value: str = "待处理"
    processing_value: str = "处理中"
    success_value: str = "处理成功"
    partial_value: str = "部分成功"
    failed_value: str = "处理失败"

class FeishuListenerPatchRequest(BaseModel):
    name: str | None = None
    base_id: str | None = None
    table_config_id: str | None = None
    workflow_id: str | None = None
    enabled: bool | None = None
    interval_seconds: int | None = None
    status_field: str | None = None
    file_field: str | None = None
    submitter_field: str | None = None
    note_field: str | None = None
    product_name_field: str | None = None
    product_category_field: str | None = None
    product_image_field: str | None = None
    prompt_field: str | None = None
    aspect_ratio_field: str | None = None
    reference_image_field: str | None = None
    product_description_field: str | None = None
    reference_style_field: str | None = None
    final_prompt_field: str | None = None
    result_field: str | None = None
    run_id_field: str | None = None
    error_field: str | None = None
    processed_at_field: str | None = None
    pending_value: str | None = None
    processing_value: str | None = None
    success_value: str | None = None
    partial_value: str | None = None
    failed_value: str | None = None

@router.get("/api/intake/listener")
def get_intake_listener() -> dict[str, Any]:
    with get_conn() as conn:
        return listener_state(conn)

@router.patch("/api/intake/listener")
def patch_intake_listener(payload: IntakeListenerRequest) -> dict[str, Any]:
    with get_conn() as conn:
        return update_listener_state(conn, enabled=payload.enabled, interval_seconds=payload.interval_seconds)

@router.get("/api/intake/listeners")
def get_intake_listeners() -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list_intake_listeners(conn)

@router.post("/api/intake/listeners")
def create_intake_listener(payload: FeishuListenerRequest) -> dict[str, Any]:
    with get_conn() as conn:
        try:
            return create_intake_listener_config(conn, payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.patch("/api/intake/listeners/{listener_id}")
def patch_intake_listener_config(listener_id: str, payload: FeishuListenerPatchRequest) -> dict[str, Any]:
    with get_conn() as conn:
        try:
            return update_intake_listener_config(
                conn,
                listener_id,
                {key: value for key, value in payload.model_dump().items() if value is not None},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.delete("/api/intake/listeners/{listener_id}")
def delete_intake_listener(listener_id: str) -> dict[str, str]:
    with get_conn() as conn:
        try:
            delete_intake_listener_config(conn, listener_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "deleted"}

@router.post("/api/intake/listeners/{listener_id}/scan")
def scan_one_intake_listener(listener_id: str) -> dict[str, Any]:
    return scan_intake_listener_once(listener_id, trigger_type="manual", limit=10)

@router.post("/api/intake/scan")
def scan_intake() -> dict[str, Any]:
    return scan_intake_once(trigger_type="manual", limit=10)

@router.get("/api/intake/runs")
def get_intake_runs(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list_intake_runs(conn, limit)
