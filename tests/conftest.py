from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import database as db  # noqa: E402


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    storage_dir = tmp_path / "storage"

    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "STORAGE_DIR", storage_dir)
    monkeypatch.setattr(db, "UPLOAD_DIR", storage_dir / "uploads")
    monkeypatch.setattr(db, "DB_PATH", data_dir / "platform.db")

    db.init_db()
    return db
