"""Google Gemini API client (Google AI Studio), restricted to the free tier.

Safeguards, all enforced before any request leaves the platform:

* Only models known to be free are accepted (FREE_*_MODELS, checked against Google's
  pricing page on 11 November 2026). Anything else is refused, not attempted.
* Connectly's own daily and per-minute limits, set below Google's free limits, are checked
  in the database first. When they are reached, the call is refused locally.
* A 429 from Google blocks further calls until the quota resets (daily quotas reset at
  midnight Pacific time) or for the delay Google gives; nothing is retried automatically.
* Every attempt is recorded in `ai_usage` (status, HTTP status, tokens, search queries,
  latency), never with the prompt, the answer or the key.

No charge can arise from the free tier itself: Google bills only projects with a billing
account linked. Keep the key's project without billing (docs/research.md).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from connectly.core.config import Settings, get_settings
from connectly.models import AIUsage

PROVIDER = "gemini"
PACIFIC = ZoneInfo("America/Los_Angeles")

# Free-tier models (Google pricing page, checked 11 Nov 2026). Only Gemini 2.5 Flash and
# Flash-Lite include Google Search grounding on the free tier (500 requests/day, shared).
FREE_SEARCH_MODELS = frozenset({"gemini-2.5-flash", "gemini-2.5-flash-lite"})
FREE_TEXT_MODELS = FREE_SEARCH_MODELS | frozenset({"gemini-3.5-flash", "gemini-3.1-flash-lite"})


class GeminiError(RuntimeError):
    """A call that could not be made or did not succeed. The message is safe to show."""

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind  # disabled | not_free | quota | rate_limited | error


@dataclass
class GroundedAnswer:
    text: str
    sources: list[dict]  # [{index, title, uri}]
    supports: list[dict]  # [{start, end, text, sources: [index...]}]
    queries: list[str]
    search_entry_point_html: str | None
    model: str
    usage: dict = field(default_factory=dict)


def pacific_day(now: datetime | None = None) -> date:
    return (now or datetime.now(tz=UTC)).astimezone(PACIFIC).date()


def next_pacific_midnight(now: datetime | None = None) -> datetime:
    local = (now or datetime.now(tz=UTC)).astimezone(PACIFIC)
    nxt = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), PACIFIC)
    return nxt.astimezone(UTC)


def _scrub(message: str, key: str | None) -> str:
    if key:
        message = message.replace(key, "[key]")
    return re.sub(r"(key=)[A-Za-z0-9_\-]+", r"\1[key]", message)[:1000]


class GeminiClient:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
        user_id: int | None = None,
    ):
        # Usage is recorded on a separate connection, so committing it never commits (or
        # rolls back) the caller's own unfinished work.
        self.session = Session(session.get_bind(), expire_on_commit=False)
        self.s = settings or get_settings()
        self.transport = transport
        self.user_id = user_id

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> GeminiClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ configuration

    @property
    def key(self) -> str | None:
        return self.s.gemini_api_key.get_secret_value() if self.s.gemini_api_key else None

    def configured(self) -> bool:
        return bool(self.key)

    def check_model(self, model: str, grounded: bool) -> None:
        allowed = FREE_SEARCH_MODELS if grounded else FREE_TEXT_MODELS
        if model not in allowed:
            raise GeminiError(
                f"Model {model!r} is not on Connectly's free-tier list for "
                f"{'Google Search research' if grounded else 'text tasks'} "
                f"({', '.join(sorted(allowed))}). It was not called.",
                "not_free",
            )

    # ------------------------------------------------------------------ budget

    def usage_today(self) -> dict[str, Any]:
        day = pacific_day()
        reached = AIUsage.status.in_(("ok", "rate_limited", "error", "pending"))
        q = select(func.count()).where(
            AIUsage.provider == PROVIDER, AIUsage.pacific_day == day, reached
        )
        searches = self.session.scalar(q.where(AIUsage.grounded.is_(True))) or 0
        requests = self.session.scalar(q.where(AIUsage.grounded.is_(False))) or 0
        minute = (
            self.session.scalar(
                select(func.count()).where(
                    AIUsage.provider == PROVIDER,
                    reached,
                    AIUsage.at > datetime.now(tz=UTC) - timedelta(seconds=60),
                )
            )
            or 0
        )
        blocked = self.session.scalar(
            select(func.max(AIUsage.blocked_until)).where(AIUsage.provider == PROVIDER)
        )
        tokens = self.session.scalar(
            select(func.coalesce(func.sum(AIUsage.total_tokens), 0)).where(
                AIUsage.provider == PROVIDER, AIUsage.pacific_day == day
            )
        )
        now = datetime.now(tz=UTC)
        return {
            "pacific_day": day.isoformat(),
            "resets_at": next_pacific_midnight().isoformat(),
            "searches": searches,
            "search_limit": self.s.gemini_daily_search_limit,
            "requests": requests,
            "request_limit": self.s.gemini_daily_request_limit,
            "last_minute": minute,
            "per_minute_limit": self.s.gemini_per_minute_limit,
            "tokens": int(tokens or 0),
            "blocked_until": blocked.isoformat() if blocked and blocked > now else None,
        }

    def _reserve(self, model: str, purpose: str, grounded: bool) -> AIUsage:
        """Check local limits and record a pending attempt, serialised across workers."""
        self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('gemini-budget'))"))
        u = self.usage_today()
        reason = None
        if u["blocked_until"]:
            reason = (
                "Google's free-tier limit was reached; no further requests until "
                f"{u['blocked_until']} (UTC)."
            )
        elif grounded and u["searches"] >= u["search_limit"]:
            reason = f"Today's web research limit ({u['search_limit']}) is used up."
        elif not grounded and u["requests"] >= u["request_limit"]:
            reason = f"Today's AI request limit ({u['request_limit']}) is used up."
        elif u["last_minute"] >= u["per_minute_limit"]:
            reason = "Too many AI requests in the last minute. Try again shortly."
        row = AIUsage(
            pacific_day=pacific_day(),
            provider=PROVIDER,
            model=model,
            purpose=purpose,
            grounded=grounded,
            status="blocked_local" if reason else "pending",
            user_id=self.user_id,
            error=reason,
        )
        self.session.add(row)
        self.session.commit()  # releases the lock; the attempt now counts
        if reason:
            raise GeminiError(
                reason + f" Limits reset at midnight Pacific time ({u['resets_at']} UTC).",
                "quota",
            )
        return row

    # ------------------------------------------------------------------ transport

    def _post(self, model: str, body: dict, purpose: str, grounded: bool) -> dict:
        if not self.configured():
            raise GeminiError(
                "Gemini is not configured (CONNECTLY_GEMINI_API_KEY is not set).", "disabled"
            )
        self.check_model(model, grounded)
        row = self._reserve(model, purpose, grounded)
        started = time.monotonic()
        try:
            with httpx.Client(transport=self.transport, timeout=self.s.gemini_timeout) as c:
                r = c.post(
                    f"{self.s.gemini_base_url.rstrip('/')}/models/{model}:generateContent",
                    headers={"x-goog-api-key": self.key or "", "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.HTTPError as e:
            self._finish(row, "error", None, started, error=_scrub(str(e), self.key))
            raise GeminiError("The Gemini API could not be reached.", "error") from None
        if r.status_code == 429:
            blocked = self._blocked_until(r)
            self._finish(row, "rate_limited", 429, started, error=_scrub(r.text, self.key),
                         blocked_until=blocked)  # fmt: skip
            raise GeminiError(
                "Google's free-tier limit for Gemini was reached. Nothing was charged. "
                f"Requests resume after {blocked.isoformat()} (UTC).",
                "rate_limited",
            )
        if r.status_code != 200:
            detail = _scrub(r.text, self.key)
            self._finish(row, "error", r.status_code, started, error=detail)
            message = {
                400: "Gemini rejected the request.",
                403: "Gemini refused the key (check it, and that this region is supported).",
                404: f"The model {model} is not available to this key.",
            }.get(r.status_code, f"Gemini returned an error (HTTP {r.status_code}).")
            raise GeminiError(message, "error")
        data = r.json()
        meta = data.get("usageMetadata") or {}
        queries = ((data.get("candidates") or [{}])[0].get("groundingMetadata") or {}).get(
            "webSearchQueries"
        ) or []
        self._finish(
            row,
            "ok",
            200,
            started,
            prompt_tokens=meta.get("promptTokenCount"),
            output_tokens=meta.get("candidatesTokenCount"),
            total_tokens=meta.get("totalTokenCount"),
            search_queries=len(queries) if grounded else None,
        )
        return data

    def record_cached(self, model: str, purpose: str) -> None:
        """Count a request answered from the cache (no call to Google)."""
        self.session.add(
            AIUsage(
                pacific_day=pacific_day(),
                provider=PROVIDER,
                model=model,
                purpose=purpose,
                grounded=False,
                status="cached",
                user_id=self.user_id,
            )  # fmt: skip
        )
        self.session.commit()

    def _blocked_until(self, r: httpx.Response) -> datetime:
        now = datetime.now(tz=UTC)
        body = r.text
        if "PerDay" in body or "per day" in body.lower():
            return next_pacific_midnight(now)
        m = re.search(r'"retryDelay"\s*:\s*"(\d+)(?:\.\d+)?s"', body)
        seconds = int(m.group(1)) if m else int(r.headers.get("retry-after", "60") or 60)
        return now + timedelta(seconds=max(seconds, 10))

    def _finish(self, row: AIUsage, status: str, http_status: int | None, started: float,
                **fields) -> None:  # fmt: skip
        row.status = status
        row.http_status = http_status
        row.latency_ms = int((time.monotonic() - started) * 1000)
        for k, v in fields.items():
            setattr(row, k, v)
        self.session.commit()

    # ------------------------------------------------------------------ calls

    def grounded_answer(self, prompt: str, system: str) -> GroundedAnswer:
        """Answer with Google Search grounding. The result must not be stored or cached."""
        model = self.s.gemini_search_model
        data = self._post(
            model,
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],
                "generationConfig": {"temperature": 0.2},
            },
            "web_research",
            grounded=True,
        )
        cand = (data.get("candidates") or [{}])[0]
        text_ = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
        gm = cand.get("groundingMetadata") or {}
        sources = [
            {"index": i, "title": (c.get("web") or {}).get("title"), "uri": (c.get("web") or {}).get("uri")}
            for i, c in enumerate(gm.get("groundingChunks") or [])
        ]  # fmt: skip
        supports = [
            {
                "start": (s.get("segment") or {}).get("startIndex", 0),
                "end": (s.get("segment") or {}).get("endIndex", 0),
                "text": (s.get("segment") or {}).get("text", ""),
                "sources": s.get("groundingChunkIndices") or [],
            }
            for s in gm.get("groundingSupports") or []
        ]
        return GroundedAnswer(
            text=text_,
            sources=sources,
            supports=supports,
            queries=gm.get("webSearchQueries") or [],
            search_entry_point_html=(gm.get("searchEntryPoint") or {}).get("renderedContent"),
            model=model,
            usage=data.get("usageMetadata") or {},
        )

    def json_answer(self, prompt: str, system: str, schema: dict, purpose: str) -> dict:
        """Structured output without Search. The caller decides whether to cache it."""
        model = self.s.gemini_text_model
        data = self._post(
            model,
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                },
            },
            purpose,
            grounded=False,
        )
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        try:
            return json.loads("".join(p.get("text", "") for p in parts))
        except ValueError:
            raise GeminiError("Gemini returned output that is not valid JSON.", "error") from None

    def text_answer(self, prompt: str, system: str) -> str:
        model = self.s.gemini_text_model
        data = self._post(
            model,
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0},
            },
            "summary",
            grounded=False,
        )
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)
