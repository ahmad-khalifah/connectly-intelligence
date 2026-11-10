"""Market entry intelligence: where and how a provider could enter, from the evidence loaded.

Inputs describe the product (or name a directory solution) and the provider's objective.
Outputs cover the brief's twelve items. Every item is tagged with its kind:

  fact            read from the database, with its source
  derived         computed here from facts (scores, counts, comparisons)
  recommendation  a rule applied to the facts; the rule and its evidence are shown
  gap             the data needed is not available; nothing is filled in

Market size, customer numbers, partnerships and costs are never estimated: no open data
supports them. Population is shown as reach, labelled modelled.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.models.directory import (
    BENEFICIARY_GROUPS,
    DEVICE_REQUIREMENTS,
    DISTRIBUTION_CHANNELS,
    INTERNET_REQUIREMENTS,
    LANGUAGES,
    POWER_REQUIREMENTS,
)
from connectly.services.directory import SOLUTION_SELECT, availability
from connectly.services.matching import (
    area_context,
    c_connectivity,
    c_distribution,
    c_feasibility,
    c_language,
)
from connectly.services.needs import assess

OBJECTIVES = {
    "pilot": "Run a pilot",
    "launch": "Launch in a new market",
    "scale": "Scale an existing service",
    "partnership": "Find delivery partners",
}

WEIGHTS = {"gap": 0.40, "fit": 0.25, "reach": 0.20, "competition": 0.15}


class MarketEntryIn(BaseModel):
    sector: str
    need: str | None = None
    solution_id: int | None = Field(None, description="Use requirements from a directory record")
    product_name: str | None = Field(None, max_length=200)
    industry: str | None = Field(None, max_length=160)
    target_groups: list[str] = Field(default_factory=list)
    price_ngn: int | None = Field(None, ge=0)
    price_unit: str | None = Field(None, max_length=64)
    internet_requirement: str | None = None
    device_requirement: str | None = None
    power_requirement: str | None = None
    languages: list[str] = Field(default_factory=list)
    distribution_channels: list[str] = Field(default_factory=list)
    objective: str = "pilot"
    budget_ngn: int | None = Field(None, ge=0)
    state_ids: list[int] = Field(default_factory=list, description="Preferred states; empty = all")


class MarketEntryError(ValueError):
    pass


def _item(kind: str, text_: str, evidence: list[str] | None = None) -> dict:
    return {"kind": kind, "text": text_, "evidence": evidence or []}


def _check(body: MarketEntryIn) -> None:
    vocab = {
        "internet_requirement": INTERNET_REQUIREMENTS,
        "device_requirement": DEVICE_REQUIREMENTS,
        "power_requirement": POWER_REQUIREMENTS,
    }
    for field, allowed in vocab.items():
        v = getattr(body, field)
        if v is not None and v not in allowed:
            raise MarketEntryError(f"{field} must be one of {', '.join(allowed)}")
    for name, values, allowed in (
        ("target_groups", body.target_groups, BENEFICIARY_GROUPS),
        ("languages", body.languages, LANGUAGES),
        ("distribution_channels", body.distribution_channels, DISTRIBUTION_CHANNELS),
    ):
        bad = [v for v in values if v not in allowed]
        if bad:
            raise MarketEntryError(f"unknown {name}: {', '.join(bad)}")
    if body.objective not in OBJECTIVES:
        raise MarketEntryError(f"objective must be one of {', '.join(OBJECTIVES)}")


def _product(session: Session, body: MarketEntryIn) -> dict:
    if body.solution_id is not None:
        row = (
            session.execute(text(SOLUTION_SELECT + " WHERE s.id = :id"), {"id": body.solution_id})
            .mappings()
            .first()
        )
        if row is None:
            raise MarketEntryError(f"no solution {body.solution_id}")
        p = dict(row)
        p["source"] = f"directory record #{p['id']}"
        return p
    return {
        "id": None,
        "name": body.product_name or "Your product",
        "need_codes": [body.need] if body.need else [],
        "internet_requirement": body.internet_requirement,
        "device_requirement": body.device_requirement,
        "power_requirement": body.power_requirement,
        "languages": body.languages,
        "distribution_channels": body.distribution_channels,
        "accessibility_features": [],
        "verification_status": "unverified",
        "beneficiary_groups": body.target_groups,
        "price_min_ngn": body.price_ngn,
        "price_unit": body.price_unit,
        "source": "details entered for this analysis",
    }


def _power_fit(product: dict, ctx: dict):
    """Power requirement against household electricity access (None if not judgeable)."""
    from connectly.services.matching import Criterion

    req = product.get("power_requirement")
    if req in ("none", "self_powered"):
        return Criterion("feasibility", 1.0, POWER_REQUIREMENTS[req], [])
    elec = ctx["values"].get("energy.households_electricity_pct")
    if req in ("occasional_charging", "grid") and elec:
        share = elec["value"] / 100
        return Criterion(
            "feasibility", min(1.0, share + 0.4) if req == "occasional_charging" else share, "", []
        )
    return None


def _percentile(values: dict[int, float]) -> dict[int, float]:
    order = sorted(values, key=lambda k: values[k])
    n = len(order)
    return {k: (i / (n - 1) if n > 1 else 0.5) for i, k in enumerate(order)}


def analyse(session: Session, body: MarketEntryIn) -> dict[str, Any]:
    _check(body)
    sector = session.execute(
        text("SELECT code, name FROM sector WHERE code = :c"), {"c": body.sector}
    ).first()
    if sector is None:
        raise MarketEntryError(f"unknown sector {body.sector!r}")
    need_names = dict(session.execute(text("SELECT code, name FROM need_category")).all())
    if body.need and body.need not in need_names:
        raise MarketEntryError(f"unknown need {body.need!r}")
    product = _product(session, body)
    needs = set(product["need_codes"]) or ({body.need} if body.need else set())

    # Candidate areas: LGAs of the preferred states, or all states.
    if body.state_ids:
        states = session.execute(
            text("SELECT id, name FROM admin_area WHERE id = ANY(:ids) AND level = 'state'"),
            {"ids": body.state_ids},
        ).all()
        if len(states) != len(set(body.state_ids)):
            raise MarketEntryError("state_ids must all be states")
        level, scopes = "lga", [(sid, name) for sid, name in states]
    else:
        country = session.scalar(text("SELECT id FROM admin_area WHERE level = 'country' LIMIT 1"))
        level, scopes = "state", [(country, "Nigeria")]

    gap: dict[int, dict] = {}
    names: dict[int, str] = {}
    parents: dict[int, str] = {}
    pops: dict[int, float] = {}
    gap_status = []
    for scope_id, scope_name in scopes:
        res = assess(session, body.sector, level, scope_id)
        gap_status.append({"scope": scope_name, "status": res["status"], "message": res["message"]})
        for a in res["areas"]:
            names[a["id"]] = a["name"]
            parents[a["id"]] = scope_name if level == "lga" else None
            if a["population"] is not None:
                pops[a["id"]] = a["population"]
            gap[a["id"]] = a
    ids = list(names)
    reach = _percentile(pops)

    # Competitors: published solutions addressing the same needs, by availability.
    comp_rows = []
    if needs:
        comp_rows = [
            dict(r)
            for r in session.execute(
                text(
                    SOLUTION_SELECT + " WHERE s.status = 'published' AND o.status = 'active' "
                    "AND s.is_active AND EXISTS (SELECT 1 FROM solution_need sn JOIN "
                    "need_category n ON n.id = sn.need_category_id WHERE sn.solution_id = s.id "
                    "AND n.code = ANY(:needs))" + (" AND s.id <> :own" if product["id"] else "")
                ),
                {"needs": list(needs), "own": product["id"]},
            ).mappings()
        ]

    candidates = []
    for aid in ids:
        ctx = area_context(session, aid)
        conn = c_connectivity(product, ctx)
        power = _power_fit(product, ctx)
        fit_parts = [
            c
            for c in (conn, c_language(product, ctx), c_distribution(product, ctx, conn), power)
            if c is not None and c.score is not None
        ]
        # Fit covers local conditions only (not record verification).
        fit = sum(c.score for c in fit_parts) / len(fit_parts) if fit_parts else None
        comps = []
        if comp_rows:
            av = availability(session, aid, [c["id"] for c in comp_rows])
            comps = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "organisation": c["organisation_name"],
                    "availability": av[c["id"]],
                }
                for c in comp_rows
                if av.get(c["id"]) in ("nationwide", "covers_area", "covers_part")
            ]
        g = gap[aid]
        parts = {
            "gap": None if g["score"] is None else g["score"] / 100,
            "fit": fit,
            "reach": reach.get(aid),
            "competition": (1 / (1 + len(comps))) if needs else None,
        }
        known = {k: v for k, v in parts.items() if v is not None}
        wk = sum(WEIGHTS[k] for k in known)
        # Without evidence of need there is no opportunity score: population and fit alone
        # would rank areas by size, which is not evidence that anyone needs the product.
        score = (
            sum(WEIGHTS[k] * v for k, v in known.items()) / wk
            if wk and parts["gap"] is not None
            else None
        )
        confidence = wk * (g["confidence"] if g["confidence"] is not None else 0.5)
        candidates.append(
            {
                "id": aid,
                "name": names[aid],
                "state": parents[aid],
                "level": level,
                "population": pops.get(aid),
                "score": None if score is None else round(score * 100, 1),
                "confidence": round(confidence, 2),
                "components": {k: (None if v is None else round(v, 2)) for k, v in parts.items()},
                "gap": {k: g[k] for k in ("score", "confidence_label", "rank")}
                | {"evidence": [c["statement"] for c in g["components"][:3]]},
                "fit": [
                    c.out()
                    for c in (
                        conn,
                        c_language(product, ctx),
                        c_distribution(product, ctx, conn),
                        c_feasibility(product, None, ctx),
                    )
                ],
                "need_evidenced": parts["gap"] is not None,
                "competitors": comps,
                "ctx": ctx,
            }
        )
    candidates.sort(
        key=lambda c: (c["score"] is None, -(c["score"] or 0) * (0.5 + 0.5 * c["confidence"]))
    )
    for i, c in enumerate(candidates, 1):
        c["rank"] = i
    top = candidates[:3]
    report = _sections(session, body, product, need_names, needs, top, candidates, gap_status)
    for c in candidates:
        c.pop("ctx")
    return {
        "sector": sector.code,
        "sector_name": sector.name,
        "objective": OBJECTIVES[body.objective],
        "product": {
            k: product.get(k)
            for k in (
                "id",
                "name",
                "internet_requirement",
                "device_requirement",
                "power_requirement",
                "languages",
                "distribution_channels",
                "source",
            )
        },
        "needs": [{"code": n, "name": need_names.get(n, n)} for n in sorted(needs)],
        "level": level,
        "weights": WEIGHTS,
        "candidates": candidates,
        "sections": report,
    }


def _sections(session, body, product, need_names, needs, top, candidates, gap_status) -> list[dict]:
    S: list[dict] = []
    scored = [c for c in candidates if c["score"] is not None]

    def add(key: str, title: str, items: list[dict]) -> None:
        S.append({"key": key, "title": title, "items": items})

    # 1. Suitable areas
    items = []
    for c in top:
        if c["score"] is None:
            continue
        ev = c["gap"]["evidence"] + [
            f"Reach: {c['population']:,.0f} people (modelled, unverified)"
            if c["population"]
            else ""
        ]
        items.append(
            _item(
                "derived",
                f"{c['name']}{', ' + c['state'] if c['state'] else ''}: opportunity score "
                f"{c['score']:.0f} (confidence {c['confidence']:.2f}).",
                [e for e in ev if e],
            )
        )
    if not items:
        items.append(
            _item(
                "gap",
                "No area could be scored: "
                + "; ".join(f"{g['scope']}: {g['message']}" for g in gap_status if g["message"])
                + ".",
            )
        )
    add("areas", "Suitable states and communities", items)

    # 2. Beneficiary segments
    seg = []
    for g in body.target_groups:
        seg.append(_item("fact", f"Target group chosen: {BENEFICIARY_GROUPS[g]}."))
    for c in top:
        for code in (
            "finance.financially_excluded_adults_pct",
            "education.women_literate_pct",
            "connectivity.households_mobile_phone_pct",
            "energy.households_electricity_pct",
        ):
            row = c["ctx"]["values"].get(code)
            if row:
                seg.append(
                    _item(
                        "fact",
                        f"{c['name']}: {row['indicator_name']} {row['value']:g}{row['unit'] and ' ' + row['unit'] or ''} "
                        f"({row['geo_level']} level, {row['period']}).",
                        [row["dataset_title"]],
                    )
                )
    if len(seg) == len(body.target_groups):
        seg.append(
            _item(
                "gap",
                "No survey indicators describing beneficiary segments are loaded for these areas.",
            )
        )
    add("segments", "Target beneficiary segments", seg)

    # 3. Demand
    dem = [
        _item(
            "gap",
            "Market demand (customers, willingness to pay, market size) is not measured "
            "in any open dataset, so it is not estimated.",
        )
    ]
    total = sum(c["population"] or 0 for c in top if c["score"] is not None)
    if total:
        dem.append(
            _item(
                "derived",
                f"Modelled population of the top areas: {total:,.0f}. This is reach, not demand.",
            )
        )
    add("demand", "Potential market demand", dem)

    # 4. Competitors
    comp = []
    for c in top:
        if c["competitors"]:
            comp.append(
                _item(
                    "fact",
                    f"{c['name']}: "
                    + "; ".join(f"{x['name']} ({x['organisation']})" for x in c["competitors"])
                    + ".",
                )
            )
    if not needs:
        comp.append(_item("gap", "Choose a need to look for competing solutions."))
    elif not comp:
        comp.append(
            _item(
                "fact",
                "No published directory solution addressing the same need operates in the top areas. "
                "The directory is curated and may be incomplete.",
            )
        )
    add("competition", "Existing competing solutions", comp)

    # 5. Community organisations
    orgs = []
    for c in top:
        rows = session.execute(
            text(
                "SELECT value_text, verification_status, source_description FROM claim WHERE "
                "attribute = 'community_organisations' AND is_active AND subject_type = 'admin_area' "
                "AND subject_id = ANY(:ids)"
            ),
            {"ids": [a["id"] for a in c["ctx"]["chain"]]},
        ).all()
        for v, st, src in rows:
            orgs.append(_item("fact", f"{c['name']}: {v} ({st.replace('_', ' ')}).", [src]))
    if not orgs:
        orgs.append(
            _item(
                "gap",
                "No community organisations are recorded for these areas. Researchers can add them on "
                "community profiles.",
            )
        )
    add("community_organisations", "Relevant community organisations", orgs)

    # 6. Institutional partners
    part = []
    for c in top:
        fac = c["ctx"]["facilities"]
        if fac:
            part.append(
                _item(
                    "fact",
                    f"{c['name']}: "
                    + ", ".join(f"{n} {k}" for k, n in sorted(fac.items()))
                    + " facilities recorded (possible delivery points, not confirmed partners).",
                )
            )
    partners = session.execute(
        text(
            "SELECT DISTINCT o.name, o.org_type FROM organisation o JOIN solution s ON s.organisation_id = o.id "
            "WHERE o.status = 'active' AND s.status = 'published' AND cardinality(s.partnership_types) > 0 "
            "AND o.org_type IN ('ngo', 'government', 'social_enterprise', 'cooperative') ORDER BY o.name"
        )
    ).all()
    for name, t in partners:
        part.append(
            _item(
                "fact",
                f"{name} ({t.replace('_', ' ')}) lists partnership interests in the directory.",
            )
        )
    if not part:
        part.append(
            _item("gap", "No institutional partners or facilities are recorded for these areas.")
        )
    add("partners", "Potential institutional partnerships", part)

    # 7. Distribution channels
    dist = []
    for c in top:
        d = next(f for f in c["fit"] if f["key"] == "distribution")
        dist.append(
            _item("derived" if d["score"] is not None else "gap", f"{c['name']}: {d['reason']}")
        )
    if not product["distribution_channels"]:
        dist.append(_item("gap", "No distribution channels were given for the product."))
    add("distribution", "Distribution channels", dist)

    # 8. Languages
    lang = []
    for c in top:
        ls = c["ctx"]["languages"]
        lang.append(
            _item(
                "fact" if ls else "gap",
                f"{c['name']}: "
                + (
                    ", ".join(LANGUAGES.get(x, x) for x in ls) + " (recorded by researchers)."
                    if ls
                    else "no languages recorded yet."
                ),
            )
        )
    add("languages", "Local languages", lang)

    # 9-10. Communication and acquisition (rules applied to evidence)
    comm, acq = [], []
    for c in top:
        v = c["ctx"]["values"]
        lit = v.get("education.women_literate_pct")
        ph = v.get("connectivity.households_mobile_phone_pct")
        tw = v.get("connectivity.nearest_tower_km_ward_point")
        if lit and lit["value"] < 50:
            comm.append(
                _item(
                    "recommendation",
                    f"{c['name']}: use voice, pictures and in-person demonstration; "
                    f"women's literacy is {lit['value']:g}% ({lit['geo_level']} level).",
                    [lit["dataset_title"]],
                )
            )
        if ph and ph["value"] < 70:
            comm.append(
                _item(
                    "recommendation",
                    f"{c['name']}: do not rely on phone-only outreach; "
                    f"{ph['value']:g}% of households have a mobile phone.",
                    [ph["dataset_title"]],
                )
            )
        if c["ctx"]["languages"]:
            comm.append(
                _item(
                    "recommendation",
                    f"{c['name']}: communicate in "
                    + ", ".join(LANGUAGES.get(x, x) for x in c["ctx"]["languages"])
                    + ".",
                )
            )
        if tw and tw["value"] > 10:
            acq.append(
                _item(
                    "recommendation",
                    f"{c['name']}: plan for offline sign-up; the nearest recorded "
                    f"mobile site is {tw['value']:g} km from the ward centre.",
                    [tw["dataset_title"]],
                )
            )
        fac = c["ctx"]["facilities"]
        for kind, channel in (
            ("health", "health facilities"),
            ("financial", "agents and bank branches"),
            ("education", "schools"),
            ("market", "markets"),
        ):
            if fac.get(kind):
                acq.append(
                    _item(
                        "recommendation",
                        f"{c['name']}: recruit users through {channel} ({fac[kind]} recorded).",
                    )
                )
    if not comm:
        comm.append(
            _item(
                "gap",
                "No literacy, phone ownership or language data is loaded for these areas, so no "
                "communication approach can be grounded in evidence. Verify locally.",
            )
        )
    if not acq:
        acq.append(
            _item(
                "gap",
                "No connectivity or facility data is loaded for these areas, so no acquisition "
                "approach can be grounded in evidence.",
            )
        )
    add("communication", "Communication strategies", comm)
    add("acquisition", "User acquisition approaches", acq)

    # 11. Risks
    risks = []
    for c in top:
        for f in c["fit"]:
            if f["score"] is not None and f["score"] < 0.5:
                risks.append(_item("derived", f"{c['name']}, {f['label'].lower()}: {f['reason']}"))
            elif f["score"] is None:
                risks.append(
                    _item("gap", f"{c['name']}, {f['label'].lower()}: not known. {f['reason']}")
                )
        if c["gap"]["confidence_label"] in ("low", "insufficient"):
            risks.append(
                _item(
                    "gap", f"{c['name']}: the evidence of need is {c['gap']['confidence_label']}."
                )
            )
    if body.budget_ngn is not None:
        risks.append(
            _item(
                "gap",
                f"Budget ₦{body.budget_ngn:,} noted. No open cost data exists, so the budget is "
                "not compared with entry costs.",
            )
        )
    if product["verification_status"] not in ("source_verified", "field_verified"):
        risks.append(_item("fact", "Product requirements are as entered and not verified."))
    add("risks", "Implementation risks", risks)

    # 12. Strategy
    strat = []
    best = next((c for c in top if c["score"] is not None), None)
    if best:
        dist_best = next(f for f in best["fit"] if f["key"] == "distribution")
        steps = [
            f"{OBJECTIVES[body.objective]} in {best['name']}{', ' + best['state'] if best['state'] else ''}, "
            f"the highest-ranked area (score {best['score']:.0f}).",
        ]
        if dist_best["score"] is not None and dist_best["score"] >= 0.8:
            steps.append(f"Use the channel that is supported here: {dist_best['reason']}")
        unknown = [f["label"].lower() for f in best["fit"] if f["score"] is None]
        if unknown:
            steps.append("Before committing, verify in the field: " + ", ".join(unknown) + ".")
        if len(scored) > 1:
            steps.append("Then compare with " + ", ".join(c["name"] for c in scored[1:3]) + ".")
        strat.append(
            _item("recommendation", " ".join(steps), ["Rule-based summary of the sections above"])
        )
    else:
        strat.append(
            _item(
                "gap",
                "No entry strategy can be recommended: there is not enough evidence to rank areas "
                "for this sector. Load the datasets listed on the Data sources page, or choose a "
                "different sector or state.",
            )
        )
    add("strategy", "Recommended entry strategy", strat)
    return S
