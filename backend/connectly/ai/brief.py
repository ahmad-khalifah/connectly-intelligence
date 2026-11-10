"""Community intelligence briefs with retrieval from the platform's own data.

1. Retrieve: gather numbered evidence items (E1, E2...) for an area and sector from the
   database: profile values, facilities, gap scores, matched solutions, community claims,
   data gaps and, for a question, a full-text search over claims, gaps and the directory.
2. Brief: build the brief's ten sections deterministically from that evidence. Every
   statement cites evidence ids and is tagged fact, derived, recommendation or gap.
3. Narrative (optional): if a self-hosted model is configured, ask it to summarise the
   evidence. The reply is accepted only if every sentence cites existing evidence ids and every
   number it uses appears in the evidence it cites. Otherwise it is discarded and the reasons
   are returned. Accepted text is labelled AI-generated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.ai.providers import Provider, ProviderError, get_provider
from connectly.models.directory import BENEFICIARY_GROUPS
from connectly.services.matching import MatchingError, match
from connectly.services.needs import assess
from connectly.services.profiles import area_profile

SECTOR_FACILITY = {
    "health": "health",
    "education": "education",
    "finance": "financial",
    "connectivity": "telecom",
    "energy": "energy",
    "commerce": "market",
    "transport": "transport",
    "agriculture": "agriculture",
}
BARRIERS = {
    # indicator: (threshold, below_is_barrier, wording)
    "connectivity.households_mobile_phone_pct": (70, True, "household mobile phone ownership"),
    "energy.households_electricity_pct": (60, True, "household electricity access"),
    "education.women_literate_pct": (60, True, "women's literacy"),
    "connectivity.nearest_tower_km_ward_point": (10, False, "distance to the nearest mobile site"),
    "finance.financially_excluded_adults_pct": (30, False, "financial exclusion"),
}


class BriefError(ValueError):
    pass


@dataclass
class Evidence:
    items: list[dict] = field(default_factory=list)

    def add(
        self,
        kind: str,
        text_: str,
        source: str,
        value_type: str | None = None,
        verification: str | None = None,
    ) -> str:
        eid = f"E{len(self.items) + 1}"
        self.items.append(
            {
                "id": eid,
                "kind": kind,
                "text": text_,
                "source": source,
                "value_type": value_type,
                "verification": verification,
            }
        )
        return eid


def _stmt(kind: str, text_: str, cites: list[str]) -> dict:
    return {"kind": kind, "text": text_, "cites": cites}


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:g}"


def search(session: Session, question: str, area_ids: list[int], limit: int = 6) -> list[dict]:
    """Full-text search (PostgreSQL, English stemming, any word) over claims, data gaps and
    solutions, ranked by relevance."""
    sql = text(
        """
        WITH q AS (SELECT to_tsquery('english', replace(plainto_tsquery('english', :q)::text, ' & ', ' | ')) AS q)
        SELECT * FROM (
          SELECT 'claim' AS kind, c.attribute || ': ' || c.value_text AS body,
                 c.source_description AS source, c.value_type, c.verification_status,
                 ts_rank(to_tsvector('english', c.value_text), q.q) AS rank
          FROM claim c, q WHERE c.is_active AND c.subject_type = 'admin_area'
            AND c.subject_id = ANY(:ids) AND to_tsvector('english', c.value_text) @@ q.q
          UNION ALL
          SELECT 'data_gap', g.title || ': ' || g.description, 'Recorded data gap', NULL, NULL,
                 ts_rank(to_tsvector('english', g.title || ' ' || g.description), q.q)
          FROM data_gap g, q WHERE g.status <> 'resolved'
            AND to_tsvector('english', g.title || ' ' || g.description) @@ q.q
          UNION ALL
          SELECT 'solution', s.name || ' (' || o.name || '): ' || s.summary,
                 'Directory: ' || s.source_description, NULL, s.verification_status,
                 ts_rank(to_tsvector('english', s.name || ' ' || s.summary || ' ' ||
                         coalesce(s.description, '')), q.q)
          FROM solution s JOIN organisation o ON o.id = s.organisation_id, q
          WHERE s.status = 'published' AND o.status = 'active'
            AND to_tsvector('english', s.name || ' ' || s.summary || ' ' ||
                coalesce(s.description, '')) @@ q.q
        ) r ORDER BY rank DESC LIMIT :limit
        """
    )
    return [
        dict(r)
        for r in session.execute(sql, {"q": question, "ids": area_ids, "limit": limit}).mappings()
    ]


def build_brief(session: Session, area_id: int, sector: str, question: str | None = None) -> dict:
    p = area_profile(session, area_id)
    if p is None:
        raise BriefError(f"no area {area_id}")
    if p["level"] == "country":
        raise BriefError("choose a state, LGA or ward")
    sec = session.execute(
        text("SELECT code, name FROM sector WHERE code = :c"), {"c": sector}
    ).first()
    if sec is None:
        raise BriefError(f"unknown sector {sector!r}")
    ev = Evidence()
    S: dict[str, list[dict]] = {
        k: []
        for k in (
            "profile",
            "infrastructure",
            "gaps",
            "beneficiaries",
            "barriers",
            "solutions",
            "opportunities",
            "limitations",
            "confidence",
            "sources",
        )
    }
    place = ", ".join(
        x
        for x in (p["name"], p["lga"] and f"{p['lga']} LGA", p["state"] and f"{p['state']} State")
        if x
    )

    # 1. Profile
    for key in ("population", "urban_classification"):
        v = p[key]
        if v and v["value"] is not None:
            if key == "population":
                t = f"Population of {p['name']}: {_fmt(v['value'])}"
                if v["lower_bound"] is not None:
                    t += f" (95% interval {_fmt(v['lower_bound'])} to {_fmt(v['upper_bound'])})"
                t += f", {v['period']}."
            else:
                t = f"{p['name']} is classified {'urban' if v['value'] >= 1 else 'rural'} ({v['period']})."
            eid = ev.add(
                "indicator", t, v["dataset_title"], v["value_type"], v["verification_status"]
            )
            S["profile"].append(_stmt("fact", t, [eid]))
    if not S["profile"]:
        S["profile"].append(_stmt("gap", f"No population estimate is loaded for {p['name']}.", []))

    # Sector values (own and context)
    sector_vals = [v for v in p["indicators"] + p["context_indicators"] if v["sector"] == sector]
    val_ids = {}
    for v in sector_vals:
        where = (
            ""
            if not v["is_context"]
            else f" ({v['measured_at_level']} figure for {v['measured_at_area']})"
        )
        t = (
            f"{v['name']}: {_fmt(v['value'])} {v['unit'] or ''}".rstrip()
            + f"{where}, {v['period']}."
        )
        val_ids[v["indicator"]] = ev.add(
            "indicator" if not v["is_context"] else "context",
            t,
            v["dataset_title"],
            v["value_type"],
            v["verification_status"],
        )

    # 2. Infrastructure
    kind = SECTOR_FACILITY.get(sector)
    fac = next((f for f in p["facilities"] if f["kind"] == kind), None)
    if fac:
        t = f"{fac['total']} {kind} facilities are recorded in {p['name']}."
        eid = ev.add("facilities", t, ", ".join(fac["datasets"]), "measured", "unverified")
        S["infrastructure"].append(_stmt("fact", t, [eid]))
    elif kind and p["facility_coverage"].get(kind):
        t = f"No {kind} facilities are recorded in {p['name']} in the loaded data."
        eid = ev.add(
            "facilities", t, ", ".join(p["facility_coverage"][kind]), "measured", "unverified"
        )
        S["infrastructure"].append(_stmt("fact", t, [eid]))
    else:
        S["infrastructure"].append(
            _stmt(
                "gap",
                f"No {kind or sector} facility data is loaded for {p['state'] or p['name']}.",
                [],
            )
        )
    for eid in val_ids.values():
        S["infrastructure"].append(_stmt("fact", ev.items[int(eid[1:]) - 1]["text"], [eid]))

    # 3. Gaps
    parent_level = {"ward": "state", "lga": "state", "state": "country"}[p["level"]]
    chain_ids = session.execute(
        text(
            "WITH RECURSIVE up AS (SELECT id, level, parent_id FROM admin_area WHERE id = :id "
            "UNION ALL SELECT a.id, a.level, a.parent_id FROM admin_area a JOIN up ON a.id = up.parent_id) "
            "SELECT id, level FROM up"
        ),
        {"id": area_id},
    ).all()
    scope = next(i for i, lvl in chain_ids if lvl == parent_level)
    res = assess(session, sector, p["level"], scope)
    mine = next((r for r in res["areas"] if r["id"] == area_id), None)
    conf_label = "insufficient"
    if mine and mine["components"]:
        for c in mine["components"]:
            eid = ev.add(
                "gap_score",
                c["statement"],
                f"Needs assessment ({c['dataset']})",
                "derived",
                c["verification_status"],
            )
            S["gaps"].append(_stmt("derived", c["statement"], [eid]))
        if mine["score"] is not None:
            conf_label = mine["confidence_label"]
            t = (
                f"Overall {sec.name.lower()} gap score {mine['score']:g} of 100, rank {mine['rank']} of "
                f"{res['areas_scored']} comparable areas ({mine['confidence_label']} confidence)."
            )
            eid = ev.add("gap_score", t, "Needs assessment", "derived", None)
            S["gaps"].insert(0, _stmt("derived", t, [eid]))
    else:
        S["gaps"].append(
            _stmt(
                "gap",
                res["message"]
                or f"No {sec.name.lower()} indicator allows {p['name']} to be compared with similar areas.",
                [],
            )
        )

    # 4. Beneficiaries (only groups named in the evidence)
    claims = p["claims"]
    for c in claims:
        if c["attribute"] in ("economic_activities", "community_organisations", "languages"):
            t = f"{c['attribute_label']}: {c['value_text']}"
            eid = ev.add(
                "claim", t, c["source_description"], c["value_type"], c["verification_status"]
            )
            S["beneficiaries" if c["attribute"] == "economic_activities" else "profile"].append(
                _stmt("fact", t, [eid])
            )

    # 5. Barriers
    for code, (threshold, below, wording) in BARRIERS.items():
        v = next(
            (x for x in p["indicators"] + p["context_indicators"] if x["indicator"] == code), None
        )
        if v is None or v["value"] is None:
            continue
        barrier = v["value"] < threshold if below else v["value"] > threshold
        if barrier:
            eid = val_ids.get(code) or ev.add(
                "indicator" if not v["is_context"] else "context",
                f"{v['name']}: {_fmt(v['value'])} {v['unit'] or ''}".rstrip() + f", {v['period']}.",
                v["dataset_title"],
                v["value_type"],
                v["verification_status"],
            )
            S["barriers"].append(
                _stmt(
                    "derived",
                    f"Low {wording} may limit adoption ({_fmt(v['value'])}{' %' if (v['unit'] or '').startswith('%') else ''}; rule: "
                    f"{'below' if below else 'above'} {threshold}).",
                    [eid],
                )
            )
    if not S["barriers"]:
        S["barriers"].append(
            _stmt(
                "gap",
                "No connectivity, electricity, literacy or financial access indicator is loaded that shows a barrier here.",
                [],
            )
        )

    # 6. Solutions
    try:
        m = match(session, area_id, sector)
    except MatchingError:
        m = {"status": "error", "results": [], "message": None}
    for r in m["results"][:3]:
        t = (
            f"{r['solution']['name']} ({r['solution']['organisation_name']}) matches with score "
            f"{r['score']:g} ({r['confidence_label']} confidence; {r['criteria_known']} of 8 criteria judged)."
        )
        eid = ev.add(
            "solution",
            t,
            "Directory and matching engine",
            "derived",
            r["solution"]["verification_status"],
        )
        S["solutions"].append(_stmt("derived", t, [eid]))
        groups = [
            BENEFICIARY_GROUPS.get(g, g)
            for g in session.scalar(
                text("SELECT beneficiary_groups FROM solution WHERE id = :i"),
                {"i": r["solution"]["id"]},
            )
            or []
        ]
        if groups:
            S["beneficiaries"].append(
                _stmt(
                    "fact", f"{r['solution']['name']} serves: {', '.join(groups).lower()}.", [eid]
                )
            )
    if not S["solutions"]:
        S["solutions"].append(
            _stmt("gap", m.get("message") or "No published directory solution matches.", [])
        )
    if not S["beneficiaries"]:
        S["beneficiaries"].append(
            _stmt("gap", "No beneficiary groups are named in the evidence for this area.", [])
        )

    # 7. Opportunities (rule: evidenced gap and an available match)
    worst = [x for x in S["gaps"] if x["kind"] == "derived"]
    avail = [
        r for r in m["results"] if r["availability"] in ("nationwide", "covers_area", "covers_part")
    ]
    if worst and avail:
        S["opportunities"].append(
            _stmt(
                "recommendation",
                f"{avail[0]['solution']['name']} already operates here and addresses the evidenced gap; it is a candidate for a pilot.",
                worst[0]["cites"] + S["solutions"][0]["cites"],
            )
        )
    elif worst:
        S["opportunities"].append(
            _stmt(
                "recommendation",
                "The gap is evidenced but no matching solution operates here yet: an opening for providers in the directory "
                "that plan to expand, or for new entrants.",
                worst[0]["cites"],
            )
        )
    else:
        S["opportunities"].append(
            _stmt("gap", "No opportunity can be stated without evidence of a gap.", [])
        )

    # 8. Limitations
    missing = [x["name"] for x in p["missing_indicators"] if x["sector"] == sector]
    if missing:
        S["limitations"].append(
            _stmt("gap", "Not available for this area: " + ", ".join(missing) + ".", [])
        )
    for g in p["data_gaps"]:
        if g["sector"] in (sector, None):
            eid = ev.add("data_gap", f"{g['title']}: {g['description']}", "Recorded data gap")
            S["limitations"].append(_stmt("fact", g["title"] + ".", [eid]))

    # Search for a question
    if question:
        ids = [i for i, _ in chain_ids]
        S["related"] = []
        for h in search(session, question, ids):
            eid = ev.add(
                "search", h["body"], h["source"], h["value_type"], h["verification_status"]
            )
            S["related"].append(
                _stmt("fact", f"{h['kind'].replace('_', ' ').capitalize()}: {h['body']}", [eid])
            )
        if not S["related"]:
            S["related"].append(
                _stmt(
                    "gap",
                    "Nothing in the platform's claims, data gaps or directory matches the question.",
                    [],
                )
            )

    # 9. Confidence
    sector_facts = [
        e
        for e in ev.items
        if e["kind"] in ("indicator", "context", "facilities", "claim", "gap_score")
    ]
    S["confidence"].append(
        _stmt(
            "derived",
            f"Gap evidence confidence: {conf_label}. {len(sector_facts)} evidence items describe this area; "
            f"{sum(1 for e in sector_facts if e['verification'] in ('source_verified', 'field_verified'))} are verified.",
            [],
        )
    )

    # 10. Sources
    for src in sorted({e["source"] for e in ev.items if e["source"]}):
        S["sources"].append(
            _stmt("fact", src, [e["id"] for e in ev.items if e["source"] == src][:5])
        )

    sufficient = any(
        e["kind"] in ("indicator", "context", "facilities", "gap_score")
        and e["text"]
        and not e["text"].startswith("Population")
        and "classified" not in e["text"]
        for e in ev.items
    )
    return {
        "area": {"id": p["id"], "name": p["name"], "level": p["level"], "place": place},
        "sector": sector,
        "sector_name": sec.name,
        "question": question,
        "sufficient_evidence": sufficient,
        "sections": [{"key": k, "statements": v} for k, v in S.items()],
        "evidence": ev.items,
    }


# ---------------------------------------------------------------------- narrative

SYSTEM = (
    "You summarise evidence about a Nigerian community for a technology access platform. "
    "Use only the numbered evidence given. End every sentence with the ids it relies on, like "
    "[E2] or [E2, E5]. Use only numbers that appear in the cited evidence, written the same way. "
    "Do not name organisations, products, places or people that are not in the evidence. If the "
    "evidence does not answer something, say that it is not known. Write at most six sentences "
    "of plain prose, no headings or lists."
)

CITE = re.compile(r"\[(E\d+(?:\s*,\s*E\d+)*)\]")
NUMBER = re.compile(r"(?<![A-Za-z\d])\d[\d,]*(?:\.\d+)?")


def _norm_numbers(s: str) -> set[str]:
    out = set()
    for n in NUMBER.findall(CITE.sub(" ", s)):
        n = n.replace(",", "").rstrip(".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def validate_narrative(text_: str, evidence: list[dict]) -> list[str]:
    """Problems with a model's narrative (empty list = accepted)."""
    by_id = {e["id"]: e for e in evidence}
    problems = []
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])|\n+", text_.strip()) if s.strip()
    ]
    if not sentences:
        return ["empty reply"]
    for s in sentences:
        cites = [c.strip() for m in CITE.findall(s) for c in m.split(",")]
        if not cites:
            problems.append(f"uncited sentence: {s[:80]}")
            continue
        unknown = [c for c in cites if c not in by_id]
        if unknown:
            problems.append(f"cites evidence that does not exist ({', '.join(unknown)}): {s[:80]}")
            continue
        allowed = set().union(*(_norm_numbers(by_id[c]["text"]) for c in cites))
        extra = _norm_numbers(s) - allowed
        if extra:
            problems.append(
                f"numbers not in the cited evidence ({', '.join(sorted(extra))}): {s[:80]}"
            )
    return problems


def narrative(
    brief: dict, provider: Provider | None = None, use_default: bool = True
) -> dict[str, Any]:
    provider = provider if provider is not None else (get_provider() if use_default else None)
    if provider is None:
        return {
            "status": "disabled",
            "text": None,
            "problems": [],
            "message": "No language model is configured. The brief above is built entirely from the data.",
        }
    if not brief["sufficient_evidence"]:
        return {
            "status": "insufficient",
            "text": None,
            "problems": [],
            "message": "Not enough evidence about this sector here for a summary; the model was not asked.",
        }
    lines = [
        f"[{e['id']}] {e['text']} (source: {e['source']}; type: {e['value_type'] or 'n/a'}; "
        f"verification: {e['verification'] or 'n/a'})"
        for e in brief["evidence"]
    ]
    ask = (
        brief["question"]
        or f"What does the evidence say about {brief['sector_name'].lower()} access in {brief['area']['place']}?"
    )
    user = f"Question: {ask}\n\nEvidence:\n" + "\n".join(lines)
    try:
        reply = provider.complete(SYSTEM, user)
    except ProviderError as e:
        return {"status": "error", "text": None, "problems": [], "message": str(e)}
    problems = validate_narrative(reply, brief["evidence"])
    if problems:
        return {
            "status": "rejected",
            "text": None,
            "problems": problems,
            "model": provider.model,
            "message": "The model's summary was discarded because it was not fully supported by the evidence.",
        }
    return {
        "status": "accepted",
        "text": reply.strip(),
        "problems": [],
        "model": provider.model,
        "provider": provider.name,
        "value_type": "ai_generated",
        "message": "AI-generated summary. Every sentence cites evidence and uses only numbers from it.",
    }
