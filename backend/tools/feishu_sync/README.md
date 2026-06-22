# Feishu Sync Tool

This tool is the Feishu implementation of table and file capabilities.

It should be replaceable by another provider later, such as Airtable, Notion,
CRM, or a PostgreSQL-backed table provider.

Runtime code lives in `client.py`.
`backend/app/feishu_client.py` is now only a compatibility wrapper for old imports.

Deletion impact:

- `table.write` to Feishu becomes unavailable.
- Local processing can still run and should degrade to local database results.
- Existing historical logs and mappings should remain for audit.
