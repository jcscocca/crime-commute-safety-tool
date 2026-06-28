from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db import get_engine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    # Readiness probe: confirm the database is reachable, not just that the process is up,
    # so an orchestrator/healthcheck can tell "serving" from "running but DB is down".
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any DB/connection failure means not-ready
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}
