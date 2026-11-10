"""Technology matching: rank published solutions for one area and one sector.

Eight criteria from the brief, each scored 0-1 from data, or "unknown" when the data needed
is missing (unknown lowers confidence; it never counts as a pass or a fail):

1. relevance        solution's needs vs the needs selected or shown by the area's gap evidence
2. suitability      beneficiary groups vs target groups; literacy requirement vs literacy
3. availability     where the solution operates vs the area
4. affordability    published price vs the user's price ceiling, else the pricing model
5. connectivity     internet and device requirements vs tower distance and phone ownership
6. language         languages supported vs languages recorded for the area
7. distribution     channels vs channels that exist in the area (facilities, agents, sites)
8. feasibility      power requirement vs electricity access; local presence; verification

A solution is only considered if it addresses one of the target needs. Products are not
recommended merely because they are in the same sector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.models.directory import (
    BENEFICIARY_GROUPS,
    DEVICE_REQUIREMENTS,
    INTERNET_REQUIREMENTS,
    LANGUAGES,
    LITERACY_REQUIREMENTS,
    POWER_REQUIREMENTS,
    PRICING_MODELS,
)
from connectly.services.directory import SOLUTION_SELECT, availability
from connectly.services.needs import assess
from connectly.services.profiles import ancestors, observations_for

CRITERIA = {
    "relevance": ("Relevance to the identified need", 0.20),
    "suitability": ("Suitability for the target population", 0.10),
    "availability": ("Geographic availability", 0.15),
    "affordability": ("Affordability", 0.10),
    "connectivity": ("Internet and device requirements", 0.15),
    "language": ("Language accessibility", 0.10),
    "distribution": ("Distribution requirements", 0.10),
    "feasibility": ("Implementation feasibility", 0.10),
}

# Which needs an indicator's gap points to.
INDICATOR_NEEDS = {
    "health.facilities_per_10k": [
        "health.care_delivery",
        "health.telemedicine",
        "health.diagnostics",
    ],
    "health.nearest_facility_km_ward_point": ["health.telemedicine", "health.care_delivery"],
    "health.settlements_over_5km_pct": ["health.telemedicine", "health.care_delivery"],
    "health.births_in_facility_pct": ["health.care_delivery", "health.health_information"],
    "connectivity.sites_per_10k": [
        "connectivity.internet_access",
        "connectivity.community_networks",
        "connectivity.digital_infrastructure",
    ],
    "connectivity.nearest_tower_km_ward_point": [
        "connectivity.internet_access",
        "connectivity.community_networks",
    ],
    "connectivity.households_mobile_phone_pct": [
        "connectivity.affordable_broadband",
        "connectivity.connectivity_services",
    ],
    "finance.access_points_per_10k": ["finance.agent_banking", "finance.digital_payments"],
    "finance.nearest_access_point_km_ward_point": [
        "finance.agent_banking",
        "finance.digital_banking",
    ],
    "finance.financially_excluded_adults_pct": [
        "finance.digital_banking",
        "finance.financial_literacy",
        "finance.microfinance_tech",
    ],
    "education.schools_per_10k": ["education.digital_learning", "education.online_resources"],
    "education.women_literate_pct": ["education.digital_skills", "education.digital_learning"],
    "energy.households_electricity_pct": [
        "energy.solar",
        "energy.affordable_electricity",
        "energy.renewable_systems",
    ],
    "commerce.markets_per_10k": ["commerce.digital_marketplaces", "commerce.ecommerce"],
}

# Channel → facility kind whose presence in the area makes the channel usable.
CHANNEL_FACILITY = {
    "agents": "financial",
    "bank_partner": "financial",
    "health_facilities": "health",
    "schools": "education",
    "mobile_operator": "telecom",
    "retail": "market",
}
CHANNELS_NOT_MEASURABLE = {
    "ngo_partner",
    "government",
    "cooperatives",
    "community_leaders",
}

VERIFIED = {"source_verified", "field_verified"}


class MatchingError(ValueError):
    pass


@dataclass
class Criterion:
    key: str
    score: float | None
    reason: str
    evidence: list[str]

    def out(self) -> dict:
        label, weight = CRITERIA[self.key]
        return {
            "key": self.key,
            "label": label,
            "weight": weight,
            "score": None if self.score is None else round(self.score, 2),
            "reason": self.reason,
            "evidence": self.evidence,
        }


# ------------------------------------------------------------------ area context


def area_context(session: Session, area_id: int) -> dict[str, Any]:
    chain = ancestors(session, area_id)
    if not chain:
        raise MatchingError(f"no area {area_id}")
    area = chain[0]
    rank = {a["level"]: i for i, a in enumerate(chain)}
    values: dict[str, dict] = {}
    for r in sorted(observations_for(session, chain), key=lambda r: rank[r["geo_level"]]):
        values.setdefault(r["code"], r)  # the closest level wins
    langs = (
        session.execute(
            text(
                """
            SELECT DISTINCT unnest(c.value_codes) FROM claim c
            WHERE c.attribute = 'languages' AND c.is_active
              AND c.verification_status NOT IN ('disputed', 'retired')
              AND c.subject_type = 'admin_area' AND c.subject_id = ANY(:ids)
            """
            ),
            {"ids": [a["id"] for a in chain]},
        )
        .scalars()
        .all()
    )
    col = {"state": "state_id", "lga": "lga_id", "ward": "ward_id"}.get(area["level"])
    facilities: dict[str, int] = {}
    covered: set[str] = set()
    if col:
        facilities = dict(
            session.execute(
                text(f"SELECT kind, count(*) FROM facility WHERE {col} = :id GROUP BY kind"),
                {"id": area_id},
            ).all()
        )
        state = next((a["id"] for a in chain if a["level"] == "state"), None)
        for kind, cov in session.execute(
            text(
                "SELECT DISTINCT f.kind, d.extra->'coverage_state_ids' FROM facility f "
                "JOIN dataset d ON d.id = f.dataset_id"
            )
        ).all():
            if cov is None or state in (cov or []):
                covered.add(kind)
    return {
        "area": area,
        "chain": chain,
        "values": values,
        "languages": sorted(langs),
        "facilities": facilities,
        "facility_kinds_covered": covered,
    }


def _v(ctx: dict, code: str) -> dict | None:
    return ctx["values"].get(code)


def _ev(row: dict) -> str:
    where = row["geo_level"].upper() if row["geo_level"] == "lga" else row["geo_level"]
    return (
        f"{row['indicator_name']}: {row['value']:g} {row['unit'] or ''} ({where} level, "
        f"{row['value_type']}, {row['verification_status']}, {row['period']}, {row['dataset_key']})"
    ).replace("  ", " ")


# ----------------------------------------------------------------------- criteria


def c_relevance(sol: dict, target: set[str], need_names: dict) -> Criterion:
    hit = sorted(set(sol["need_codes"]) & target)
    names = ", ".join(need_names.get(n, n) for n in hit)
    return Criterion(
        "relevance",
        min(1.0, 0.7 + 0.15 * len(hit)),
        f"Addresses {names}.",
        [f"Solution record lists: {', '.join(need_names.get(n, n) for n in sol['need_codes'])}"],
    )


def c_suitability(sol: dict, groups: list[str], ctx: dict) -> Criterion:
    parts, ev, reasons = [], [], []
    if groups:
        if sol["beneficiary_groups"]:
            overlap = set(groups) & set(sol["beneficiary_groups"])
            parts.append(1.0 if overlap else 0.2)
            reasons.append(
                "Serves " + ", ".join(BENEFICIARY_GROUPS[g].lower() for g in overlap)
                if overlap
                else "Does not list the target groups among its beneficiaries"
            )
        else:
            reasons.append("Beneficiary groups not stated")
    lit = sol["literacy_requirement"]
    row = _v(ctx, "education.women_literate_pct")
    if lit in ("none", "basic"):
        parts.append(1.0)
        reasons.append(f"Literacy needed: {LITERACY_REQUIREMENTS[lit].lower()}")
    elif lit in ("functional", "digital"):
        if row:
            ev.append(_ev(row))
            parts.append(min(1.0, row["value"] / 100 + 0.1))
            reasons.append(
                f"Needs {LITERACY_REQUIREMENTS[lit].lower()}; {row['value']:g}% of women are "
                f"literate ({row['geo_level']} figure)"
            )
        else:
            reasons.append(f"Needs {LITERACY_REQUIREMENTS[lit].lower()}; local literacy not known")
    else:
        reasons.append("Literacy requirement not stated")
    if sol["accessibility_features"] and {"voice", "low_literacy_design", "assisted_use"} & set(
        sol["accessibility_features"]
    ):
        reasons.append("Has features for low-literacy users")
    score = sum(parts) / len(parts) if parts else None
    return Criterion("suitability", score, "; ".join(reasons) + ".", ev)


AVAIL_SCORE = {
    "nationwide": (1.0, "Available in every state"),
    "covers_area": (1.0, "Operates in this area"),
    "covers_part": (0.7, "Operates in part of this area"),
    "expansion_interest": (0.4, "Not operating here yet; the provider wants to expand here"),
    "not_available": (0.1, "Does not operate here"),
}


def c_availability(av: str | None) -> Criterion:
    if av in AVAIL_SCORE:
        s, r = AVAIL_SCORE[av]
        return Criterion("availability", s, r + ".", ["Directory coverage record"])
    return Criterion("availability", None, "Coverage not stated by the provider.", [])


PRICING_BASE = {
    "free": 1.0,
    "donor_funded": 1.0,
    "freemium": 0.8,
    "b2b_contract": 0.7,
    "pay_as_you_go": 0.7,
    "pay_per_use": 0.7,
    "subscription": 0.5,
    "one_off": 0.4,
}


def c_affordability(sol: dict, max_price: int | None) -> Criterion:
    lo, model = sol["price_min_ngn"], sol["pricing_model"]
    unit = f" {sol['price_unit']}" if sol["price_unit"] else ""
    if max_price is not None and lo is not None:
        s = 1.0 if lo <= max_price else 0.5 if lo <= 2 * max_price else 0.1
        return Criterion(
            "affordability",
            s,
            f"Lowest published price ₦{lo:,}{unit} against your ceiling of ₦{max_price:,}.",
            ["Price as published by the provider"],
        )
    if model in PRICING_BASE:
        note = (
            " No income data for this area is open, so affordability is judged from the pricing "
            "model only."
        )
        price = f" (from ₦{lo:,}{unit})" if lo is not None else ""
        return Criterion(
            "affordability", PRICING_BASE[model], f"{PRICING_MODELS[model]}{price}.{note}", []
        )
    return Criterion("affordability", None, "Price and pricing model not published.", [])


def c_connectivity(sol: dict, ctx: dict) -> Criterion:
    net, dev = sol["internet_requirement"], sol["device_requirement"]
    tower = _v(ctx, "connectivity.nearest_tower_km_ward_point")
    phones = _v(ctx, "connectivity.households_mobile_phone_pct")
    parts, reasons, ev = [], [], []
    if net in ("none", "sms_ussd", "intermittent"):
        parts.append(1.0 if net != "sms_ussd" or not tower or tower["value"] <= 15 else 0.6)
        reasons.append(INTERNET_REQUIREMENTS[net])
    elif net in ("mobile_2g", "mobile_3g", "broadband_4g"):
        if tower:
            km = tower["value"]
            ev.append(_ev(tower))
            if net == "broadband_4g":
                s = 0.8 if km <= 3 else 0.3
            else:
                s = 1.0 if km <= 5 else 0.6 if km <= 15 else 0.3
            parts.append(s)
            reasons.append(
                f"Needs {INTERNET_REQUIREMENTS[net].lower()}; nearest recorded mobile site "
                f"{km:g} km (crowdsourced site locations; coverage is not measured)"
            )
        else:
            reasons.append(f"Needs {INTERNET_REQUIREMENTS[net].lower()}; local coverage not known")
    else:
        reasons.append("Internet requirement not stated")
    if dev in ("none", "special_hardware"):
        parts.append(1.0)
        reasons.append(DEVICE_REQUIREMENTS[dev])
    elif dev in ("basic_phone", "smartphone"):
        if phones:
            ev.append(_ev(phones))
            share = phones["value"] / 100
            parts.append(max(0.2, share if dev == "basic_phone" else share * 0.6))
            reasons.append(
                f"Needs {DEVICE_REQUIREMENTS[dev].lower()}; {phones['value']:g}% of households "
                f"have a mobile phone ({phones['geo_level']} figure"
                + (
                    "; smartphone ownership is not measured in open data)"
                    if dev == "smartphone"
                    else ")"
                )
            )
        else:
            reasons.append(f"Needs {DEVICE_REQUIREMENTS[dev].lower()}; phone ownership not known")
    elif dev == "computer":
        parts.append(0.2)
        reasons.append("Needs a computer")
    else:
        reasons.append("Device requirement not stated")
    # Parts whose local data is missing are left out; if nothing can be judged, unknown.
    score = sum(parts) / len(parts) if parts else None
    return Criterion("connectivity", score, "; ".join(reasons) + ".", ev)


def c_language(sol: dict, ctx: dict) -> Criterion:
    local = set(ctx["languages"])
    supported = set(sol["languages"])
    if not supported:
        return Criterion("language", None, "Languages supported not stated.", [])
    if not local:
        return Criterion(
            "language",
            None,
            "Supports "
            + ", ".join(LANGUAGES.get(c, c) for c in sorted(supported))
            + ". No languages are recorded for this area yet (add them on its profile).",
            [],
        )
    overlap = supported & local
    audio = {"voice", "local_language_audio"} & set(sol["accessibility_features"])
    if overlap:
        s = 1.0
        reason = "Supports " + ", ".join(LANGUAGES[c] for c in sorted(overlap)) + ", spoken here"
    else:
        s = 0.4 if audio else 0.2
        reason = "None of the languages recorded here is supported"
    return Criterion(
        "language",
        s,
        reason + ".",
        ["Languages recorded here: " + ", ".join(LANGUAGES.get(c, c) for c in sorted(local))],
    )


def c_distribution(sol: dict, ctx: dict, connectivity: Criterion) -> Criterion:
    channels = sol["distribution_channels"]
    if not channels:
        return Criterion("distribution", None, "Distribution channels not stated.", [])
    best, reasons, ev = None, [], []
    for ch in channels:
        s = None
        kind = CHANNEL_FACILITY.get(ch)
        if kind:
            n = ctx["facilities"].get(kind, 0)
            if n:
                s = 1.0
                reasons.append(f"{ch.replace('_', ' ')}: {n} {kind} facilities recorded here")
            elif kind in ctx["facility_kinds_covered"]:
                s = 0.2
                reasons.append(f"{ch.replace('_', ' ')}: no {kind} facilities recorded here")
        elif ch == "direct_digital":
            s = connectivity.score
            if s is not None:
                reasons.append("direct sign-up: depends on connectivity (see above)")
        elif ch in CHANNELS_NOT_MEASURABLE:
            reasons.append(f"{ch.replace('_', ' ')}: presence here not measured")
        if s is not None:
            best = s if best is None else max(best, s)
    if best is None:
        return Criterion(
            "distribution",
            None,
            "The data needed to check these channels here is not loaded ("
            + ", ".join(c.replace("_", " ") for c in channels)
            + ").",
            ev,
        )
    return Criterion("distribution", best, "; ".join(reasons) + ".", ev)


def c_feasibility(sol: dict, av: str | None, ctx: dict) -> Criterion:
    parts, reasons, ev = [], [], []
    power = sol["power_requirement"]
    elec = _v(ctx, "energy.households_electricity_pct")
    if power in ("none", "self_powered"):
        parts.append(1.0)
        reasons.append(POWER_REQUIREMENTS[power])
    elif power in ("occasional_charging", "grid"):
        if elec:
            ev.append(_ev(elec))
            share = elec["value"] / 100
            parts.append(min(1.0, share + 0.4) if power == "occasional_charging" else share)
            reasons.append(
                f"Needs {POWER_REQUIREMENTS[power].lower()}; {elec['value']:g}% of households have "
                f"electricity ({elec['geo_level']} figure)"
            )
        else:
            reasons.append(
                f"Needs {POWER_REQUIREMENTS[power].lower()}; electricity access not known"
            )
    else:
        reasons.append("Power requirement not stated")
    presence = {
        "nationwide": 1.0,
        "covers_area": 1.0,
        "covers_part": 0.8,
        "expansion_interest": 0.5,
    }
    if av in presence:
        parts.append(presence[av])
        reasons.append(
            "Provider already operates nearby"
            if presence[av] >= 0.8
            else "Provider plans to expand here"
        )
    elif av == "not_available":
        parts.append(0.3)
        reasons.append("Provider has no presence here")
    checked = sol["verification_status"] in VERIFIED
    parts.append(1.0 if checked else 0.6)
    reasons.append("Record checked against its source" if checked else "Record not yet verified")
    return Criterion("feasibility", sum(parts) / len(parts), "; ".join(reasons) + ".", ev)


# ------------------------------------------------------------------------- engine


def target_needs(
    session: Session, sector: str, need: str | None, ctx: dict
) -> tuple[set[str], str, list[str]]:
    if need:
        return {need}, "selected", []
    area = ctx["area"]
    if area["level"] == "country":
        return set(), "none", []
    parent_level = {"ward": "state", "lga": "state", "state": "country"}[area["level"]]
    scope = next(a["id"] for a in ctx["chain"] if a["level"] == parent_level)
    res = assess(session, sector, area["level"], scope)
    mine = next((r for r in res["areas"] if r["id"] == area["id"]), None)
    # Individual indicator comparisons count as evidence even when there are too few for an
    # overall gap score.
    if not mine or not mine["components"]:
        return set(), "none", []
    needs, statements = set(), []
    for comp in mine["components"]:
        if comp["percentile"] >= 50:
            needs.update(INDICATOR_NEEDS.get(comp["indicator"], []))
            statements.append(comp["statement"])
    return needs, "gap_evidence", statements


def match(
    session: Session,
    area_id: int,
    sector: str,
    need: str | None = None,
    target_groups: list[str] | None = None,
    max_price_ngn: int | None = None,
) -> dict[str, Any]:
    ctx = area_context(session, area_id)
    sector_row = session.execute(
        text("SELECT id, name FROM sector WHERE code = :c"), {"c": sector}
    ).first()
    if sector_row is None:
        raise MatchingError(f"unknown sector {sector!r}")
    need_names = dict(session.execute(text("SELECT code, name FROM need_category")).all())
    if need and need not in need_names:
        raise MatchingError(f"unknown need {need!r}")
    for g in target_groups or []:
        if g not in BENEFICIARY_GROUPS:
            raise MatchingError(f"unknown beneficiary group {g!r}")
    target, basis, gap_statements = target_needs(session, sector, need, ctx)
    base = {
        "area": {k: ctx["area"][k] for k in ("id", "name", "level")},
        "breadcrumbs": [{k: a[k] for k in ("id", "name", "level")} for a in reversed(ctx["chain"])],
        "sector": sector,
        "sector_name": sector_row.name,
        "need": need,
        "target_needs": [{"code": n, "name": need_names.get(n, n)} for n in sorted(target)],
        "needs_basis": basis,
        "gap_evidence": gap_statements,
        "criteria": [{"key": k, "label": v[0], "weight": v[1]} for k, v in CRITERIA.items()],
        "area_languages": ctx["languages"],
    }
    if not target:
        return base | {
            "status": "needs_unclear",
            "message": "Choose a specific need. This area has no gap evidence in this sector to "
            "say which needs are most pressing, and solutions are not matched on sector alone.",
            "results": [],
            "excluded": [],
        }
    rows = [
        dict(r)
        for r in session.execute(
            text(
                SOLUTION_SELECT
                + " WHERE s.status = 'published' AND o.status = 'active' AND s.is_active "
                "ORDER BY s.name"
            )
        ).mappings()
    ]
    av = availability(session, area_id, [r["id"] for r in rows])
    results, excluded = [], []
    for sol in rows:
        if not set(sol["need_codes"]) & target:
            if sol["sector"] == sector:
                excluded.append(
                    {
                        "id": sol["id"],
                        "name": sol["name"],
                        "organisation_name": sol["organisation_name"],
                        "reason": "Same sector, but does not address the target needs.",
                    }
                )
            continue
        a = av.get(sol["id"])
        conn = c_connectivity(sol, ctx)
        crit = [
            c_relevance(sol, target, need_names),
            c_suitability(sol, target_groups or [], ctx),
            c_availability(a),
            c_affordability(sol, max_price_ngn),
            conn,
            c_language(sol, ctx),
            c_distribution(sol, ctx, conn),
            c_feasibility(sol, a, ctx),
        ]
        known = [c for c in crit if c.score is not None]
        w_known = sum(CRITERIA[c.key][1] for c in known)
        score = sum(CRITERIA[c.key][1] * c.score for c in known) / w_known
        quality = 1.0 if sol["verification_status"] in VERIFIED else 0.8
        confidence = w_known * quality
        strengths = [c.reason for c in sorted(known, key=lambda c: -c.score) if c.score >= 0.8][:3]
        cautions = [c.reason for c in crit if c.score is None or c.score < 0.5]
        results.append(
            {
                "solution": {
                    k: sol[k]
                    for k in (
                        "id",
                        "name",
                        "summary",
                        "organisation_id",
                        "organisation_name",
                        "sector",
                        "sector_name",
                        "need_codes",
                        "verification_status",
                        "website",
                    )
                },
                "availability": a,
                "score": round(score * 100, 1),
                "confidence": round(confidence, 2),
                "confidence_label": "high"
                if confidence >= 0.7
                else "medium"
                if confidence >= 0.45
                else "low",
                "criteria_known": len(known),
                "criteria": [c.out() for c in crit],
                "strengths": strengths,
                "cautions": cautions,
            }
        )
    results.sort(key=lambda r: (-r["score"] * (0.5 + 0.5 * r["confidence"]), r["solution"]["name"]))
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return base | {
        "status": "ok" if results else "no_matches",
        "message": None
        if results
        else "No published solution in the directory addresses these needs. The directory is "
        "curated; see the Directory page.",
        "results": results,
        "excluded": excluded,
    }
