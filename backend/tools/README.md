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

## Current Runtime Policy

The MVP runtime has been moved into tool directories:

1. `lead_import` owns CSV lead cleaning and customer merge workflow code.
2. `feishu_sync` owns the Feishu Bitable API client code.
3. `feishu_intake` owns the Feishu CSV submission listener code.
4. `backend/app` keeps platform core code plus thin compatibility wrappers for
   old imports.
5. Every new business tool should start in `backend/tools/<tool_id>/` and expose
   its metadata through `manifest.json`.
