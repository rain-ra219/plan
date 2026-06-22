# Lead Import Tool

This tool represents the validated CSV lead workflow:

```text
CSV -> lead cleaning -> customer merge -> table.write leads -> table.write customers
```

Runtime code lives in `workflow.py`.
`backend/app/lead_workflow.py` is now only a compatibility wrapper for old imports.

Deletion impact:

- Removing this tool disables CSV lead import workflows.
- It should not remove local historical data, task logs, or Feishu mappings.
