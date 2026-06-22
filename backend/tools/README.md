# Tool Directory Standard

`backend/tools` is the home for pluggable business tools and workflows.
The platform core stays in `backend/app`; tool-specific code, manifests, and
documentation should live under one directory per tool.

## Directory Layout

```text
backend/tools/
  <tool_id>/
    manifest.json
    README.md
    service.py
    workflow.py
    schemas.py
```

Use only the files that make sense for the tool. A listener can use
`listener.py` instead of `workflow.py`; an API integration can use `client.py`.

## Rules

- The platform core owns routing, configuration, scheduling, logging, and status.
- A tool owns its own business logic and should not modify another tool directly.
- Tools communicate through capabilities such as `table.write`, `file.download`,
  `lead.normalize`, and `customer.merge`.
- Every tool must have a `manifest.json` before runtime code is migrated into it.
- Removing a tool should only disable the capabilities it provides; the platform
  should still boot and other tools should continue to run.

## Manifest Fields

```json
{
  "id": "tool-id",
  "name": "Human name",
  "version": "1.0.0",
  "type": "workflow | listener | capability-provider",
  "enabled": true,
  "provides": ["capability.name"],
  "uses": ["dependency.capability"],
  "entrypoints": {
    "run": "python.import.path:function_name"
  },
  "configSchema": {},
  "dataTables": [],
  "failureIsolation": "Tool errors must be logged and must not stop unrelated tools."
}
```

## Current Migration Policy

The current MVP runtime still lives in `backend/app` because it has already been
validated with Feishu. The first migration step is metadata-only:

1. Put every real tool under `backend/tools/<tool_id>/manifest.json`.
2. Expose manifests through `GET /api/tools`.
3. Move runtime code tool by tool after each manifest is stable.
