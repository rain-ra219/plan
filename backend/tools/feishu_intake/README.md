# Feishu Intake Tool

This tool listens to a Feishu Bitable CSV submission table.

Current flow:

```text
Feishu CSV 提交任务表 -> scan pending records -> download CSV attachment -> run lead-import -> write status back to Feishu
```

Runtime code currently remains in `backend/app/intake_listener.py`.

Deletion impact:

- Team members can no longer submit CSV through Feishu as a task queue.
- Admin CSV upload and existing lead import workflow can still run.
