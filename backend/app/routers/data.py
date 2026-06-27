from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..database import get_conn, row_to_dict

router = APIRouter()


@router.get("/api/leads")
def list_leads(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY updated_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@router.get("/api/customers")
def list_customers(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM customers ORDER BY updated_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
        return [row_to_dict(row) for row in rows]
