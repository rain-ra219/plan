from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tool_registry import list_tool_manifests
from .workflow_registry import load_entrypoint


class CapabilityRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class CapabilityDefinition:
    capability: str
    module_id: str
    module_name: str
    entrypoint: str
    capability_enabled: bool
    module_enabled: bool


def get_capability_definition(
    conn: Any,
    capability: str,
    *,
    require_enabled: bool = True,
) -> CapabilityDefinition:
    row = conn.execute(
        """
        SELECT c.name, c.enabled AS capability_enabled, c.provider_module_id,
               m.name AS module_name, m.enabled AS module_enabled
        FROM capabilities c
        LEFT JOIN modules m ON m.id = c.provider_module_id
        WHERE c.name = ?
        """,
        (capability,),
    ).fetchone()
    if not row:
        return _manifest_capability_definition(conn, capability, require_enabled=require_enabled)

    module_id = row["provider_module_id"]
    manifest = _tool_manifest(module_id)
    entrypoint = _capability_entrypoint(manifest, capability)
    definition = CapabilityDefinition(
        capability=capability,
        module_id=module_id,
        module_name=row["module_name"] or str(manifest.get("name") or module_id),
        entrypoint=entrypoint,
        capability_enabled=bool(row["capability_enabled"]),
        module_enabled=bool(row["module_enabled"]) if row["module_enabled"] is not None else bool(manifest.get("enabled", True)),
    )

    if require_enabled:
        if not definition.capability_enabled:
            raise CapabilityRegistryError(f"capability is disabled: {capability}")
        if not definition.module_enabled:
            raise CapabilityRegistryError(f"capability provider module is disabled: {module_id}")
        if not manifest.get("enabled", True):
            raise CapabilityRegistryError(f"capability provider tool is disabled: {module_id}")
    return definition


def call_capability(conn: Any, capability: str, *args: Any, **kwargs: Any) -> Any:
    definition = get_capability_definition(conn, capability)
    function = load_entrypoint(definition.entrypoint)
    return function(*args, **kwargs)


def capability_module_id(conn: Any, capability: str, default: str = "") -> str:
    try:
        return get_capability_definition(conn, capability, require_enabled=False).module_id
    except CapabilityRegistryError:
        return default


def _tool_manifest(module_id: str) -> dict[str, Any]:
    for manifest in list_tool_manifests():
        if manifest.get("id") == module_id:
            return manifest
    raise CapabilityRegistryError(f"capability provider tool is not registered: {module_id}")


def _manifest_capability_definition(
    conn: Any,
    capability: str,
    *,
    require_enabled: bool,
) -> CapabilityDefinition:
    for manifest in list_tool_manifests():
        if capability not in [str(item) for item in manifest.get("provides", [])]:
            continue
        module_id = str(manifest.get("id", ""))
        module = conn.execute("SELECT name, enabled FROM modules WHERE id = ?", (module_id,)).fetchone()
        module_enabled = bool(module["enabled"]) if module and module["enabled"] is not None else bool(manifest.get("enabled", True))
        definition = CapabilityDefinition(
            capability=capability,
            module_id=module_id,
            module_name=(module["name"] if module else str(manifest.get("name") or module_id)),
            entrypoint=_capability_entrypoint(manifest, capability),
            capability_enabled=True,
            module_enabled=module_enabled,
        )
        if require_enabled:
            if not definition.module_enabled:
                raise CapabilityRegistryError(f"capability provider module is disabled: {module_id}")
            if not manifest.get("enabled", True):
                raise CapabilityRegistryError(f"capability provider tool is disabled: {module_id}")
        return definition
    raise CapabilityRegistryError(f"capability is not configured: {capability}")


def _capability_entrypoint(manifest: dict[str, Any], capability: str) -> str:
    capability_entrypoints = manifest.get("capabilityEntrypoints", {})
    if isinstance(capability_entrypoints, dict) and capability_entrypoints.get(capability):
        return str(capability_entrypoints[capability])

    entrypoints = manifest.get("entrypoints", {})
    if isinstance(entrypoints, dict):
        candidate_names = [
            capability,
            capability.replace(".", "_"),
            capability.rsplit(".", 1)[-1],
        ]
        for name in candidate_names:
            if entrypoints.get(name):
                return str(entrypoints[name])

    raise CapabilityRegistryError(
        f"capability entrypoint is not registered: {manifest.get('id', '')}.{capability}"
    )
