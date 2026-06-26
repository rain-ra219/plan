from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class ModelProviderError(RuntimeError):
    pass


def generate_text(
    prompt: str,
    config: dict[str, str] | None = None,
    images: list[str] | None = None,
    system: str = "",
) -> str:
    config = config or {}
    api_key = (config.get("apiKey") or config.get("api_key") or "").strip()
    base_url = (config.get("baseUrl") or config.get("base_url") or "https://api.siliconflow.cn/v1/chat/completions").strip()
    model = (config.get("model") or "Qwen/Qwen3.6-27B").strip()
    auth_mode = (config.get("authMode") or config.get("auth_mode") or "bearer").strip().lower()

    if not api_key:
        raise ModelProviderError("模型 API 未配置：apiKey 为空")
    if not model:
        raise ModelProviderError("模型 API 未配置：model 为空")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in clean_images(images):
        content.append({"type": "image_url", "image_url": {"url": image}})

    messages: list[dict[str, Any]] = []
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": content})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    body = post_json(chat_completion_endpoint(base_url), payload, api_key, auth_mode)
    text = extract_text(json.loads(body.decode("utf-8", errors="replace")))
    if not text:
        raise ModelProviderError("模型 API 返回为空")
    return text.strip()


def describe_image(image: str, question: str, config: dict[str, str] | None = None) -> str:
    return generate_text(question, config=config, images=[image])


def describe_images(images: list[str], question: str, config: dict[str, str] | None = None) -> str:
    return generate_text(question, config=config, images=images)


def post_json(endpoint_url: str, payload: dict[str, Any], api_key: str, auth_mode: str) -> bytes:
    request = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": authorization_header(api_key, auth_mode),
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ModelProviderError(f"Model API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        raise ModelProviderError(f"Model API network error after {elapsed} ms: {exc.reason}") from exc


def chat_completion_endpoint(base_url: str) -> str:
    clean = (base_url or "https://api.siliconflow.cn/v1/chat/completions").strip().rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def authorization_header(api_key: str, auth_mode: str) -> str:
    key = api_key.strip()
    if key.lower().startswith("bearer "):
        return key
    if auth_mode == "raw":
        return key
    return f"Bearer {key}"


def clean_images(images: list[str] | None) -> list[str]:
    if not images:
        return []
    return [item.strip() for item in images if isinstance(item, str) and item.strip()]


def extract_text(result: Any) -> str:
    choices = result.get("choices") if isinstance(result, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return content_to_text(message.get("content"))
    return content_to_text(result)


def content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    if isinstance(value, dict):
        text = value.get("text") or value.get("content") or value.get("output_text")
        return str(text) if text else ""
    return str(value)
