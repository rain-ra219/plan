# Feishu Intake Tool

This tool listens to a Feishu Bitable CSV submission table.

Current flow:

```text
Feishu 任务表 -> scan pending records -> enqueue task_queue -> worker executes workflow -> write status back to Feishu
```

Runtime code lives in `listener.py`.
`backend/app/intake_listener.py` is now only a compatibility wrapper for old imports.

The listener only discovers pending Feishu records and writes queue tasks. The
queue worker owns the slower workflow execution, so scans stay quick and queue
backlog can be inspected from the admin console.

Default queue controls:

- `TASK_QUEUE_WORKERS=5`
- `TASK_QUEUE_TOTAL_CONCURRENCY=5`
- `TASK_QUEUE_IMAGE_CONCURRENCY=3`
- `TASK_QUEUE_CSV_CONCURRENCY=2`

Network-like failures such as HTTP 429/5xx, timeout, SSL EOF, and remote
disconnects are retried up to 3 attempts with a short backoff. Configuration and
field errors fail directly so bad tasks do not loop forever.

Deletion impact:

- Team members can no longer submit CSV through Feishu as a task queue.
- Admin CSV upload and existing lead import workflow can still run.
