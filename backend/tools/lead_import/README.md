# Lead Import Tool

This tool represents the validated CSV lead workflow:

```text
CSV -> lead cleaning -> customer merge -> table.write leads -> table.write customers
```

Runtime code currently remains in `backend/app/lead_workflow.py`.
The manifest exists so the platform can discover and manage this workflow as an
independent tool before moving code into this directory.

Deletion impact:

- Removing this tool disables CSV lead import workflows.
- It should not remove local historical data, task logs, or Feishu mappings.
