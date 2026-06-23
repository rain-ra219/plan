from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_PROMPT = (
    "A clean product photo of a white ceramic mug on a light gray background, "
    "studio lighting, ecommerce main image, no text, no watermark"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the image generation API from the exported n8n workflow.")
    parser.add_argument("--workflow-json", default="gpt api (2).json")
    parser.add_argument("--output-dir", default="test_outputs")
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--aspect-ratio", default="1:1")
    args = parser.parse_args()

    root = Path.cwd()
    workflow_path = Path(args.workflow_json)
    if not workflow_path.is_absolute():
        workflow_path = root / workflow_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_n8n_image_config(workflow_path)
    opener = build_opener(args.proxy)
    payload = {
        "model": config["model"],
        "prompt": args.prompt,
        "aspect_ratio": args.aspect_ratio,
    }

    print("Image API:", config["base_url"])
    print("Model:", config["model"])
    print("Proxy:", args.proxy or "disabled")
    print("Output:", output_dir)
    print()

    # The current platform uses Bearer auth. The old n8n workflow appears to pass the raw key.
    tests = [
        ("bearer", f"Bearer {config['api_key']}"),
        ("raw", config["api_key"]),
    ]
    for tag, auth_value in tests:
        print(f"Testing auth mode: {tag}")
        result = call_image_api(
            opener=opener,
            base_url=config["base_url"],
            auth_value=auth_value,
            payload=payload,
            output_dir=output_dir,
            tag=tag,
        )
        if result:
            print(f"SUCCESS: {result}")
            return 0
        print()

    print("FAILED: both Bearer and raw Authorization modes failed.")
    return 1


def load_n8n_image_config(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"Workflow JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    node = next(
        (
            item
            for item in data.get("nodes", [])
            if "ai.t8star.cn/v1/images/generations" in json.dumps(item, ensure_ascii=False)
        ),
        None,
    )
    if not node:
        raise SystemExit("Image generation HTTP node not found in workflow JSON.")

    params = node.get("parameters", {})
    url = str(params.get("url", "")).strip()
    match = re.match(r"^(https?://[^/]+/v1)/images/generations$", url)
    base_url = match.group(1) if match else "https://ai.t8star.cn/v1"

    header_items = params.get("headerParameters", {}).get("parameters", [])
    api_key = ""
    for item in header_items:
        if str(item.get("name", "")).lower() == "authorization":
            api_key = str(item.get("value", "")).strip()
            break
    if not api_key:
        raise SystemExit("Authorization key not found in workflow JSON.")

    model = "gpt-image-2"
    json_body = str(params.get("jsonBody", ""))
    if "gpt-image-2" in json_body:
        model = "gpt-image-2"
    return {"base_url": base_url, "api_key": api_key, "model": model}


def build_opener(proxy: str) -> urllib.request.OpenerDirector:
    if not proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def call_image_api(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    auth_value: str,
    payload: dict[str, str],
    output_dir: Path,
    tag: str,
) -> Path | None:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/images/generations",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": auth_value},
        method="POST",
    )
    try:
        with opener.open(request, timeout=300) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail[:500]}")
        return None
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")
        return None

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        print(f"Non-JSON response: {body[:500]}")
        return None

    item = (result.get("data") or [{}])[0]
    if item.get("b64_json"):
        image_bytes = base64.b64decode(item["b64_json"])
        output_path = output_dir / f"image_api_test_{tag}.png"
        output_path.write_bytes(image_bytes)
        return output_path

    if item.get("url"):
        return download_image(opener, item["url"], output_dir, tag)

    print(f"No image returned: {json.dumps(result, ensure_ascii=False)[:800]}")
    return None


def download_image(opener: urllib.request.OpenerDirector, url: str, output_dir: Path, tag: str) -> Path | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(request, timeout=120) as response:
            image_bytes = response.read()
            content_type = response.headers.get("Content-Type", "")
    except Exception as exc:
        print(f"Image download failed: {type(exc).__name__}: {exc}")
        return None

    extension = "png"
    if "jpeg" in content_type or "jpg" in content_type:
        extension = "jpg"
    elif "webp" in content_type:
        extension = "webp"
    output_path = output_dir / f"image_api_test_{tag}.{extension}"
    output_path.write_bytes(image_bytes)
    return output_path


if __name__ == "__main__":
    sys.exit(main())
