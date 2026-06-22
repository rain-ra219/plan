# New Tool Template

Copy this checklist when adding a new tool under `backend/tools/<tool_id>/`.
Do not put a real `manifest.json` in this template directory, otherwise the
registry will treat it as an installed tool.

## Required Files

```text
backend/tools/<tool_id>/
  manifest.json
  README.md
```

## Optional Runtime Files

```text
service.py     core business logic
workflow.py    multi-step workflow logic
listener.py    polling or event listener logic
client.py      external API client
schemas.py     input and output models
```

## Manifest Checklist

```json
{
  "id": "tool-id",
  "name": "Tool name",
  "version": "1.0.0",
  "type": "workflow",
  "enabled": true,
  "description": "What this tool does.",
  "provides": ["capability.name"],
  "uses": ["dependency.capability"],
  "entrypoints": {
    "run": "backend.tools.tool_id.workflow:run"
  },
  "configSchema": {},
  "dataTables": [],
  "failureIsolation": "How this tool fails without breaking the platform."
}
```

## Before Enabling

- Confirm the tool has its own folder.
- Confirm it does not import another tool's private internals.
- Confirm inputs and outputs are documented.
- Confirm every runtime call writes task logs or workflow run records.
- Confirm failure only disables this tool or this workflow step.
