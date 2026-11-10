"""Technology matching for a community and sector."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from connectly.api.deps import get_session
from connectly.services import matching

router = APIRouter(prefix="/api/v1", tags=["matching"])


class MatchIn(BaseModel):
    area_id: int
    sector: str
    need: str | None = Field(None, description="A need code, e.g. health.telemedicine")
    target_groups: list[str] = Field(default_factory=list)
    max_price_ngn: int | None = Field(None, ge=0, description="Highest acceptable price")


@router.post("/matching")
def run_matching(body: MatchIn, session: Session = Depends(get_session)) -> dict:
    """Rank published solutions for the area on the eight criteria, with reasons."""
    try:
        return matching.match(
            session, body.area_id, body.sector, body.need, body.target_groups, body.max_price_ngn
        )
    except matching.MatchingError as e:
        raise HTTPException(404 if str(e).startswith("no area") else 422, str(e)) from None
