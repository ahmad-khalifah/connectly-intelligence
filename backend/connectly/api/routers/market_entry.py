"""Market entry intelligence."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from connectly.api.deps import get_session
from connectly.services import market_entry as me

router = APIRouter(prefix="/api/v1", tags=["market entry"])


@router.get("/market-entry/objectives")
def objectives() -> dict[str, str]:
    return me.OBJECTIVES


@router.post("/market-entry")
def market_entry(body: me.MarketEntryIn, session: Session = Depends(get_session)) -> dict:
    """Rank candidate areas and report the brief's twelve market entry items, each tagged as
    fact, derived, recommendation or gap."""
    try:
        return me.analyse(session, body)
    except me.MarketEntryError as e:
        raise HTTPException(422, str(e)) from None
