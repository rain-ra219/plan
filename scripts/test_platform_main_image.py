from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PAYLOAD = {
    "product_name": "API test white ceramic mug",
    "product_category": "Home goods",
    "prompt": "Clean ecommerce product main image, white background, soft studio light, no text, no watermark.",
    "main_image_ratio": "1:1",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the running platform main-image workflow.")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="Backend API base URL.")
    parser.add_argument("--output-dir", default="test_outputs", help="Where to save the returned generated asset.")
    args = parser.parse_args()

    api_base = args.api.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Calling:", f"{api_base}/api/product-tasks/main-image")
    print("This uses the image-generator config saved in the platform.")
    print()

    try:
        response = post_json(f"{api_base}/api/product-tasks/main-image", DEFAULT_PAYLOAD, timeout=360)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail[:1200]}")
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")
        print("Check that Docker/backend is running and port 8000 is available.")
        return 1

    workflow = response.get("workflow") or {}
    task = response.get("task") or {}
    source = workflow.get("source")
    status = workflow.get("status")
    asset_url = task.get("main_image_url")

    print("Workflow status:", status)
    print("Image source:", source)
    print("Workflow run:", workflow.get("workflow_run_id"))
    print("Task id:", task.get("id"))

    if asset_url:
        saved = download_asset(api_base, asset_url, output_dir)
        if saved:
            print("Saved asset:", saved)

    if status == "success" and source == "api":
        return 0

    if status == "partial_success" or source == "placeholder":
        print()
        print("The workflow ran, but it produced a placeholder.")
        print("Most likely cause: image-generator module is disabled or API config was not saved in the running backend.")
        return 2

    print()
    print("The workflow did not return a real API image.")
    print(json.dumps(response, ensure_ascii=False)[:1600])
    return 1


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def download_asset(api_base: str, asset_url: str, output_dir: Path) -> Path | None:
    url = asset_url if asset_url.startswith("http") else f"{api_base}{asset_url}"
    extension = "png"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type", "")
    except Exception as exc:
        print(f"Asset download failed: {type(exc).__name__}: {exc}")
        return None

    if "svg" in content_type:
        extension = "svg"
    elif "jpeg" in content_type or "jpg" in content_type:
        extension = "jpg"
    elif "webp" in content_type:
        extension = "webp"

    path = output_dir / f"platform_main_image_{int(time.time())}.{extension}"
    path.write_bytes(content)
    return path


if __name__ == "__main__":
    sys.exit(main())
