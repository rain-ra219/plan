# Tool Architecture

This project should stay clean as more automations are added. The rule is:

```text
backend/app   = platform core
backend/tools = replaceable tools and workflows
```

## Platform Core Responsibilities

The core system owns stable platform concerns:

- HTTP API
- authentication and permissions later
- configuration storage
- capability routing
- task scheduling
- workflow run records
- task logs
- health and error status
- graceful degradation

Core code should not contain deep business logic for one specific tool.

## Tool Responsibilities

A tool owns one replaceable capability provider, listener, or workflow.

Examples:

- `lead_import`: CSV lead cleaning and customer merge workflow
- `feishu_sync`: Feishu Bitable table provider
- `feishu_intake`: Feishu CSV submission listener
- `image_generate`: image generation provider
- `product_page_generate`: product page generation workflow

Each tool should live under:

```text
backend/tools/<tool_id>/
  manifest.json
  README.md
  service.py
  workflow.py
  schemas.py
```

Only keep files that are needed. For example, a listener can use `listener.py`;
an external integration can use `client.py`.

## Dependency Rule

Tools should depend on capabilities, not concrete modules.

Prefer:

```text
lead_import -> table.write
table.write -> feishu_sync
```

Avoid:

```text
lead_import imports feishu_sync internals directly
```

This lets the platform replace Feishu with Airtable, Notion, CRM, or a local
database provider without rewriting the lead workflow.

## Deletion Rule

Deleting one tool should not break the platform or unrelated tools.

Before removing a tool, check:

- what it `provides`
- what other tools `use`
- which configs belong to it
- which database tables are historical audit data and should not be deleted

The platform should treat a missing tool as a disabled capability, not as a
startup crash.

## Concurrency Rule

Installed tools do not cost much by themselves. Runtime pressure comes from
active jobs:

- how many users submit tasks at the same time
- how many long-running AI calls are active
- whether image/file processing runs locally
- whether external APIs are slow or rate-limited

The migration path is:

```text
MVP: FastAPI + SQLite + database task tables
Next: background worker thread for light listeners
Scale: Redis + Celery/RQ workers
Heavy tools: independent worker containers
```

## Current Migration Stage

The project is currently at metadata-first modularization:

1. Keep validated runtime code in `backend/app`.
2. Add `backend/tools/*/manifest.json` for every real tool.
3. Expose manifests through `GET /api/tools`.
4. Move runtime code into each tool folder one tool at a time.

This keeps the working Feishu workflow stable while creating a long-term home
for future tools.
