from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from .tool_registry import list_tool_manifests


class WorkflowRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    tool_id: str
    tool_name: str
    entrypoint: str
    tool_enabled: bool
    intake_kind: str = ""
    options: dict[str, Any] | None = None

    def option(self, key: str, default: Any = None) -> Any:
        return (self.options or {}).get(key, default)


def list_workflow_definitions() -> list[WorkflowDefinition]:
    definitions: list[WorkflowDefinition] = []
    for manifest in list_tool_manifests():
        definitions.extend(_definitions_from_manifest(manifest))
    return sorted(definitions, key=lambda item: item.workflow_id)


def get_workflow_definition(target_workflow_id: str) -> WorkflowDefinition:
    for definition in list_workflow_definitions():
        if definition.workflow_id == target_workflow_id:
            return definition
    raise WorkflowRegistryError(f"workflow is not registered: {target_workflow_id}")


def ensure_workflow_available(conn: Any, target_workflow_id: str) -> WorkflowDefinition:
    definition = get_workflow_definition(target_workflow_id)
    if not definition.tool_enabled:
        raise WorkflowRegistryError(f"workflow tool is disabled: {definition.tool_id}")

    workflow = conn.execute("SELECT enabled FROM workflows WHERE id = ?", (target_workflow_id,)).fetchone()
    if not workflow:
        raise WorkflowRegistryError(f"workflow is not configured in database: {target_workflow_id}")
    if not workflow["enabled"]:
        raise WorkflowRegistryError(f"workflow is disabled: {target_workflow_id}")

    module = conn.execute("SELECT enabled FROM modules WHERE id = ?", (definition.tool_id,)).fetchone()
    if module and not module["enabled"]:
        raise WorkflowRegistryError(f"workflow module is disabled: {definition.tool_id}")

    return definition


def run_workflow(conn: Any, target_workflow_id: str, *args: Any, **kwargs: Any) -> Any:
    definition = ensure_workflow_available(conn, target_workflow_id)
    return call_entrypoint(definition.entrypoint, conn, *args, **kwargs)


def call_tool_entrypoint(tool_id: str, entrypoint_name: str, *args: Any, **kwargs: Any) -> Any:
    manifest = _tool_manifest(tool_id)
    if not manifest.get("enabled", True):
        raise WorkflowRegistryError(f"tool is disabled: {tool_id}")

    entrypoints = manifest.get("entrypoints", {})
    if not isinstance(entrypoints, dict):
        raise WorkflowRegistryError(f"tool entrypoints are invalid: {tool_id}")

    entrypoint = entrypoints.get(entrypoint_name)
    if not entrypoint:
        raise WorkflowRegistryError(f"tool entrypoint is not registered: {tool_id}.{entrypoint_name}")

    return call_entrypoint(str(entrypoint), *args, **kwargs)


def call_entrypoint(entrypoint: str, *args: Any, **kwargs: Any) -> Any:
    function = load_entrypoint(entrypoint)
    return function(*args, **kwargs)


def load_entrypoint(entrypoint: str) -> Callable[..., Any]:
    if ":" not in entrypoint:
        raise WorkflowRegistryError(f"entrypoint must use module:function format: {entrypoint}")
    module_name, function_name = entrypoint.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise WorkflowRegistryError(f"failed to import workflow entrypoint {entrypoint}: {exc}") from exc

    try:
        function = getattr(module, function_name)
    except AttributeError as exc:
        raise WorkflowRegistryError(f"workflow entrypoint function not found: {entrypoint}") from exc

    if not callable(function):
        raise WorkflowRegistryError(f"workflow entrypoint is not callable: {entrypoint}")
    return function


def _definitions_from_manifest(manifest: dict[str, Any]) -> list[WorkflowDefinition]:
    definitions: list[WorkflowDefinition] = []
    seen: set[str] = set()
    workflows = manifest.get("workflows")
    if isinstance(workflows, dict):
        for workflow_id, raw_definition in workflows.items():
            definition = _definition_from_workflow_config(manifest, str(workflow_id), raw_definition)
            if definition:
                definitions.append(definition)
                seen.add(definition.workflow_id)

    legacy_entrypoint = _legacy_run_entrypoint(manifest)
    for workflow_id in manifest.get("workflowIds", []):
        workflow_id = str(workflow_id)
        if workflow_id in seen or not legacy_entrypoint:
            continue
        definitions.append(
            WorkflowDefinition(
                workflow_id=workflow_id,
                tool_id=str(manifest.get("id", "")),
                tool_name=str(manifest.get("name", manifest.get("id", ""))),
                entrypoint=legacy_entrypoint,
                tool_enabled=bool(manifest.get("enabled", True)),
                intake_kind=str(manifest.get("intakeKind", "")),
                options={},
            )
        )
    return definitions


def _definition_from_workflow_config(
    manifest: dict[str, Any],
    workflow_id: str,
    raw_definition: Any,
) -> WorkflowDefinition | None:
    options: dict[str, Any] = {}
    if isinstance(raw_definition, str):
        entrypoint = raw_definition
    elif isinstance(raw_definition, dict):
        entrypoint = str(raw_definition.get("entrypoint") or raw_definition.get("run") or _legacy_run_entrypoint(manifest) or "")
        options = {
            key: value
            for key, value in raw_definition.items()
            if key not in {"entrypoint", "run"}
        }
    else:
        return None

    if not entrypoint:
        return None

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tool_id=str(manifest.get("id", "")),
        tool_name=str(manifest.get("name", manifest.get("id", ""))),
        entrypoint=entrypoint,
        tool_enabled=bool(manifest.get("enabled", True)),
        intake_kind=str(options.get("intakeKind") or manifest.get("intakeKind", "")),
        options=options,
    )


def _legacy_run_entrypoint(manifest: dict[str, Any]) -> str:
    entrypoints = manifest.get("entrypoints", {})
    if not isinstance(entrypoints, dict):
        return ""
    return str(entrypoints.get("run") or "")


def _tool_manifest(tool_id: str) -> dict[str, Any]:
    for manifest in list_tool_manifests():
        if manifest.get("id") == tool_id:
            return manifest
    raise WorkflowRegistryError(f"tool is not registered: {tool_id}")
