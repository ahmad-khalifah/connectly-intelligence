"""Research intelligence with Gemini. Google is never called: every request goes to an
httpx.MockTransport that answers in the documented generateContent response format."""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select, text

from connectly.ai.gemini import GeminiClient, GeminiError, next_pacific_midnight
from connectly.ai.providers import GeminiProvider, ProviderError, get_provider
from connectly.api.routers import research as R
from connectly.core.config import Settings
from connectly.models import AICache, AIUsage, ResearchFinding, ResearchSource
from connectly.research import service
from connectly.research.fetch import FetchedDoc, FetchError, check_url, fetch
from tests.conftest import auth_header, make_user
from tests.test_matching import m  # noqa: F401

KEY = "AIzaTEST-not-a-real-key-123456"

DOC = (
    "Digital health in West North LGA, 2025 survey report.\n\n"
    "In West North LGA, only 12 of 40 primary health care centres had a working mobile "
    "connection in 2025, according to the state primary health care board.\n\n"
    "Community health workers said that patients travel up to 15 km to reach a clinic with "
    "a telemedicine service. The board estimates that 30% of households own a smartphone.\n\n"
    "This report was prepared for planning purposes and does not identify any person."
)


def doc(url="https://example.org/report", text_=DOC) -> FetchedDoc:
    import hashlib

    return FetchedDoc(
        url=url,
        final_url=url,
        content_type="text/html",
        title="Digital health survey",
        publisher="Example Health Board",
        published_on=datetime(2025, 6, 1).date(),
        published_basis="page metadata (article:published_time)",
        text=text_,
        sha256=hashlib.sha256(text_.encode()).hexdigest(),
        retrieved_at=datetime.now(tz=UTC),
    )


GOOD = {
    "statement": "Only 12 of 40 primary health care centres in West North had a working mobile connection in 2025.",
    "quote": "In West North LGA, only 12 of 40 primary health care centres had a working mobile connection in 2025",
    "kind": "measured",
    "sector": "health",
    "places": ["West North"],
    "period": "2025",
}
FABRICATED = GOOD | {
    "statement": "Most clinics have no electricity.",
    "quote": "Most clinics in West North have no electricity at all",
}
EXTRA_NUMBER = GOOD | {
    "statement": "30% of households, about 8,000, own a smartphone.",
    "quote": "The board estimates that 30% of households own a smartphone",
    "kind": "estimated",
}
NOWHERE = GOOD | {
    "quote": "Community health workers said that patients travel up to 15 km to reach a clinic",
    "statement": "Patients travel up to 15 km to reach a clinic.",
    "places": ["Atlantis"],
}


def reply(payload: dict | str, grounding: dict | None = None, tokens=30) -> dict:
    cand: dict = {
        "content": {
            "role": "model",
            "parts": [{"text": payload if isinstance(payload, str) else json.dumps(payload)}],
        }
    }
    if grounding:
        cand["groundingMetadata"] = grounding
    return {
        "candidates": [cand],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": tokens - 10,
            "totalTokenCount": tokens,
        },
    }


ANSWER = "Clinics in Testland’s north have weak connectivity [1]. Inference: telemedicine reach is limited."
GROUNDING = {
    "webSearchQueries": ["digital health access northern Testland"],
    "searchEntryPoint": {"renderedContent": "<div class='chips'>digital health</div>"},
    "groundingChunks": [
        {
            "web": {
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                "title": "example.org",
            }
        }
    ],
    "groundingSupports": [
        {
            "segment": {
                "startIndex": 0,
                "endIndex": len(ANSWER.split(" [1]")[0].encode()),
                "text": ANSWER.split(" [1]")[0],
            },
            "groundingChunkIndices": [0],
        }
    ],
}


class FakeGoogle:
    """Records requests and plays back responses."""

    def __init__(self, *responses: httpx.Response | dict):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return r if isinstance(r, httpx.Response) else httpx.Response(200, json=r)


def settings(**kw) -> Settings:
    return Settings(gemini_api_key=KEY, **kw)


@pytest.fixture
def api(m, session):  # noqa: F811
    """The app with Gemini pointed at a fake Google, and a fake page fetcher."""
    state = {"google": FakeGoogle(reply(ANSWER, GROUNDING)), "settings": settings(), "doc": doc()}
    app = m["c"].app
    app.dependency_overrides[R.gemini_factory] = lambda: (
        lambda s, uid: GeminiClient(
            s,
            settings=state["settings"],
            transport=httpx.MockTransport(state["google"]),
            user_id=uid,
        )  # fmt: skip
    )
    app.dependency_overrides[R.source_fetcher] = lambda: lambda url: state["doc"]
    researcher = auth_header(make_user(session, "researcher"))
    admin = auth_header(make_user(session, "admin"))
    yield m | {"state": state, "r": researcher, "admin": admin}
    app.dependency_overrides.clear()


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# ---------------------------------------------------------------------- live research


def test_live_research_is_shown_not_stored(api, session):
    c, state = api["c"], api["state"]
    r = c.post(
        "/api/v1/research/live",
        headers=api["r"],
        json={"question": "Which communities lack digital healthcare?", "sector": "health"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stored"] is False and d["value_type"] == "ai_generated"
    assert d["verification_status"] == "unverified"
    assert d["search_entry_point_html"] == "<div class='chips'>digital health</div>"
    assert d["sources"][0]["title"] == "example.org"
    # Byte offsets from Google become character offsets (the answer contains a ’).
    sup = d["supports"][0]
    assert d["text"][sup["start"] : sup["end"]] == ANSWER.split(" [1]")[0]
    assert KEY not in r.text

    sent = state["google"].requests[0]
    assert sent.url.path.endswith("/models/gemini-2.5-flash:generateContent")
    assert sent.headers["x-goog-api-key"] == KEY and "key=" not in str(sent.url)
    body = json.loads(sent.content)
    assert body["tools"] == [{"google_search": {}}]
    assert "Nigeria (all 36 states and the FCT)" in body["contents"][0]["parts"][0]["text"]

    # Nothing from the grounded answer was kept: no cache, sources or findings. Only counts.
    session.expire_all()
    assert count(session, AICache) == count(session, ResearchSource) == 0
    assert count(session, ResearchFinding) == 0
    u = session.scalars(select(AIUsage)).one()
    assert (u.status, u.grounded, u.purpose, u.total_tokens, u.search_queries) == (
        "ok", True, "web_research", 30, 1,
    )  # fmt: skip
    stored = json.dumps(
        [list(r) for r in session.execute(text("SELECT * FROM ai_usage")).all()], default=str
    )
    assert "vertexaisearch" not in stored and "weak connectivity" not in stored


def test_research_roles_and_disabled_state(api, session):
    c = api["c"]
    q = {"question": "Which communities lack digital healthcare?"}
    assert c.post("/api/v1/research/live", headers=api["h"], json=q).status_code == 403
    api["state"]["settings"] = Settings(gemini_api_key=None)
    st = c.get("/api/v1/research/status", headers=api["h"]).json()
    assert st["configured"] is False and "CONNECTLY_GEMINI_API_KEY" in st["message"]
    r = c.post("/api/v1/research/live", headers=api["r"], json=q)
    assert r.status_code == 503 and r.json()["detail"]["kind"] == "disabled"
    assert api["state"]["google"].requests == []
    assert c.get("/api/v1/research/usage", headers=api["r"]).status_code == 403
    assert c.get("/api/v1/research/usage", headers=api["admin"]).status_code == 200


def test_only_free_tier_models_are_called(session):
    google = FakeGoogle(reply(ANSWER, GROUNDING))
    for grounded, s in (
        (True, settings(gemini_search_model="gemini-2.5-pro")),
        (True, settings(gemini_search_model="gemini-3.5-flash")),  # free, but not with Search
        (False, settings(gemini_text_model="gemini-3-pro")),
    ):
        with GeminiClient(session, settings=s, transport=httpx.MockTransport(google)) as g:
            with pytest.raises(GeminiError) as e:
                g.grounded_answer("q", "s") if grounded else g.text_answer("q", "s")
        assert e.value.kind == "not_free"
    assert google.requests == [] and count(session, AIUsage) == 0


def test_local_limits_stop_calls_before_google(session):
    google = FakeGoogle(reply(ANSWER, GROUNDING))
    s = settings(gemini_daily_search_limit=1)
    with GeminiClient(session, settings=s, transport=httpx.MockTransport(google)) as g:
        g.grounded_answer("q", "s")
        with pytest.raises(GeminiError) as e:
            g.grounded_answer("q", "s")
        assert e.value.kind == "quota" and "midnight Pacific" in str(e.value)
        g.text_answer("q", "s")  # the text budget is separate
    with (
        GeminiClient(
            session,
            settings=settings(gemini_per_minute_limit=2),
            transport=httpx.MockTransport(google),
        ) as g,
        pytest.raises(GeminiError),
    ):
        g.text_answer("q", "s")  # two calls in the last minute already
    assert len(google.requests) == 2
    statuses = sorted(session.scalars(select(AIUsage.status)).all())
    assert statuses == ["blocked_local", "blocked_local", "ok", "ok"]


def test_google_rate_limit_blocks_until_reset(session):
    quota = httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": f"Quota exceeded for key {KEY}",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}
                        ],
                    }
                ],
            }
        },
    )
    google = FakeGoogle(quota)
    with GeminiClient(session, settings=settings(), transport=httpx.MockTransport(google)) as g:
        with pytest.raises(GeminiError) as e:
            g.grounded_answer("q", "s")
        assert e.value.kind == "rate_limited" and "Nothing was charged" in str(e.value)
        with pytest.raises(GeminiError) as e2:
            g.text_answer("q", "s")  # blocked locally: Google is not asked again
        assert e2.value.kind == "quota"
        assert g.usage_today()["blocked_until"] == next_pacific_midnight().isoformat()
    assert len(google.requests) == 1
    row = session.scalars(select(AIUsage).where(AIUsage.status == "rate_limited")).one()
    assert KEY not in row.error and "[key]" in row.error


def test_minute_rate_limit_uses_retry_delay(session):
    google = FakeGoogle(
        httpx.Response(
            429,
            json={"error": {"details": [{"retryDelay": "42s"}], "status": "RESOURCE_EXHAUSTED"}},
        )
    )
    with GeminiClient(session, settings=settings(), transport=httpx.MockTransport(google)) as g:
        with pytest.raises(GeminiError):
            g.text_answer("q", "s")
        until = datetime.fromisoformat(g.usage_today()["blocked_until"])
    assert 30 < (until - datetime.now(tz=UTC)).total_seconds() <= 42


# ---------------------------------------------------------------------- source analysis


def test_source_analysis_keeps_only_checked_findings(api, session):
    c, state = api["c"], api["state"]
    state["google"] = FakeGoogle(
        reply({"publication_date": "", "findings": [GOOD, FABRICATED, EXTRA_NUMBER, NOWHERE]})
    )
    r = c.post(
        "/api/v1/research/sources",
        headers=api["r"],
        json={"url": "https://example.org/report", "sector": "health"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert [f["statement"] for f in d["findings"]] == [GOOD["statement"]]
    f = d["findings"][0]
    assert (
        f["verification_status"] == "unverified" and f["extracted_by"] == "gemini:gemini-2.5-flash"
    )
    assert [a["name"] for a in f["areas"]] == ["West North"]
    assert f["source"]["published_on"] == "2025-06-01" and f["source"]["retrieved_at"]
    reasons = {x["statement"]: x["reason"] for x in d["rejected"]}
    assert "word for word" in reasons[FABRICATED["statement"]]
    assert "8000" in reasons[EXTRA_NUMBER["statement"]]
    assert "matches a loaded area" in reasons[NOWHERE["statement"]]
    body = json.loads(state["google"].requests[0].content)
    assert "tools" not in body  # extraction never uses Search
    assert body["generationConfig"]["responseMimeType"] == "application/json"

    # The same document again comes from the cache: Google is not called.
    r2 = c.post(
        "/api/v1/research/sources",
        headers=api["r"],
        json={"url": "https://example.org/report", "sector": "health"},
    )
    assert r2.json()["from_cache"] is True and r2.json()["findings"] == []
    assert "already recorded" in r2.json()["rejected"][0]["reason"]
    assert len(state["google"].requests) == 1
    session.expire_all()
    assert sorted(session.scalars(select(AIUsage.status)).all()) == ["cached", "ok"]
    assert count(session, ResearchSource) == 1


def test_source_analysis_refuses_google_redirect_links(api):
    api["c"].app.dependency_overrides[R.source_fetcher] = lambda: fetch
    r = api["c"].post(
        "/api/v1/research/sources",
        headers=api["r"],
        json={"url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"},
    )
    assert r.status_code == 422 and "redirect link" in r.json()["detail"]["message"]


def test_zone_names_resolve_to_their_states(api, session, monkeypatch):
    monkeypatch.setattr(
        service,
        "_zones_raw",
        lambda: {
            "zones": {"north_test": {"name": "North Test", "states": ["West", "Nowhere"]}},
            "groups": {"all_test": {"name": "All Test", "zones": ["north_test"]}},
        },
    )
    zone = service.zones(session)[0]
    assert zone["state_ids"] == [api["ids"]["West"]] and zone["missing_states"] == ["Nowhere"]
    ids, unmatched = service._resolve_places(session, ["North-Test geopolitical zone", "Mars"])
    assert ids == [api["ids"]["West"]] and unmatched == ["Mars"]
    scope = service._scope(session, None, "north_test")
    assert scope["missing_states"] == ["Nowhere"] and "West" in scope["states"]


def test_review_and_briefs_use_findings(api, session):
    from connectly.ai.brief import build_brief

    c, state = api["c"], api["state"]
    state["google"] = FakeGoogle(reply({"findings": [GOOD]}))
    fid = c.post(
        "/api/v1/research/sources", headers=api["r"], json={"url": "https://example.org/report"}
    ).json()["findings"][0]["id"]

    b = build_brief(session, api["ids"]["West North"], "health")
    research = next(s for s in b["sections"] if s["key"] == "research")["statements"]
    assert research[0]["text"].startswith("Unverified: Only 12 of 40")
    ev = next(e for e in b["evidence"] if e["id"] == research[0]["cites"][0])
    assert ev["kind"] == "research" and GOOD["quote"] in ev["text"]
    assert "https://example.org/report" in ev["source"] and "Published 2025-06-01" in ev["source"]
    assert (ev["value_type"], ev["verification"]) == ("measured", "unverified")
    assert any(s["kind"] == "gap" for s in research)

    # Findings about an LGA show for its state too, and not for other areas.
    west = c.get(f"/api/v1/research/findings?area_id={api['ids']['West']}", headers=api["h"])
    assert [f["id"] for f in west.json()] == [fid]
    east = c.get(f"/api/v1/research/findings?area_id={api['ids']['East']}", headers=api["h"])
    assert east.json() == []

    url = f"/api/v1/research/findings/{fid}/review"
    assert (
        c.post(
            url, headers=api["h"], json={"status": "source_verified", "note": "checked"}
        ).status_code
        == 403
    )
    assert (
        c.post(
            url, headers=api["r"], json={"status": "field_verified", "note": "checked page"}
        ).status_code
        == 422
    )
    ok = c.post(
        url,
        headers=api["r"],
        json={"status": "source_verified", "note": "Matched page 3 of the report"},
    )
    assert ok.status_code == 200 and ok.json()["verification_status"] == "source_verified"
    audit = (
        session.execute(text("SELECT action FROM audit_log WHERE entity_type = 'research_finding'"))
        .scalars()
        .all()
    )
    assert audit == ["review"]
    session.expire_all()
    b = build_brief(session, api["ids"]["West North"], "health")
    research = next(s for s in b["sections"] if s["key"] == "research")["statements"]
    assert research[0]["text"].startswith("Only 12 of 40")

    c.post(url, headers=api["r"], json={"status": "retired", "note": "Superseded by 2026 report"})
    session.expire_all()
    b = build_brief(session, api["ids"]["West North"], "health")
    research = next(s for s in b["sections"] if s["key"] == "research")["statements"]
    assert research[0]["kind"] == "gap" and len(research) == 1


# ---------------------------------------------------------------------- fetching


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.org/x",
        "http://localhost:8000/api",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "https://user:pw@example.org/",
        "https://db.internal/",
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
    ],
)
def test_unsafe_urls_refused(url):
    with pytest.raises(FetchError):
        check_url(url, resolve=False)


def test_fetch_reads_page_metadata_and_rechecks_redirects():
    page = (
        "<html><head><title>Fallback</title>"
        '<meta property="og:title" content="Clinic connectivity 2025">'
        '<meta property="og:site_name" content="Example Health Board">'
        '<meta property="article:published_time" content="2025-06-01T09:00:00Z">'
        "<script>var x = 'not text';</script></head><body><p>"
        + DOC.replace("\n\n", "</p><p>")
        + "</p></body></html>"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/old":
            return httpx.Response(301, headers={"location": "/report"})
        if req.url.path == "/evil":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})

    t = httpx.MockTransport(handler)
    d = fetch("https://example.org/old", transport=t, resolve=False)
    assert d.final_url == "https://example.org/report"
    assert (d.title, d.publisher, d.published_on.isoformat()) == (
        "Clinic connectivity 2025", "Example Health Board", "2025-06-01",
    )  # fmt: skip
    assert "not text" not in d.text and "12 of 40" in d.text
    with pytest.raises(FetchError, match="private"):
        fetch("https://example.org/evil", transport=t, resolve=False)


# ---------------------------------------------------------------------- separation


def test_engines_do_not_depend_on_gemini():
    """Needs, matching, market entry, profiles and ingestion work without any AI module."""
    root = Path(__file__).resolve().parents[1] / "connectly"
    for folder in ("services", "ingest"):
        for path in (root / folder).glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith(("connectly.ai", "connectly.research")), path
                if isinstance(node, ast.Import):
                    assert not any(
                        a.name.startswith(("connectly.ai", "connectly.research"))
                        for a in node.names
                    ), path


def test_gemini_provider_selection():
    with pytest.raises(ProviderError, match="CONNECTLY_GEMINI_API_KEY"):
        get_provider(Settings(ai_provider="gemini", gemini_api_key=None))
    with pytest.raises(ProviderError, match="free-tier"):
        get_provider(settings(ai_provider="gemini", gemini_text_model="gemini-2.5-pro"))
    p = get_provider(settings(ai_provider="gemini"))
    assert isinstance(p, GeminiProvider) and p.model == "gemini-2.5-flash"
