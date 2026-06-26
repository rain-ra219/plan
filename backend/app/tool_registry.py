from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import BACKEND_ROOT


TOOLS_ROOT = BACKEND_ROOT / "tools"
REQUIRED_FIELDS = ("id", "name", "version", "type", "provides")


def list_tool_manifests() -> list[dict[str, Any]]:
    """Read tool manifests without importing tool code.

    The registry stays metadata-only so the platform can discover tools without
    importing or starting business runtime code.
    """
    tools: list[dict[str, Any]] = []
    if not TOOLS_ROOT.exists():
        return tools

    for manifest_path in sorted(TOOLS_ROOT.glob("*/manifest.json")):
        tools.append(load_tool_manifest(manifest_path))
    return tools


def load_tool_manifest(manifest_path: Path) -> dict[str, Any]:
    tool_dir = manifest_path.parent
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        problems = validate_manifest(manifest)
        status = "valid" if not problems else "invalid"
    except Exception as exc:
        manifest = {}
        problems = [str(exc)]
        status = "invalid"

    manifest.setdefault("id", tool_dir.name)
    manifest.setdefault("name", tool_dir.name)
    manifest.setdefault("version", "0.0.0")
    manifest.setdefault("type", "unknown")
    manifest.setdefault("enabled", False)
    manifest.setdefault("provides", [])
    manifest.setdefault("uses", [])
    manifest["path"] = str(tool_dir.relative_to(BACKEND_ROOT)).replace("\\", "/")
    manifest["registryStatus"] = status
    manifest["registryProblems"] = problems
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            problems.append(f"missing required field: {field}")

    for list_field in ("provides", "uses"):
        if list_field in manifest and not isinstance(manifest[list_field], list):
            problems.append(f"{list_field} must be a list")

    if "configSchema" in manifest and not isinstance(manifest["configSchema"], dict):
        problems.append("configSchema must be an object")

    if "entrypoints" in manifest and not isinstance(manifest["entrypoints"], dict):
        problems.append("entrypoints must be an object")

    if "workflows" in manifest and not isinstance(manifest["workflows"], dict):
        problems.append("workflows must be an object")

    if "capabilityEntrypoints" in manifest and not isinstance(manifest["capabilityEntrypoints"], dict):
        problems.append("capabilityEntrypoints must be an object")

    return problems
