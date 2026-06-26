from __future__ import annotations

import pytest

from app.workflow_registry import (
    WorkflowRegistryError,
    ensure_workflow_available,
    get_workflow_definition,
    list_workflow_definitions,
)


def test_workflow_definitions_are_loaded_from_tool_manifests():
    definitions = {item.workflow_id: item for item in list_workflow_definitions()}

    assert "lead-import-to-feishu" in definitions
    assert "product-main-image" in definitions
    assert "product-main-detail" in definitions
    assert definitions["product-main-detail"].tool_id == "product-main-image"
    assert definitions["product-main-detail"].option("writesTraceFields") is True


def test_unknown_workflow_raises_registry_error():
    with pytest.raises(WorkflowRegistryError, match="workflow is not registered"):
        get_workflow_definition("unknown-workflow")


def test_disabled_workflow_is_not_available(temp_db):
    with temp_db.get_conn() as conn:
        conn.execute("UPDATE workflows SET enabled = 0 WHERE id = ?", ("product-main-image",))

        with pytest.raises(WorkflowRegistryError, match="workflow is disabled"):
            ensure_workflow_available(conn, "product-main-image")


def test_disabled_module_is_not_available(temp_db):
    with temp_db.get_conn() as conn:
        conn.execute("UPDATE modules SET enabled = 0 WHERE id = ?", ("product-main-image",))

        with pytest.raises(WorkflowRegistryError, match="workflow module is disabled"):
            ensure_workflow_available(conn, "product-main-image")
