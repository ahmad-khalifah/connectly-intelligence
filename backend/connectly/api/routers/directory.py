"""Technology solutions directory: organisations and solutions, with review workflow.

Visibility: published solutions and active organisations are visible to every signed-in
user. Drafts, submissions and rejected records are visible to admins and to the company
account that owns them.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.api.deps import client_ip, current_user, get_session, require_admin, require_roles
from connectly.models import VERIFICATION_STATUSES, Organisation, Solution, User
from connectly.services import audit
from connectly.services.directory import (
    AUDIT_ORG_FIELDS,
    SOLUTION_SELECT,
    VOCABULARIES,
    DirectoryError,
    OrganisationIn,
    SolutionIn,
    apply_organisation,
    apply_solution,
    availability,
    publish,
    snapshot_solution,
)

router = APIRouter(prefix="/api/v1", tags=["directory"])
require_editor = require_roles("admin", "company")

Verification = Literal[VERIFICATION_STATUSES]  # type: ignore[valid-type]


class OrgReviewIn(BaseModel):
    status: Literal["active", "rejected", "retired"] | None = None
    verification_status: Verification | None = None
    note: str = Field(min_length=5, max_length=2000)


class SolutionStatusIn(BaseModel):
    status: Literal["draft", "submitted", "published", "rejected", "retired"]
    note: str | None = Field(None, max_length=2000)


class SolutionVerifyIn(BaseModel):
    verification_status: Verification
    note: str = Field(min_length=5, max_length=2000)


def _bad(e: DirectoryError) -> HTTPException:
    return HTTPException(422, str(e))


def _owns(user: User, organisation_id: int) -> bool:
    return user.role == "company" and user.organisation_id == organisation_id


@router.get("/directory/vocabularies")
def vocabularies(_: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    sectors = session.execute(
        text(
            "SELECT s.code, s.name, coalesce(json_agg(json_build_object('code', n.code, "
            "'name', n.name) ORDER BY n.sort_order) FILTER (WHERE n.id IS NOT NULL), '[]') AS needs "
            "FROM sector s LEFT JOIN need_category n ON n.sector_id = s.id "
            "GROUP BY s.id ORDER BY s.sort_order"
        )
    ).mappings()
    return VOCABULARIES | {"sectors": [dict(s) for s in sectors]}


# ------------------------------------------------------------------- organisations

ORG_SELECT = """
    SELECT o.*, st.name AS headquarters_state,
           (SELECT count(*) FROM solution s WHERE s.organisation_id = o.id
              AND s.status = 'published') AS published_solutions
    FROM organisation o LEFT JOIN admin_area st ON st.id = o.headquarters_state_id
"""


def _org_out(session: Session, org_id: int) -> dict:
    r = session.execute(text(ORG_SELECT + " WHERE o.id = :id"), {"id": org_id}).mappings().first()
    if r is None:
        raise HTTPException(404, f"no organisation {org_id}")
    return dict(r)


def _visible_org(user: User, row: dict) -> bool:
    return row["status"] == "active" or user.role == "admin" or _owns(user, row["id"])


@router.get("/organisations")
def list_organisations(
    q: str | None = Query(None, min_length=2),
    org_type: str | None = None,
    status: str | None = None,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    where, params = [], {}
    if q:
        where.append("(o.name ILIKE :q OR o.industry ILIKE :q)")
        params["q"] = f"%{q}%"
    if org_type:
        where.append("o.org_type = :t")
        params["t"] = org_type
    if user.role == "admin":
        if status:
            where.append("o.status = :s")
            params["s"] = status
    else:
        where.append("(o.status = 'active' OR o.id = :own)")
        params["own"] = user.organisation_id if user.role == "company" else -1
    sql = ORG_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY o.name"
    return [dict(r) for r in session.execute(text(sql), params).mappings()]


@router.get("/organisations/{org_id}")
def get_organisation(
    org_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    org = _org_out(session, org_id)
    if not _visible_org(user, org):
        raise HTTPException(404, f"no organisation {org_id}")
    return org | {"solutions": _solutions(session, user, organisation_id=org_id)}


@router.post("/organisations", status_code=201)
def create_organisation(
    body: OrganisationIn,
    request: Request,
    user: User = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict:
    if user.role == "company" and user.organisation_id is not None:
        raise HTTPException(409, "your account already manages an organisation")
    org = Organisation(
        created_by_id=user.id, status="active" if user.role == "admin" else "submitted"
    )
    try:
        apply_organisation(session, org, body)
    except DirectoryError as e:
        raise _bad(e) from None
    session.add(org)
    session.flush()
    if user.role == "company":
        user.organisation_id = org.id
    audit.record(
        session,
        user,
        "create",
        "organisation",
        org.id,
        org.name,
        {"after": audit.snapshot(org, AUDIT_ORG_FIELDS)},
        ip=client_ip(request),
    )
    session.commit()
    return _org_out(session, org.id)


def _get_org(session: Session, org_id: int) -> Organisation:
    org = session.get(Organisation, org_id)
    if org is None:
        raise HTTPException(404, f"no organisation {org_id}")
    return org


@router.put("/organisations/{org_id}")
def update_organisation(
    org_id: int,
    body: OrganisationIn,
    request: Request,
    user: User = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict:
    org = _get_org(session, org_id)
    if user.role != "admin" and not _owns(user, org_id):
        raise HTTPException(403, "you can only edit your own organisation")
    before = audit.snapshot(org, AUDIT_ORG_FIELDS)
    try:
        apply_organisation(session, org, body)
    except DirectoryError as e:
        raise _bad(e) from None
    if (
        user.role == "company"
        and audit.diff(before, audit.snapshot(org, AUDIT_ORG_FIELDS))["after"]
    ):
        org.verification_status = "unverified"  # the company changed what was checked
    audit.record(
        session,
        user,
        "update",
        "organisation",
        org.id,
        None,
        audit.diff(before, audit.snapshot(org, AUDIT_ORG_FIELDS)),
        ip=client_ip(request),
    )
    session.commit()
    return _org_out(session, org.id)


@router.post("/organisations/{org_id}/review")
def review_organisation(
    org_id: int,
    body: OrgReviewIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    org = _get_org(session, org_id)
    before = audit.snapshot(org, AUDIT_ORG_FIELDS)
    if body.status:
        org.status = body.status
    if body.verification_status:
        org.verification_status = body.verification_status
    org.verification_note = body.note
    audit.record(
        session,
        admin,
        "review",
        "organisation",
        org.id,
        body.note,
        audit.diff(before, audit.snapshot(org, AUDIT_ORG_FIELDS)),
        ip=client_ip(request),
    )
    session.commit()
    return _org_out(session, org.id)


# ------------------------------------------------------------------------ solutions


def _solutions(
    session: Session,
    user: User,
    *,
    organisation_id: int | None = None,
    sector: str | None = None,
    need: str | None = None,
    q: str | None = None,
    status: str | None = None,
    solution_id: int | None = None,
) -> list[dict]:
    where, params = ["s.is_active OR s.status = 'retired'"], {}
    if solution_id is not None:
        where.append("s.id = :sid")
        params["sid"] = solution_id
    if organisation_id is not None:
        where.append("s.organisation_id = :org")
        params["org"] = organisation_id
    if sector:
        where.append("sec.code = :sector")
        params["sector"] = sector
    if need:
        where.append(
            "EXISTS (SELECT 1 FROM solution_need sn JOIN need_category n ON n.id = "
            "sn.need_category_id WHERE sn.solution_id = s.id AND n.code = :need)"
        )
        params["need"] = need
    if q:
        where.append("(s.name ILIKE :q OR s.summary ILIKE :q OR o.name ILIKE :q)")
        params["q"] = f"%{q}%"
    own = user.organisation_id if user.role == "company" else -1
    if user.role != "admin":
        # Others see only what is published by an active organisation, plus their own.
        where.append(
            "((s.status = 'published' AND o.status = 'active') OR s.organisation_id = :own)"
        )
        params["own"] = own
    if status:
        where.append("s.status = :status")
        params["status"] = status
    sql = SOLUTION_SELECT + " WHERE " + " AND ".join(f"({w})" for w in where)
    sql += " ORDER BY o.name, s.name"
    return [dict(r) for r in session.execute(text(sql), params).mappings()]


@router.get("/solutions")
def list_solutions(
    sector: str | None = None,
    need: str | None = None,
    q: str | None = Query(None, min_length=2),
    status: str | None = None,
    organisation_id: int | None = None,
    area_id: int | None = Query(None, description="Add availability in this area"),
    available_only: bool = False,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = _solutions(
        session,
        user,
        organisation_id=organisation_id,
        sector=sector,
        need=need,
        q=q,
        status=status,
    )
    if area_id is not None:
        av = availability(session, area_id, [r["id"] for r in rows])
        for r in rows:
            r["availability"] = av.get(r["id"])
        if available_only:
            rows = [
                r for r in rows if r["availability"] in ("nationwide", "covers_area", "covers_part")
            ]
    return rows


def _solution_out(session: Session, user: User, solution_id: int) -> dict:
    rows = _solutions(session, user, solution_id=solution_id)
    if not rows:
        raise HTTPException(404, f"no solution {solution_id}")
    return rows[0]


@router.get("/solutions/{solution_id}")
def get_solution(
    solution_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    return _solution_out(session, user, solution_id)


@router.post("/organisations/{org_id}/solutions", status_code=201)
def create_solution(
    org_id: int,
    body: SolutionIn,
    request: Request,
    user: User = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict:
    org = _get_org(session, org_id)
    if user.role != "admin" and not _owns(user, org_id):
        raise HTTPException(403, "you can only add solutions to your own organisation")
    if org.status in ("rejected", "retired"):
        raise HTTPException(409, f"organisation is {org.status}")
    sol = Solution(organisation_id=org.id, created_by_id=user.id, status="draft")
    session.add(sol)
    try:
        apply_solution(session, sol, body)
    except DirectoryError as e:
        session.rollback()
        raise _bad(e) from None
    audit.record(
        session,
        user,
        "create",
        "solution",
        sol.id,
        sol.name,
        {"after": snapshot_solution(session, sol)},
        ip=client_ip(request),
    )
    session.commit()
    return _solution_out(session, user, sol.id)


def _get_solution(session: Session, solution_id: int) -> Solution:
    sol = session.get(Solution, solution_id)
    if sol is None:
        raise HTTPException(404, f"no solution {solution_id}")
    return sol


@router.put("/solutions/{solution_id}")
def update_solution(
    solution_id: int,
    body: SolutionIn,
    request: Request,
    user: User = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict:
    sol = _get_solution(session, solution_id)
    if user.role != "admin" and not _owns(user, sol.organisation_id):
        raise HTTPException(403, "you can only edit your own organisation's solutions")
    if sol.status == "retired":
        raise HTTPException(409, "retired solutions cannot be edited")
    before = snapshot_solution(session, sol)
    try:
        apply_solution(session, sol, body)
    except DirectoryError as e:
        session.rollback()
        raise _bad(e) from None
    after = snapshot_solution(session, sol)
    changes = audit.diff(before, after)
    if user.role == "company" and changes["after"]:
        # The provider's edits are reviewed again before they reach users.
        sol.verification_status = "unverified"
        if sol.status == "published":
            sol.status = "submitted"
        changes = audit.diff(before, snapshot_solution(session, sol))
    audit.record(session, user, "update", "solution", sol.id, None, changes, ip=client_ip(request))
    session.commit()
    return _solution_out(session, user, sol.id)


# Allowed status changes: (from, to) for company owners; admins may make any change.
COMPANY_TRANSITIONS = {
    ("draft", "submitted"),
    ("rejected", "submitted"),
    ("submitted", "draft"),
    ("published", "retired"),
}


@router.post("/solutions/{solution_id}/status")
def change_status(
    solution_id: int,
    body: SolutionStatusIn,
    request: Request,
    user: User = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict:
    sol = _get_solution(session, solution_id)
    if user.role != "admin":
        if not _owns(user, sol.organisation_id):
            raise HTTPException(403, "you can only manage your own organisation's solutions")
        if (sol.status, body.status) not in COMPANY_TRANSITIONS:
            raise HTTPException(
                403, f"you cannot move a solution from {sol.status} to {body.status}"
            )
    if body.status == "rejected" and not body.note:
        raise HTTPException(422, "give a reason when rejecting")
    if body.status == "published":
        org = session.get(Organisation, sol.organisation_id)
        if org.status != "active":
            raise HTTPException(409, "approve the organisation before publishing its solutions")
    before = sol.status
    if body.status == "published":
        publish(sol)
    else:
        sol.status = body.status
    sol.status_note = body.note
    sol.is_active = body.status != "retired"
    audit.record(
        session,
        user,
        "status",
        "solution",
        sol.id,
        body.note,
        {"before": {"status": before}, "after": {"status": sol.status}},
        ip=client_ip(request),
    )
    session.commit()
    return _solution_out(session, user, sol.id)


@router.post("/solutions/{solution_id}/verify")
def verify_solution(
    solution_id: int,
    body: SolutionVerifyIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    sol = _get_solution(session, solution_id)
    before = sol.verification_status
    sol.verification_status = body.verification_status
    sol.verification_note = body.note
    audit.record(
        session,
        admin,
        "verify",
        "solution",
        sol.id,
        body.note,
        {
            "before": {"verification_status": before},
            "after": {"verification_status": sol.verification_status},
        },
        ip=client_ip(request),
    )
    session.commit()
    return _solution_out(session, admin, sol.id)
