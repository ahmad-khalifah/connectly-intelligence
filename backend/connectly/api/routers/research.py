"""Research intelligence: live web research with Gemini, analysis of submitted sources, and the
findings they produce. A separate service; the analytics and matching engines never call it.

Live answers are returned to the requesting user only and never stored. Findings are stored only
from sources a researcher submitted by URL, with a verbatim quote checked against the source.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectly.ai.gemini import FREE_SEARCH_MODELS, FREE_TEXT_MODELS, GeminiClient, GeminiError
from connectly.api.deps import current_user, get_session, require_roles
from connectly.core.config import get_settings
from connectly.models import AIUsage, User
from connectly.research import service
from connectly.research.fetch import FetchError, fetch
from connectly.research.service import ResearchError

router = APIRouter(prefix="/api/v1/research", tags=["research"])

RESEARCHERS = ("admin", "researcher")
GEMINI_HTTP = {"disabled": 503, "not_free": 409, "quota": 429, "rate_limited": 429}

FREE_TIER_NOTICE = (
    "Gemini is used on Google's free tier only. Google may use free-tier prompts and answers to "
    "improve its products, and people may review them, so do not enter personal, sensitive or "
    "confidential information."
)


def gemini_factory() -> Callable[[Session, int | None], GeminiClient]:
    """Overridden in tests to inject a mock transport."""
    return lambda session, user_id: GeminiClient(session, user_id=user_id)


def source_fetcher() -> Callable:
    return fetch


def _fail(e: Exception):
    if isinstance(e, GeminiError):
        raise HTTPException(GEMINI_HTTP.get(e.kind, 502), {"kind": e.kind, "message": str(e)})
    if isinstance(e, FetchError | ResearchError):
        raise HTTPException(422, {"kind": "invalid", "message": str(e)})
    if isinstance(e, LookupError):
        raise HTTPException(404, {"kind": "not_found", "message": str(e)})
    raise e


class LiveIn(BaseModel):
    question: str = Field(min_length=10, max_length=1000)
    sector: str | None = None
    state_ids: list[int] | None = Field(None, max_length=37)
    zone: str | None = None


class SourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    sector: str | None = None
    question: str | None = Field(None, max_length=500)


class ReviewIn(BaseModel):
    status: str
    note: str = Field(min_length=5, max_length=2000)


@router.get("/status")
def status(
    session: Session = Depends(get_session),
    _: User = Depends(current_user),
    factory=Depends(gemini_factory),
) -> dict:
    s = get_settings()
    with factory(session, None) as g:
        configured = g.configured()
        usage = g.usage_today()
    return {
        "configured": configured,
        "provider": "gemini",
        "search_model": s.gemini_search_model,
        "text_model": s.gemini_text_model,
        "search_model_allowed": s.gemini_search_model in FREE_SEARCH_MODELS,
        "text_model_allowed": s.gemini_text_model in FREE_TEXT_MODELS,
        "usage": usage,
        "notice": FREE_TIER_NOTICE,
        "message": None
        if configured
        else "No Gemini API key is configured (CONNECTLY_GEMINI_API_KEY), so web research and "
        "source analysis are unavailable. Findings already recorded, and the rest of the "
        "platform, work without it.",
    }


@router.get("/zones")
def zones(session: Session = Depends(get_session), _: User = Depends(current_user)) -> list:
    return service.zones(session)


@router.post("/live")
def live(
    body: LiveIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(*RESEARCHERS)),
    factory=Depends(gemini_factory),
) -> dict:
    try:
        with factory(session, user.id) as g:
            return service.live_research(
                session, user, body.question, body.sector, body.state_ids, body.zone, client=g
            )
    except (GeminiError, ResearchError, LookupError) as e:
        _fail(e)


@router.post("/sources")
def analyse(
    body: SourceIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(*RESEARCHERS)),
    factory=Depends(gemini_factory),
    fetcher=Depends(source_fetcher),
) -> dict:
    try:
        with factory(session, user.id) as g:
            return service.analyse_source(
                session, user, body.url, body.sector, body.question, client=g, fetcher=fetcher
            )
    except (GeminiError, ResearchError, FetchError, LookupError) as e:
        session.rollback()
        _fail(e)


@router.get("/findings")
def findings(
    area_id: int | None = None,
    sector: str | None = None,
    status: str | None = Query(None, pattern="^(unverified|source_verified|disputed|retired)$"),
    include_retired: bool = False,
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_session),
    _: User = Depends(current_user),
) -> list:
    try:
        return service.list_findings(session, area_id, sector, status, include_retired, limit)
    except ResearchError as e:
        _fail(e)


@router.post("/findings/{finding_id}/review")
def review(
    finding_id: int,
    body: ReviewIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(*RESEARCHERS)),
) -> dict:
    try:
        return service.review_finding(session, user, finding_id, body.status, body.note)
    except (ResearchError, LookupError) as e:
        _fail(e)


@router.get("/usage")
def usage(
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
    _: User = Depends(require_roles("admin")),
    factory=Depends(gemini_factory),
) -> dict:
    """Requests, tokens and errors per day, for the admin page. Nothing about content is kept."""
    since = datetime.now(tz=UTC).date().toordinal() - days
    rows = session.execute(
        select(
            AIUsage.pacific_day,
            AIUsage.purpose,
            AIUsage.status,
            func.count().label("requests"),
            func.coalesce(func.sum(AIUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(AIUsage.search_queries), 0).label("search_queries"),
        )
        .where(AIUsage.provider == "gemini")
        .group_by(AIUsage.pacific_day, AIUsage.purpose, AIUsage.status)
        .order_by(AIUsage.pacific_day.desc(), AIUsage.purpose, AIUsage.status)
    ).all()
    recent_errors = session.execute(
        select(AIUsage.at, AIUsage.purpose, AIUsage.status, AIUsage.http_status, AIUsage.error)
        .where(AIUsage.provider == "gemini", AIUsage.error.is_not(None))
        .order_by(AIUsage.at.desc())
        .limit(20)
    ).all()
    with factory(session, None) as g:
        today = g.usage_today()
    return {
        "today": today,
        "days": [
            {
                "day": r.pacific_day.isoformat(),
                "purpose": r.purpose,
                "status": r.status,
                "requests": r.requests,
                "tokens": int(r.tokens),
                "search_queries": int(r.search_queries),
            }
            for r in rows
            if r.pacific_day.toordinal() >= since
        ],
        "recent_errors": [
            {
                "at": e.at.isoformat(),
                "purpose": e.purpose,
                "status": e.status,
                "http_status": e.http_status,
                "error": e.error,
            }
            for e in recent_errors
        ],
    }
