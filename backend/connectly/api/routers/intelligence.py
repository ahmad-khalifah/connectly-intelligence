"""Community intelligence briefs (deterministic, with an optional checked AI summary)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from connectly.ai.brief import BriefError, build_brief, narrative
from connectly.ai.providers import ProviderError, get_provider
from connectly.api.deps import get_session
from connectly.core.config import get_settings

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


class BriefIn(BaseModel):
    area_id: int
    sector: str
    question: str | None = Field(None, max_length=500)
    summarise: bool = True


@router.get("/status")
def status() -> dict:
    s = get_settings()
    try:
        p = get_provider(s)
    except ProviderError as e:
        return {"enabled": False, "provider": s.ai_provider, "error": str(e)}
    return {"enabled": p is not None, "provider": s.ai_provider, "model": p.model if p else None}


@router.post("/brief")
def brief(body: BriefIn, session: Session = Depends(get_session)) -> dict:
    try:
        b = build_brief(session, body.area_id, body.sector, body.question)
    except BriefError as e:
        raise HTTPException(404 if str(e).startswith("no area") else 422, str(e)) from None
    b["narrative"] = (
        narrative(b, use_default=body.summarise)
        if body.summarise
        else {"status": "skipped", "text": None, "problems": [], "message": None}
    )
    return b
