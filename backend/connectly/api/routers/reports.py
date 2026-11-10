"""Saved reports: run an analysis server-side, store its snapshot, export it as PDF."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.ai.brief import BriefError, build_brief, narrative
from connectly.api.deps import client_ip, current_user, get_session
from connectly.models import Report, User
from connectly.reports.pdf import render
from connectly.services import audit, market_entry, matching, needs

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class ReportIn(BaseModel):
    kind: Literal["brief", "needs", "matching", "market_entry"]
    params: dict
    title: str | None = Field(None, max_length=300)


def _run(session: Session, kind: str, params: dict) -> tuple[dict, str]:
    """Re-run the analysis from its parameters; the client's copy of a result is never trusted."""
    try:
        if kind == "brief":
            b = build_brief(
                session, int(params["area_id"]), params["sector"], params.get("question")
            )
            b["narrative"] = narrative(b) if params.get("summarise") else {"status": "skipped"}
            return b, f"{b['sector_name']}: {b['area']['place']}"
        if kind == "needs":
            r = needs.assess(session, params["sector"], params["level"], int(params["scope_id"]))
            return (
                r,
                f"{r['sector_name']} needs: {r['level'].upper() if r['level'] == 'lga' else r['level']}s in {r['scope']['name']}",
            )
        if kind == "matching":
            r = matching.match(
                session,
                int(params["area_id"]),
                params["sector"],
                params.get("need"),
                params.get("target_groups") or [],
                params.get("max_price_ngn"),
            )
            return r, f"{r['sector_name']} solutions for {r['area']['name']}"
        body = market_entry.MarketEntryIn(**params)
        r = market_entry.analyse(session, body)
        return r, f"Market entry: {r['product']['name']} ({r['sector_name']})"
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(422, f"invalid parameters: {e}") from None
    except (
        BriefError,
        needs.NeedsError,
        matching.MatchingError,
        market_entry.MarketEntryError,
    ) as e:
        raise HTTPException(422, str(e)) from None


LIST_SQL = """
    SELECT r.id, r.kind, r.title, r.params, r.created_at, r.created_by_id, u.full_name AS created_by
    FROM report r LEFT JOIN app_user u ON u.id = r.created_by_id
"""


def _get(session: Session, user: User, report_id: int, full: bool = False) -> dict:
    cols = LIST_SQL.replace("r.created_at,", "r.created_at, r.result," if full else "r.created_at,")
    row = session.execute(text(cols + " WHERE r.id = :id"), {"id": report_id}).mappings().first()
    if row is None or (user.role != "admin" and row["created_by_id"] != user.id):
        raise HTTPException(404, f"no report {report_id}")
    return dict(row)


@router.post("", status_code=201)
def create_report(
    body: ReportIn,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    result, default_title = _run(session, body.kind, body.params)
    report = Report(
        kind=body.kind,
        title=(body.title or default_title)[:300],
        params=body.params,
        result=result,
        created_by_id=user.id,
    )
    session.add(report)
    session.flush()
    audit.record(session, user, "create", "report", report.id, report.title, ip=client_ip(request))
    session.commit()
    return _get(session, user, report.id)


@router.get("")
def list_reports(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict]:
    sql = (
        LIST_SQL
        + ("" if user.role == "admin" else " WHERE r.created_by_id = :u")
        + " ORDER BY r.created_at DESC LIMIT 200"
    )
    return [dict(r) for r in session.execute(text(sql), {"u": user.id}).mappings()]


@router.get("/{report_id}")
def get_report(
    report_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    return _get(session, user, report_id, full=True)


@router.get("/{report_id}/pdf")
def report_pdf(
    report_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> Response:
    r = _get(session, user, report_id, full=True)
    pdf = render(r)
    name = re.sub(r"[^A-Za-z0-9]+", "-", r["title"]).strip("-")[:80] or "report"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="connectly-{report_id}-{name}.pdf"'},
    )


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    r = _get(session, user, report_id)
    session.execute(text("DELETE FROM report WHERE id = :id"), {"id": report_id})
    audit.record(session, user, "delete", "report", report_id, r["title"], ip=client_ip(request))
    session.commit()
