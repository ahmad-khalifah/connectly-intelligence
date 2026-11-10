"""Qualitative community claims: entered by researchers, reviewed by a second person."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.api.deps import client_ip, current_user, get_session, require_researcher
from connectly.models import CLAIM_ATTRIBUTES, AdminArea, Claim, Settlement, User
from connectly.services import audit
from connectly.services.personal_data import personal_data_found

router = APIRouter(prefix="/api/v1", tags=["claims"])

Subject = Literal["admin_area", "settlement"]
# A person enters claims, so they are never modelled or AI-generated.
ClaimValueType = Literal["measured", "estimated", "derived", "assumed"]
ReviewStatus = Literal["source_verified", "field_verified", "disputed"]
CLAIM_FIELDS = (
    "attribute",
    "value_text",
    "value_type",
    "source_description",
    "source_url",
    "observed_on",
    "verification_status",
    "verification_note",
    "is_active",
)


class ClaimIn(BaseModel):
    subject_type: Subject
    subject_id: int
    attribute: str
    value_text: str = Field(min_length=2, max_length=4000)
    value_type: ClaimValueType
    source_description: str = Field(min_length=5, max_length=2000)
    source_url: str | None = Field(None, max_length=1024)
    observed_on: str | None = Field(None, max_length=32, description="Date or period observed")

    @field_validator("attribute")
    @classmethod
    def known_attribute(cls, v: str) -> str:
        if v not in CLAIM_ATTRIBUTES:
            raise ValueError(f"attribute must be one of: {', '.join(CLAIM_ATTRIBUTES)}")
        return v

    @field_validator("source_url")
    @classmethod
    def http_url(cls, v: str | None) -> str | None:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("source_url must start with http:// or https://")
        return v or None


class ClaimUpdateIn(BaseModel):
    value_text: str | None = Field(None, min_length=2, max_length=4000)
    value_type: ClaimValueType | None = None
    source_description: str | None = Field(None, min_length=5, max_length=2000)
    source_url: str | None = Field(None, max_length=1024)
    observed_on: str | None = Field(None, max_length=32)


class ReviewIn(BaseModel):
    status: ReviewStatus
    note: str = Field(min_length=5, max_length=2000, description="What was checked, and how")


class RetireIn(BaseModel):
    note: str = Field(min_length=5, max_length=2000)


CLAIM_SELECT = """
    SELECT c.id, c.subject_type, c.subject_id, c.attribute, c.value_text, c.value_type,
           c.source_description, c.source_url, c.observed_on, c.verification_status,
           c.verification_note, c.verified_at, c.is_active, c.created_at, c.updated_at,
           c.created_by_id, cu.full_name AS created_by, vu.full_name AS verified_by,
           CASE c.subject_type WHEN 'admin_area' THEN a.name ELSE s.name END AS subject_name
    FROM claim c
    LEFT JOIN app_user cu ON cu.id = c.created_by_id
    LEFT JOIN app_user vu ON vu.id = c.verified_by_id
    LEFT JOIN admin_area a ON c.subject_type = 'admin_area' AND a.id = c.subject_id
    LEFT JOIN settlement s ON c.subject_type = 'settlement' AND s.id = c.subject_id
"""


def _claim_out(session: Session, claim_id: int) -> dict:
    row = session.execute(text(CLAIM_SELECT + " WHERE c.id = :id"), {"id": claim_id}).mappings()
    r = row.first()
    if r is None:
        raise HTTPException(404, f"no claim {claim_id}")
    return dict(r) | {"attribute_label": CLAIM_ATTRIBUTES.get(r["attribute"])}


def _check_text(*texts: str | None) -> None:
    found = personal_data_found(*texts)
    if found:
        raise HTTPException(
            422,
            f"remove {' and '.join(found)}: Connectly records facts about places, "
            "not personal details of residents",
        )


@router.get("/claims/attributes")
def claim_attributes(_: User = Depends(current_user)) -> dict[str, str]:
    return CLAIM_ATTRIBUTES


@router.get("/claims")
def list_claims(
    subject_type: Subject | None = None,
    subject_id: int | None = None,
    status: str | None = None,
    include_retired: bool = False,
    limit: int = Query(200, ge=1, le=1000),
    _: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    where, params = [], {"limit": limit}
    if subject_type:
        where.append("c.subject_type = :st")
        params["st"] = subject_type
    if subject_id is not None:
        where.append("c.subject_id = :sid")
        params["sid"] = subject_id
    if status:
        where.append("c.verification_status = :status")
        params["status"] = status
    if not include_retired:
        where.append("c.is_active")
    sql = CLAIM_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY c.updated_at DESC LIMIT :limit"
    return [
        dict(r) | {"attribute_label": CLAIM_ATTRIBUTES.get(r["attribute"])}
        for r in session.execute(text(sql), params).mappings()
    ]


@router.post("/claims", status_code=201)
def create_claim(
    body: ClaimIn,
    request: Request,
    user: User = Depends(require_researcher),
    session: Session = Depends(get_session),
) -> dict:
    model = AdminArea if body.subject_type == "admin_area" else Settlement
    if session.get(model, body.subject_id) is None:
        raise HTTPException(404, f"no {body.subject_type} {body.subject_id}")
    _check_text(body.value_text, body.source_description)
    claim = Claim(**body.model_dump(), created_by_id=user.id)
    session.add(claim)
    session.flush()
    audit.record(
        session,
        user,
        "create",
        "claim",
        claim.id,
        f"{body.attribute} for {body.subject_type} {body.subject_id}",
        {"after": audit.snapshot(claim, CLAIM_FIELDS)},
        ip=client_ip(request),
    )
    session.commit()
    return _claim_out(session, claim.id)


def _get_claim(session: Session, claim_id: int) -> Claim:
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(404, f"no claim {claim_id}")
    return claim


@router.patch("/claims/{claim_id}")
def update_claim(
    claim_id: int,
    body: ClaimUpdateIn,
    request: Request,
    user: User = Depends(require_researcher),
    session: Session = Depends(get_session),
) -> dict:
    claim = _get_claim(session, claim_id)
    if claim.created_by_id != user.id and user.role != "admin":
        raise HTTPException(403, "only the author or an admin can edit a claim")
    if not claim.is_active:
        raise HTTPException(409, "retired claims cannot be edited")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "nothing to change")
    _check_text(changes.get("value_text"), changes.get("source_description"))
    before = audit.snapshot(claim, CLAIM_FIELDS)
    for k, v in changes.items():
        setattr(claim, k, v)
    # Any edit needs a fresh review.
    claim.verification_status = "unverified"
    claim.verified_by_id = None
    claim.verified_at = None
    claim.verification_note = None
    audit.record(
        session,
        user,
        "update",
        "claim",
        claim.id,
        None,
        audit.diff(before, audit.snapshot(claim, CLAIM_FIELDS)),
        ip=client_ip(request),
    )
    session.commit()
    return _claim_out(session, claim.id)


@router.post("/claims/{claim_id}/review")
def review_claim(
    claim_id: int,
    body: ReviewIn,
    request: Request,
    user: User = Depends(require_researcher),
    session: Session = Depends(get_session),
) -> dict:
    claim = _get_claim(session, claim_id)
    if not claim.is_active:
        raise HTTPException(409, "retired claims cannot be reviewed")
    if claim.created_by_id == user.id:
        raise HTTPException(403, "a claim must be reviewed by someone other than its author")
    _check_text(body.note)
    before = audit.snapshot(claim, CLAIM_FIELDS)
    claim.verification_status = body.status
    claim.verification_note = body.note
    claim.verified_by_id = user.id
    claim.verified_at = datetime.now(UTC)
    audit.record(
        session,
        user,
        "review",
        "claim",
        claim.id,
        body.status,
        audit.diff(before, audit.snapshot(claim, CLAIM_FIELDS)),
        ip=client_ip(request),
    )
    session.commit()
    return _claim_out(session, claim.id)


@router.post("/claims/{claim_id}/retire")
def retire_claim(
    claim_id: int,
    body: RetireIn,
    request: Request,
    user: User = Depends(require_researcher),
    session: Session = Depends(get_session),
) -> dict:
    claim = _get_claim(session, claim_id)
    if claim.created_by_id != user.id and user.role != "admin":
        raise HTTPException(403, "only the author or an admin can retire a claim")
    before = audit.snapshot(claim, CLAIM_FIELDS)
    claim.is_active = False
    claim.verification_status = "retired"
    claim.verification_note = body.note
    audit.record(
        session,
        user,
        "retire",
        "claim",
        claim.id,
        body.note,
        audit.diff(before, audit.snapshot(claim, CLAIM_FIELDS)),
        ip=client_ip(request),
    )
    session.commit()
    return _claim_out(session, claim.id)


@router.get("/claims/{claim_id}/history")
def claim_history(
    claim_id: int, _: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict]:
    _get_claim(session, claim_id)
    rows = session.execute(
        text(
            "SELECT created_at, actor, action, summary, changes FROM audit_log "
            "WHERE entity_type = 'claim' AND entity_id = :id ORDER BY created_at, id"
        ),
        {"id": str(claim_id)},
    ).mappings()
    return [dict(r) for r in rows]
