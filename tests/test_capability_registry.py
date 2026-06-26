from __future__ import annotations

import pytest

from app.capability_registry import (
    CapabilityRegistryError,
    capability_module_id,
    get_capability_definition,
)


def test_capability_resolves_database_provider_when_enabled(temp_db):
    with temp_db.get_conn() as conn:
        conn.execute("UPDATE modules SET enabled = 1 WHERE id = ?", ("image-generator",))
        definition = get_capability_definition(conn, "image.generate")

    assert definition.capability == "image.generate"
    assert definition.module_id == "image-generator"
    assert definition.entrypoint == "tools.image_generate.service:generate_image"
    assert definition.capability_enabled is True
    assert definition.module_enabled is True


def test_disabled_provider_module_blocks_capability(temp_db):
    with temp_db.get_conn() as conn:
        with pytest.raises(CapabilityRegistryError, match="provider module is disabled"):
            get_capability_definition(conn, "image.generate")


def test_manifest_provider_is_used_when_capability_row_is_missing(temp_db):
    with temp_db.get_conn() as conn:
        conn.execute("UPDATE modules SET enabled = 1 WHERE id = ?", ("image-generator",))
        conn.execute("DELETE FROM capabilities WHERE name = ?", ("image.generate",))
        definition = get_capability_definition(conn, "image.generate")

    assert definition.module_id == "image-generator"
    assert definition.entrypoint == "tools.image_generate.service:generate_image"


def test_capability_module_id_returns_default_for_unknown_capability(temp_db):
    with temp_db.get_conn() as conn:
        module_id = capability_module_id(conn, "unknown.capability", default="fallback")

    assert module_id == "fallback"
