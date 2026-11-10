"""Needs assessment: relative access-gap scores by sector, with evidence and confidence."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from connectly.api.deps import get_session
from connectly.services import needs

router = APIRouter(prefix="/api/v1/needs", tags=["needs"])


@router.get("/models")
def need_models(session: Session = Depends(get_session)) -> list[dict]:
    """Indicators and weights used for each sector."""
    return needs.models(session)


@router.get("/assessment")
def assessment(
    sector: str,
    level: Literal["state", "lga", "ward"],
    scope_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Rank every `level` area inside `scope_id` by its access gap in `sector`."""
    try:
        return needs.assess(session, sector, level, scope_id)
    except needs.NeedsError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/areas/{area_id}")
def area_needs(area_id: int, session: Session = Depends(get_session)) -> dict:
    """This area's gap score in every sector, compared with similar areas in its state."""
    try:
        return needs.area_summary(session, area_id)
    except needs.NeedsError as e:
        raise HTTPException(404 if "no area" in str(e) else 422, str(e)) from None
