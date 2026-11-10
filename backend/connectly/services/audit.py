"""Writing the audit log."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from connectly.models import AuditLog, User


def _plain(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


def snapshot(obj: Any, fields: tuple[str, ...]) -> dict:
    return {f: _plain(getattr(obj, f)) for f in fields}


def diff(before: dict, after: dict) -> dict:
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {"before": {k: before.get(k) for k in keys}, "after": {k: after[k] for k in keys}}


def record(
    session: Session,
    actor: User | str,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    summary: str | None = None,
    changes: dict | None = None,
    ip: str | None = None,
) -> None:
    user = actor if isinstance(actor, User) else None
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            actor=user.email if user else str(actor),
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            summary=summary,
            changes=changes,
            ip=ip,
        )
    )
