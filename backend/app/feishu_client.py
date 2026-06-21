from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"


class FeishuApiError(RuntimeError):
    pass


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, timeout: int = 20) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout
        self._tenant_access_token: str | None = None

    def batch_create_records(self, app_token: str, table_id: str, fields_list: list[dict[str, Any]]) -> dict[str, Any]:
        if not fields_list:
            return {"created": 0, "record_ids": []}

        created = 0
        record_ids: list[str] = []
        for chunk in chunks(fields_list, 500):
            body = {"records": [{"fields": fields} for fields in chunk]}
            result = self._request(
                "POST",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
                body,
                auth=True,
            )
            records = result.get("data", {}).get("records", [])
            created += len(records) or len(chunk)
            record_ids.extend(record.get("record_id", "") for record in records if record.get("record_id"))
        return {"created": created, "record_ids": record_ids}

    def batch_update_records(self, app_token: str, table_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {"updated": 0, "record_ids": []}

        updated = 0
        record_ids: list[str] = []
        for chunk in chunks(records, 500):
            body = {
                "records": [
                    {"record_id": record["record_id"], "fields": record["fields"]}
                    for record in chunk
                ]
            }
            result = self._request(
                "POST",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update",
                body,
                auth=True,
            )
            returned_records = result.get("data", {}).get("records", [])
            updated += len(returned_records) or len(chunk)
            record_ids.extend(
                record.get("record_id", "")
                for record in returned_records
                if record.get("record_id")
            )
        return {"updated": updated, "record_ids": record_ids}

    def _tenant_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        result = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
            auth=False,
        )
        token = result.get("tenant_access_token")
        if not token:
            raise FeishuApiError("飞书未返回 tenant_access_token")
        self._tenant_access_token = token
        return token

    def _request(self, method: str, path: str, body: dict[str, Any], auth: bool) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self._tenant_token()}"
        request = urllib.request.Request(
            f"{FEISHU_BASE_URL}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FeishuApiError(f"飞书 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FeishuApiError(f"飞书网络错误: {exc.reason}") from exc

        code = payload.get("code", 0)
        if code != 0:
            message = payload.get("msg") or payload.get("message") or "未知错误"
            raise FeishuApiError(f"飞书 API 错误 {code}: {message}")
        return payload


def build_lead_fields(row: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "线索编号": row.get("id"),
        "客户ID": row.get("customer_id"),
        "来源平台": row.get("source_platform"),
        "询盘时间": to_feishu_date(row.get("inquiry_time")),
        "客户名称": row.get("customer_name"),
        "联系人": row.get("contact_person"),
        "联系方式": row.get("contact"),
        "地区": row.get("region"),
        "原始咨询内容": row.get("raw_content"),
        "商品标题": row.get("product_title"),
        "AI识别产品": row.get("product"),
        "AI识别数量": to_number(row.get("quantity")),
        "AI识别需求": row.get("demand"),
        "缺失信息": row.get("missing_info"),
        "意向等级": normalize_intent(row.get("intent_level")),
        "建议回复": row.get("suggested_reply"),
        "当前状态": normalize_lead_status(row.get("status")),
    }
    return compact_fields(fields)


def build_customer_fields(row: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "客户ID": row.get("id"),
        "客户名称": row.get("customer_name"),
        "联系人": row.get("contact_person"),
        "联系方式": row.get("contact"),
        "地区": row.get("region"),
        "来源平台": row.get("source_platform"),
        "线索数量": row.get("lead_count"),
        "待处理线索数": row.get("pending_count"),
        "最新咨询时间": row.get("latest_inquiry_time"),
        "最近咨询内容": row.get("latest_raw_content"),
        "客户状态": row.get("customer_status"),
    }
    return compact_fields(fields)


def compact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "")}


def to_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return value
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def to_feishu_date(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return int(time.time() * 1000)


def normalize_intent(value: Any) -> str:
    mapping = {"高": "A", "中": "B", "低": "C", "A": "A", "B": "B", "C": "C"}
    return mapping.get(str(value or "").strip(), str(value or "").strip() or "C")


def normalize_lead_status(value: Any) -> str:
    status = str(value or "").strip()
    return "新线索" if status in ("", "新询盘") else status


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
