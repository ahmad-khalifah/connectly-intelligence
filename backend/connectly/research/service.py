"""Research intelligence: live web research, source analysis and research findings.

Two paths, kept apart because Google's terms treat them differently:

1. Live web research: Gemini with Google Search grounding. The answer, its links and
   Google's Search Suggestions go only to the user who asked. They are never stored or
   cached (Google's terms for Grounding with Google Search forbid it). The answer is
   labelled AI-generated and unverified.
2. Source analysis: a researcher submits the original URL of a page they opened. Connectly
   fetches it, Gemini (without Search) proposes findings with verbatim quotes, and only
   findings whose quote appears word for word in the page are stored, as unverified, with
   the URL, publication date and retrieval date. A researcher then verifies or rejects them.

Neither path feeds the deterministic needs, matching or market entry engines.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Integer, select, text
from sqlalchemy.orm import Session

from connectly.ai.gemini import GeminiClient
from connectly.core.config import get_settings
from connectly.ingest.coverage import CoverageError, resolve_state_names
from connectly.models import (
    AICache,
    ResearchFinding,
    ResearchFindingArea,
    ResearchSource,
    Sector,
    User,
)
from connectly.research.fetch import FetchedDoc, fetch
from connectly.services import audit
from connectly.services.personal_data import personal_data_found

PROMPT_VERSION = "2026-11-11"
MAX_DOC_CHARS = 60_000  # keeps one extraction well inside free-tier token limits
REVIEW_STATUSES = ("unverified", "source_verified", "disputed", "retired")
ZONES_FILE = Path(__file__).resolve().parents[1] / "taxonomy" / "zones.yaml"


class ResearchError(ValueError):
    pass


# ---------------------------------------------------------------------- scope


@lru_cache
def _zones_raw() -> dict:
    return yaml.safe_load(ZONES_FILE.read_text(encoding="utf-8"))


def _state_ids(session: Session, names: list[str]) -> tuple[list[int], list[str]]:
    ids, missing = [], []
    for n in names:
        try:
            ids += resolve_state_names(session, [n])
        except CoverageError:
            missing.append(n)
    return sorted(set(ids)), missing


def zones(session: Session) -> list[dict]:
    """Geopolitical zones and the northern/southern groups, with the loaded states in each.
    `missing_states` lists any zone member not loaded, so a scope is never silently partial."""
    raw = _zones_raw()
    out = []
    for code, z in raw["zones"].items():
        ids, missing = _state_ids(session, z["states"])
        out.append(
            {
                "code": code,
                "name": z["name"],
                "kind": "zone",
                "state_ids": ids,
                "missing_states": missing,
            }  # fmt: skip
        )
    by_code = {z["code"]: z for z in out}
    for code, g in raw["groups"].items():
        ids = sorted({i for zc in g["zones"] for i in by_code[zc]["state_ids"]})
        missing = [m for zc in g["zones"] for m in by_code[zc]["missing_states"]]
        out.append(
            {
                "code": code,
                "name": g["name"],
                "kind": "group",
                "state_ids": ids,
                "missing_states": missing,
            }  # fmt: skip
        )
    return out


def _zone_key(name: str) -> str:
    n = re.sub(r"[-_]", " ", name.lower())
    n = re.sub(r"\b(geopolitical|geo political|zone|region|of nigeria)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _scope(session: Session, state_ids: list[int] | None, zone: str | None) -> dict:
    names = dict(
        session.execute(
            text("SELECT id, name FROM admin_area WHERE level = 'state' AND active")
        ).all()
    )
    label = "Nigeria (all 36 states and the FCT)"
    ids: list[int] = []
    missing: list[str] = []
    if zone:
        z = next((z for z in zones(session) if z["code"] == zone), None)
        if z is None:
            raise ResearchError(f"unknown zone {zone!r}")
        ids, missing = z["state_ids"], z["missing_states"]
        label = z["name"] if z["kind"] == "group" else f"{z['name']} zone of Nigeria"
    if state_ids:
        unknown = [i for i in state_ids if i not in names]
        if unknown:
            raise ResearchError(f"unknown state ids {unknown}")
        ids = sorted(set(state_ids) | set(ids)) if zone else sorted(set(state_ids))
        if not zone:
            label = ", ".join(names[i] for i in ids)
    return {
        "label": label,
        "state_ids": ids,
        "states": [names[i] for i in ids] + missing,
        "missing_states": missing,
    }


def _sector(session: Session, code: str | None) -> Sector | None:
    if not code:
        return None
    sec = session.scalar(select(Sector).where(Sector.code == code))
    if sec is None:
        raise ResearchError(f"unknown sector {code!r}")
    return sec


def _guard(*texts: str | None) -> None:
    found = personal_data_found(*texts)
    if found:
        raise ResearchError(
            f"The text contains {', '.join(found)}. Research is about places, not people, and "
            "nothing personal may be sent to the AI service."
        )


# ---------------------------------------------------------------------- live research

LIVE_SYSTEM = """You research technology access in Nigerian communities for Connectly Intelligence.
Use Google Search and rely on what the sources say, not on memory.
Rules:
- Stay within Nigeria and the geographic scope given.
- Name a community, ward, LGA or state only when a source you found names it.
- For every figure, say what it measures, its year or period, and who published it.
- Write "Inference:" before anything you conclude yourself rather than read in a source.
- If the sources are few, old or indirect, say so plainly. Never invent a figure, a place or a source.
- Do not mention or describe individual people.
Structure: a short answer first, then the evidence by place, then "Limitations"."""


def _char_offsets(text_: str, supports: list[dict]) -> list[dict]:
    """Gemini reports segment positions in UTF-8 bytes; the browser needs characters."""
    raw = text_.encode("utf-8")

    def ch(i: int) -> int:
        return len(raw[: max(0, min(i, len(raw)))].decode("utf-8", errors="ignore"))

    return [s | {"start": ch(s["start"]), "end": ch(s["end"])} for s in supports]


def live_research(
    session: Session,
    user: User,
    question: str,
    sector: str | None = None,
    state_ids: list[int] | None = None,
    zone: str | None = None,
    client: GeminiClient | None = None,
) -> dict[str, Any]:
    question = (question or "").strip()
    if len(question) < 10:
        raise ResearchError("Ask a fuller question (at least 10 characters).")
    _guard(question)
    scope = _scope(session, state_ids, zone)
    sec = _sector(session, sector)
    prompt = (
        f"Research question: {question}\n"
        f"Geographic scope: {scope['label']}"
        + (f" (states: {', '.join(scope['states'])})" if scope["states"] else "")
        + (f"\nSector: {sec.name}" if sec else "")
    )
    g = client or GeminiClient(session, user_id=user.id)
    try:
        ans = g.grounded_answer(prompt, LIVE_SYSTEM)
    finally:
        if client is None:
            g.close()
    return {
        "question": question,
        "scope": scope,
        "sector": sec.code if sec else None,
        "model": ans.model,
        "text": ans.text,
        "supports": _char_offsets(ans.text, ans.supports),
        "sources": ans.sources,
        "queries": ans.queries,
        "search_entry_point_html": ans.search_entry_point_html,
        "value_type": "ai_generated",
        "verification_status": "unverified",
        "stored": False,
        "notice": (
            "AI-generated answer from Gemini using Google Search. It is unverified, shown only "
            "to you, and not stored: Google's terms do not allow saving these results or their "
            "links. To keep evidence, open a source and submit its address under "
            '"Analyse a source".'
        ),
        "limitations": [
            "Search results reflect what is online and indexed, which under-represents many "
            "rural communities.",
            "Figures are as reported by each source; check the year and method before use.",
            'Statements marked "Inference:" are the model\'s conclusions, not facts from a source.',
        ]
        + (
            []
            if ans.sources
            else ["The model returned no sources for this answer; treat it as unsupported."]
        ),
    }


# ---------------------------------------------------------------------- source analysis

EXTRACT_SYSTEM = """You extract research findings about technology access in Nigeria from one document.
Rules:
- Use only the document text. Do not add knowledge from elsewhere.
- Each finding is one statement in plain words plus "quote": an exact, word-for-word passage
  copied from the document (20 to 400 characters) that supports it. Do not alter the quote.
- Every number in the statement must appear in the quote.
- kind: "measured" (a reported measurement or count), "estimated" (an estimate or projection),
  "assumed" (an assumption or expectation), or "opinion" (a view or recommendation).
- places: the Nigerian places the finding is about, as named in the document (state, LGA,
  ward, town or community). Use "Nigeria" for national findings. Skip findings about other countries.
- period: the year or period the finding refers to, if stated.
- Never include information about identifiable individuals.
- Return at most 15 findings, the most relevant to the question or sector given."""


def _schema(sector_codes: list[str]) -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "publication_date": {
                "type": "STRING",
                "description": "YYYY-MM-DD if the document states its publication date, else empty",
            },
            "findings": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "statement": {"type": "STRING"},
                        "quote": {"type": "STRING"},
                        "kind": {
                            "type": "STRING",
                            "enum": ["measured", "estimated", "assumed", "opinion"],
                        },
                        "sector": {"type": "STRING", "enum": sector_codes},
                        "places": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "period": {"type": "STRING"},
                    },
                    "required": ["statement", "quote", "kind", "places"],
                },
            },
        },
        "required": ["findings"],
    }


_WS = re.compile(r"\s+")
_NUM = re.compile(r"(?<![A-Za-z\d])\d[\d,]*(?:\.\d+)?")


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return _WS.sub(" ", s).strip()


def _numbers(s: str) -> set[str]:
    out = set()
    for n in _NUM.findall(s):
        n = n.replace(",", "").rstrip(".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def _resolve_places(session: Session, places: list[str]) -> tuple[list[int], list[str]]:
    """Match place names to active areas; ambiguous names count only if a named state settles them."""
    candidates: dict[str, list[tuple[int, str, int | None]]] = {}
    zone_ids: set[int] = set()
    by_zone = {_zone_key(z["name"]): z for z in zones(session)}
    for name in places:
        n = name.strip()
        if not n:
            continue
        z = by_zone.get(_zone_key(n)) or by_zone.get(_zone_key(n).replace(" nigeria", ""))
        if z and z["state_ids"]:
            zone_ids.update(z["state_ids"])  # a zone is recorded as its states
            continue
        rows = session.execute(
            text(
                """
                SELECT a.id, a.level,
                  CASE a.level WHEN 'state' THEN a.id WHEN 'lga' THEN a.parent_id
                    WHEN 'ward' THEN (SELECT parent_id FROM admin_area WHERE id = a.parent_id) END
                FROM admin_area a
                WHERE a.active AND (lower(a.name) = lower(:n) OR EXISTS (
                  SELECT 1 FROM place_alias p WHERE p.admin_area_id = a.id AND lower(p.alias) = lower(:n)))
                """
            ),
            {"n": re.sub(r"\s+(state|lga|local government area)$", "", n, flags=re.I)},
        ).all()
        candidates[n] = [(r[0], r[1], r[2]) for r in rows]
    states = {
        r[0] for rows in candidates.values() if len(rows) == 1 for r in rows if r[1] == "state"
    }
    ids, unmatched = set(zone_ids), []
    for name, rows in candidates.items():
        if len(rows) == 1:
            ids.add(rows[0][0])
        elif rows and (pick := [r for r in rows if r[2] in states]) and len(pick) == 1:
            ids.add(pick[0][0])
        else:
            unmatched.append(name)
    return sorted(ids), unmatched


def _check_finding(f: dict, doc_norm: str, sector_codes: set[str]) -> str | None:
    quote = _norm(f.get("quote") or "")
    statement = (f.get("statement") or "").strip()
    if not statement or len(quote) < 20 or len(quote) > 600:
        return "statement or quote missing, or quote outside 20–600 characters"
    if quote not in doc_norm:
        return "quote does not appear word for word in the document"
    extra = _numbers(statement) - _numbers(quote)
    if extra:
        return f"statement has numbers not in the quote ({', '.join(sorted(extra))})"
    if f.get("sector") and f["sector"] not in sector_codes:
        return "unknown sector"
    if personal_data_found(statement, quote):
        return "contains personal contact details"
    return None


def analyse_source(
    session: Session,
    user: User,
    url: str,
    sector: str | None = None,
    question: str | None = None,
    client: GeminiClient | None = None,
    fetcher=fetch,
) -> dict[str, Any]:
    _guard(question)
    sec = _sector(session, sector)
    doc: FetchedDoc = fetcher(url)
    s = get_settings()
    g = client or GeminiClient(session, user_id=user.id)
    sector_codes = [x for (x,) in session.execute(select(Sector.code)).all()]
    truncated = len(doc.text) > MAX_DOC_CHARS
    body = doc.text[:MAX_DOC_CHARS]
    model = s.gemini_text_model
    key = hashlib.sha256(
        f"{model}|{PROMPT_VERSION}|{doc.sha256}|{sector or ''}|{question or ''}".encode()
    ).hexdigest()
    now = datetime.now(tz=UTC)
    cached = session.get(AICache, key)
    try:
        if cached is not None and cached.expires_at > now:
            reply, from_cache = cached.response, True
            cached.hits += 1
            g.record_cached(model, "source_extraction")
        else:
            prompt = (
                f"Document title: {doc.title or 'unknown'}\nPublisher: {doc.publisher or 'unknown'}\n"
                + (f"Sector of interest: {sec.name}\n" if sec else "")
                + (f"Question: {question}\n" if question else "")
                + f"\nDocument text:\n{body}"
            )
            reply = g.json_answer(
                prompt, EXTRACT_SYSTEM, _schema(sector_codes), "source_extraction"
            )
            from_cache = False
            if cached is not None:
                session.delete(cached)
                session.flush()
            session.add(
                AICache(
                    key=key,
                    purpose="source_extraction",
                    model=model,
                    response=reply,
                    expires_at=now + timedelta(days=s.gemini_cache_days),
                )  # fmt: skip
            )
    finally:
        if client is None:
            g.close()

    published, basis = doc.published_on, doc.published_basis
    if published is None and (d := (reply.get("publication_date") or "").strip()):
        try:
            published, basis = date.fromisoformat(d[:10]), "stated in the document (read by AI)"
        except ValueError:
            pass

    src = session.scalar(select(ResearchSource).where(ResearchSource.url == doc.url))
    if src is None:
        src = ResearchSource(url=doc.url, submitted_by_id=user.id)
        session.add(src)
    src.final_url = doc.final_url
    src.title = doc.title
    src.publisher = doc.publisher
    src.published_on = published
    src.published_basis = basis
    src.retrieved_at = doc.retrieved_at
    src.content_type = doc.content_type
    src.content_sha256 = doc.sha256
    src.char_count = len(doc.text)
    session.flush()

    existing = {
        _norm(q)
        for (q,) in session.execute(
            select(ResearchFinding.quote).where(ResearchFinding.source_id == src.id)
        ).all()
    }
    doc_norm = _norm(body)
    stored, rejected = [], []
    sector_ids = dict(session.execute(select(Sector.code, Sector.id)).all())
    for f in (reply.get("findings") or [])[:15]:
        problem = _check_finding(f, doc_norm, set(sector_codes))
        places = [p for p in (f.get("places") or []) if isinstance(p, str)]
        area_ids, unmatched = ([], places) if problem else _resolve_places(session, places)
        if not problem and not area_ids:
            problem = "no Nigerian place in the finding matches a loaded area"
        if not problem and _norm(f["quote"]) in existing:
            problem = "already recorded from this source"
        if problem:
            rejected.append({"statement": (f.get("statement") or "")[:300], "reason": problem})
            continue
        fnd = ResearchFinding(
            source_id=src.id,
            statement=f["statement"].strip(),
            quote=_norm(f["quote"]),
            kind=f["kind"],
            sector_id=sector_ids.get(f.get("sector") or sector or ""),
            period_text=(f.get("period") or "").strip()[:128] or None,
            places_text=places,
            extracted_by=f"gemini:{model}",
            verification_status="unverified",
            created_by_id=user.id,
        )
        session.add(fnd)
        session.flush()
        for aid in area_ids:
            session.add(ResearchFindingArea(finding_id=fnd.id, admin_area_id=aid))
        existing.add(fnd.quote)
        stored.append(fnd.id)
    audit.record(session, user, "analyse", "research_source", src.id,
                 f"{len(stored)} findings stored, {len(rejected)} rejected from {doc.url}")  # fmt: skip
    session.commit()
    return {
        "source": source_out(src),
        "findings": [finding_out(session, session.get(ResearchFinding, i)) for i in stored],
        "rejected": rejected,
        "truncated": truncated,
        "from_cache": from_cache,
        "model": model,
        "notice": (
            "Findings were extracted by AI (Gemini) and each quote was checked word for word "
            "against the document. They are unverified until a researcher reviews them."
        ),
    }


# ---------------------------------------------------------------------- findings


def source_out(src: ResearchSource) -> dict:
    return {
        "id": src.id,
        "url": src.url,
        "final_url": src.final_url,
        "title": src.title,
        "publisher": src.publisher,
        "published_on": src.published_on.isoformat() if src.published_on else None,
        "published_basis": src.published_basis,
        "retrieved_at": src.retrieved_at.isoformat(),
        "content_type": src.content_type,
    }


def finding_out(session: Session, f: ResearchFinding) -> dict:
    areas = (
        session.execute(
            text(
                """
            SELECT a.id, a.name, a.level FROM research_finding_area x
            JOIN admin_area a ON a.id = x.admin_area_id WHERE x.finding_id = :f ORDER BY a.level, a.name
            """
            ),
            {"f": f.id},
        )
        .mappings()
        .all()
    )
    sector = session.get(Sector, f.sector_id) if f.sector_id else None
    return {
        "id": f.id,
        "statement": f.statement,
        "quote": f.quote,
        "kind": f.kind,
        "sector": sector.code if sector else None,
        "period": f.period_text,
        "places": f.places_text or [],
        "areas": [dict(a) for a in areas],
        "extracted_by": f.extracted_by,
        "verification_status": f.verification_status,
        "verification_note": f.verification_note,
        "verified_at": f.verified_at.isoformat() if f.verified_at else None,
        "source": source_out(f.source),
    }


AREA_FAMILY_SQL = """
    WITH RECURSIVE up AS (
      SELECT id, parent_id FROM admin_area WHERE id = :area
      UNION ALL SELECT a.id, a.parent_id FROM admin_area a JOIN up ON a.id = up.parent_id),
    down AS (
      SELECT id FROM admin_area WHERE id = :area
      UNION ALL SELECT a.id FROM admin_area a JOIN down ON a.parent_id = down.id)
    SELECT id FROM up UNION SELECT id FROM down
"""


def list_findings(
    session: Session,
    area_id: int | None = None,
    sector: str | None = None,
    status: str | None = None,
    include_retired: bool = False,
    limit: int = 200,
) -> list[dict]:
    """Findings about an area, its larger areas (context) and the areas inside it."""
    q = select(ResearchFinding).order_by(ResearchFinding.id.desc()).limit(limit)
    if area_id is not None:
        q = q.where(
            ResearchFinding.id.in_(
                select(ResearchFindingArea.finding_id).where(
                    ResearchFindingArea.admin_area_id.in_(
                        text(AREA_FAMILY_SQL).bindparams(area=area_id).columns(id=Integer)
                    )
                )
            )
        )
    if sector:
        sec = _sector(session, sector)
        q = q.where((ResearchFinding.sector_id == sec.id) | ResearchFinding.sector_id.is_(None))
    if status:
        q = q.where(ResearchFinding.verification_status == status)
    elif not include_retired:
        q = q.where(ResearchFinding.verification_status != "retired")
    return [finding_out(session, f) for f in session.scalars(q)]


def review_finding(session: Session, user: User, finding_id: int, status: str, note: str) -> dict:
    if status not in REVIEW_STATUSES:
        raise ResearchError(f"status must be one of {', '.join(REVIEW_STATUSES)}")
    note = (note or "").strip()
    if len(note) < 5:
        raise ResearchError("Say what was checked, and how (at least 5 characters).")
    _guard(note)
    f = session.get(ResearchFinding, finding_id)
    if f is None:
        raise LookupError(f"no finding {finding_id}")
    before = f.verification_status
    f.verification_status = status
    f.verification_note = note
    f.verified_by_id = user.id
    f.verified_at = datetime.now(tz=UTC)
    audit.record(session, user, "review", "research_finding", f.id, f"{before} → {status}: {note}")
    session.commit()
    return finding_out(session, f)
