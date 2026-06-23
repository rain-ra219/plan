from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app import database as db


class ImageGenerateError(RuntimeError):
    pass


def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    config: dict[str, str] | None = None,
    filename_prefix: str = "main-image",
) -> dict[str, Any]:
    config = config or {}
    api_key = config.get("apiKey") or config.get("api_key") or ""
    base_url = (config.get("baseUrl") or config.get("base_url") or "https://api.openai.com/v1").strip()
    mode = provider_mode(config, base_url)
    model = config.get("model") or ("gpt-4o-image" if mode == "chat" else "gpt-image-2")
    auth_mode = (config.get("authMode") or config.get("auth_mode") or "").strip().lower()

    if not api_key:
        return create_placeholder_image(prompt, aspect_ratio, filename_prefix)

    if mode == "chat":
        return generate_chat_image(prompt, aspect_ratio, base_url, model, api_key, auth_mode, filename_prefix)
    return generate_images_api_image(prompt, aspect_ratio, base_url, model, api_key, auth_mode, filename_prefix)


def generate_images_api_image(
    prompt: str,
    aspect_ratio: str,
    base_url: str,
    model: str,
    api_key: str,
    auth_mode: str,
    filename_prefix: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": aspect_ratio,
    }
    body, content_type = post_json_for_image(image_generation_endpoint(base_url), payload, api_key, base_url, auth_mode)
    if looks_like_image(body, content_type):
        extension = extension_from_content_type(content_type)
        path = save_asset_bytes(body, filename_prefix, extension)
        return {
            "path": str(path),
            "content_type": content_type or guess_content_type(path),
            "source": "api",
            "model": model,
        }

    result = parse_image_api_json(body, content_type)
    item = (result.get("data") or [{}])[0]
    if item.get("b64_json"):
        image_bytes = base64.b64decode(item["b64_json"])
        path = save_asset_bytes(image_bytes, filename_prefix, "png")
        return {
            "path": str(path),
            "content_type": "image/png",
            "source": "api",
            "model": model,
        }
    if item.get("url"):
        image_bytes = download_image(item["url"], api_key=api_key, base_url=base_url, auth_mode=auth_mode)
        path = save_asset_bytes(image_bytes, filename_prefix, image_extension(item["url"]))
        return {
            "path": str(path),
            "content_type": guess_content_type(path),
            "source": "api",
            "model": model,
            "remote_url": item["url"],
        }
    raise ImageGenerateError(f"Image API returned no image data: {json.dumps(result, ensure_ascii=False)[:500]}")


def generate_chat_image(
    prompt: str,
    aspect_ratio: str,
    base_url: str,
    model: str,
    api_key: str,
    auth_mode: str,
    filename_prefix: str,
) -> dict[str, Any]:
    chat_prompt = (
        f"{prompt}\n\n"
        f"Aspect ratio: {aspect_ratio or '1:1'}.\n"
        "Return the generated image as an image URL or base64 image data. "
        "Do not return only descriptive text."
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": chat_prompt,
                    }
                ],
            }
        ],
    }
    body, content_type = post_json_for_image(chat_completion_endpoint(base_url), payload, api_key, base_url, auth_mode)
    if looks_like_image(body, content_type):
        extension = extension_from_content_type(content_type)
        path = save_asset_bytes(body, filename_prefix, extension)
        return {
            "path": str(path),
            "content_type": content_type or guess_content_type(path),
            "source": "api",
            "model": model,
            "response_format": "raw-image",
        }

    result = parse_image_api_json(body, content_type)
    candidate = first_image_candidate(result)
    if not candidate:
        raise ImageGenerateError(f"Chat image API returned no image data: {json.dumps(result, ensure_ascii=False)[:800]}")

    kind, value = candidate
    if kind == "url":
        image_bytes = download_image(value, api_key=api_key, base_url=base_url, auth_mode=auth_mode)
        path = save_asset_bytes(image_bytes, filename_prefix, image_extension(value))
        return {
            "path": str(path),
            "content_type": guess_content_type(path),
            "source": "api",
            "model": model,
            "remote_url": value,
            "response_format": "chat.completions",
        }
    if kind == "data_uri":
        mime_type, image_bytes = decode_data_uri_image(value)
        extension = extension_from_content_type(mime_type)
        path = save_asset_bytes(image_bytes, filename_prefix, extension)
        return {
            "path": str(path),
            "content_type": mime_type,
            "source": "api",
            "model": model,
            "response_format": "chat.completions",
        }
    if kind == "base64":
        image_bytes = base64.b64decode(value)
        path = save_asset_bytes(image_bytes, filename_prefix, "png")
        return {
            "path": str(path),
            "content_type": "image/png",
            "source": "api",
            "model": model,
            "response_format": "chat.completions",
        }
    raise ImageGenerateError(f"Unsupported chat image candidate: {kind}")


def post_json_for_image(
    endpoint_url: str,
    payload: dict[str, Any],
    api_key: str,
    base_url: str,
    auth_mode: str,
) -> tuple[bytes, str]:
    request = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": authorization_header(api_key, base_url, auth_mode),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ImageGenerateError(f"Image API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise ImageGenerateError(f"Image API network error: {exc.reason}") from exc


def provider_mode(config: dict[str, str], base_url: str) -> str:
    explicit = (config.get("providerMode") or config.get("provider_mode") or "").strip().lower()
    if explicit in {"chat", "images"}:
        return explicit
    clean = (base_url or "").strip().rstrip("/")
    if clean.endswith("/chat/completions"):
        return "chat"
    return "images"


def image_generation_endpoint(base_url: str) -> str:
    clean = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    if clean.endswith("/images/generations"):
        return clean
    return f"{clean}/images/generations"


def chat_completion_endpoint(base_url: str) -> str:
    clean = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def authorization_header(api_key: str, base_url: str, auth_mode: str) -> str:
    key = api_key.strip()
    if key.lower().startswith("bearer "):
        return key
    if auth_mode == "bearer":
        return f"Bearer {key}"
    if auth_mode == "raw":
        return key
    if "ai.t8star.cn" in base_url:
        return key
    return f"Bearer {key}"


def first_image_candidate(value: Any) -> tuple[str, str] | None:
    for candidate in iter_image_candidates(value):
        return candidate
    return None


def iter_image_candidates(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("b64_json", "base64", "image_base64"):
            item = value.get(key)
            if isinstance(item, str) and looks_like_base64(item):
                yield "base64", strip_base64_prefix(item)

        item = value.get("image_url")
        if isinstance(item, dict):
            url = item.get("url")
            if isinstance(url, str):
                yield from iter_image_candidates(url)
        elif isinstance(item, str):
            yield from iter_image_candidates(item)

        item = value.get("url")
        if isinstance(item, str):
            yield from iter_image_candidates(item)

        item = value.get("image")
        if isinstance(item, str):
            yield from iter_image_candidates(item)

        preferred = ["choices", "message", "content", "images", "data", "output"]
        for key in preferred:
            if key in value:
                yield from iter_image_candidates(value[key])
        for key, item in value.items():
            if key not in preferred and key not in {"b64_json", "base64", "image_base64", "image_url", "url", "image"}:
                yield from iter_image_candidates(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_image_candidates(item)
    elif isinstance(value, str):
        text = value.strip()
        data_match = re.search(r"data:(image/[^;]+);base64,([A-Za-z0-9+/=\s]+)", text)
        if data_match:
            yield "data_uri", data_match.group(0)
            return
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                yield from iter_image_candidates(parsed)
        if looks_like_base64(text):
            yield "base64", strip_base64_prefix(text)
            return
        for url in re.findall(r"https?://[^\s)\"']+", text):
            yield "url", url.rstrip(".,;")


def decode_data_uri_image(value: str) -> tuple[str, bytes]:
    match = re.match(r"data:(image/[^;]+);base64,([A-Za-z0-9+/=\s]+)", value.strip())
    if not match:
        raise ImageGenerateError("Invalid data URI image returned by API.")
    mime_type = match.group(1)
    image_bytes = base64.b64decode(re.sub(r"\s+", "", match.group(2)))
    return mime_type, image_bytes


def looks_like_base64(value: str) -> bool:
    clean = strip_base64_prefix(value)
    if len(clean) < 200:
        return False
    return re.fullmatch(r"[A-Za-z0-9+/=\s]+", clean) is not None


def strip_base64_prefix(value: str) -> str:
    text = value.strip()
    if "," in text and text.lower().startswith("data:image/"):
        text = text.split(",", 1)[1]
    return re.sub(r"\s+", "", text)


def looks_like_image(body: bytes, content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return (
        lowered.startswith("image/")
        or body.startswith(b"\x89PNG\r\n\x1a\n")
        or body.startswith(b"\xff\xd8\xff")
        or (body.startswith(b"RIFF") and b"WEBP" in body[:16])
    )


def parse_image_api_json(body: bytes, content_type: str) -> dict[str, Any]:
    if not body:
        raise ImageGenerateError("Image API returned an empty response.")
    try:
        text = body.decode("utf-8")
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = body[:300].decode("utf-8", errors="replace").replace("\n", " ")
        raise ImageGenerateError(
            "Image API returned non-JSON data. "
            f"content_type={content_type or 'unknown'}, preview={preview}"
        ) from exc


def extension_from_content_type(content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "jpeg" in lowered or "jpg" in lowered:
        return "jpg"
    if "webp" in lowered:
        return "webp"
    if "svg" in lowered:
        return "svg"
    return "png"


def create_placeholder_image(prompt: str, aspect_ratio: str, filename_prefix: str) -> dict[str, Any]:
    width, height = ratio_size(aspect_ratio)
    safe_prompt = escape_svg(prompt[:180] or "Product main image")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f8fafc"/>
  <rect x="32" y="32" width="{width - 64}" height="{height - 64}" rx="28" fill="#ffffff" stroke="#cbd5e1" stroke-width="3"/>
  <circle cx="{width * 0.5:.0f}" cy="{height * 0.36:.0f}" r="{min(width, height) * 0.16:.0f}" fill="#14b8a6" opacity="0.18"/>
  <text x="50%" y="46%" text-anchor="middle" font-family="Arial, Microsoft YaHei, sans-serif" font-size="34" font-weight="700" fill="#0f172a">Main image preview</text>
  <text x="50%" y="54%" text-anchor="middle" font-family="Arial, Microsoft YaHei, sans-serif" font-size="18" fill="#64748b">Image API is not configured. Placeholder generated.</text>
  <foreignObject x="80" y="{height * 0.62:.0f}" width="{width - 160}" height="{height * 0.24:.0f}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,'Microsoft YaHei',sans-serif;font-size:18px;line-height:1.5;color:#334155;text-align:center;word-break:break-word;">{safe_prompt}</div>
  </foreignObject>
</svg>
"""
    path = save_asset_bytes(svg.encode("utf-8"), filename_prefix, "svg")
    return {
        "path": str(path),
        "content_type": "image/svg+xml",
        "source": "placeholder",
        "model": "local-placeholder",
    }


def save_asset_bytes(content: bytes, filename_prefix: str, extension: str) -> Path:
    asset_dir = db.STORAGE_DIR / "generated_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "-", filename_prefix).strip("-") or "asset"
    path = asset_dir / f"{safe_prefix}_{uuid.uuid4().hex[:10]}.{extension}"
    path.write_bytes(content)
    return path


def download_image(url: str, api_key: str = "", base_url: str = "", auth_mode: str = "") -> bytes:
    headers = {
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if api_key:
        headers["Authorization"] = authorization_header(api_key, base_url or url, auth_mode)
    if base_url:
        headers["Referer"] = base_url
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ImageGenerateError(f"Generated image download failed: HTTP {exc.code} {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ImageGenerateError(f"Generated image download failed: {exc.reason}") from exc


def image_extension(url: str) -> str:
    clean = url.split("?")[0].lower()
    for extension in ("png", "jpg", "jpeg", "webp"):
        if clean.endswith(f".{extension}"):
            return extension
    return "png"


def guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def ratio_size(aspect_ratio: str) -> tuple[int, int]:
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*$", aspect_ratio or "")
    if not match:
        return 1024, 1024
    left = float(match.group(1))
    right = float(match.group(2))
    if left <= 0 or right <= 0:
        return 1024, 1024
    if left >= right:
        return 1024, max(512, int(1024 * right / left))
    return max(512, int(1024 * left / right)), 1024


def escape_svg(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
