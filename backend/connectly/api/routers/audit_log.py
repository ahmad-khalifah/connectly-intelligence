"""The audit log, for administrators."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.api.deps import get_session, require_admin
from connectly.models import User

router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.get("/audit")
def audit_entries(
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: int | None = None,
    action: str | None = None,
    before: datetime | None = Query(None, description="Return entries older than this"),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[dict]:
    where, params = [], {"limit": limit}
    for col, val in (
        ("entity_type", entity_type),
        ("entity_id", entity_id),
        ("user_id", user_id),
        ("action", action),
    ):
        if val is not None:
            where.append(f"{col} = :{col}")
            params[col] = val
    if before is not None:
        where.append("created_at < :before")
        params["before"] = before
    sql = (
        "SELECT id, created_at, user_id, actor, action, entity_type, entity_id, summary, "
        "changes, ip FROM audit_log"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT :limit"
    return [dict(r) for r in session.execute(text(sql), params).mappings()]


@router.get("/ingest/runs")
def ingest_runs(
    limit: int = Query(50, ge=1, le=500),
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Dataset loads, newest first, with their notes and errors."""
    rows = session.execute(
        text(
            "SELECT r.*, d.key AS dataset_key, d.title AS dataset_title FROM ingest_run r "
            "LEFT JOIN dataset d ON d.id = r.dataset_id ORDER BY r.id DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).mappings()
    return [dict(r) for r in rows]
