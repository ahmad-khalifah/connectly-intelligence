"""Needs assessment: how underserved each area is in a sector, relative to comparable areas.

Method (docs/methodology.md):

1. Scope: all areas of one level inside one larger area (e.g. the wards of Adamawa).
2. For each indicator in the sector's model, rank the areas in scope that have a value
   measured at that level. Values from larger areas are not used to rank smaller ones, since
   they are identical across the scope. Percentile 100 = most underserved in scope.
3. Gap score = weighted mean of the available percentiles (0-100).
4. Coverage = share of the model's weight available for the area. Confidence = coverage x
   weighted quality of the values used (value type and verification).
5. Below MIN_COVERAGE, no score is given; the result says which data is missing.

Scores are relative: a high score means "worse than most comparable areas on the evidence
loaded", not an absolute level of need.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.taxonomy.need_models import (
    MIN_AREAS_TO_RANK,
    MIN_COVERAGE,
    NEED_MODELS,
    VALUE_TYPE_QUALITY,
    VERIFICATION_QUALITY,
)

SCOPE_AREAS_SQL = """
    WITH RECURSIVE d AS (
        SELECT id, level FROM admin_area WHERE id = :scope
        UNION ALL SELECT c.id, c.level FROM admin_area c JOIN d ON c.parent_id = d.id
        WHERE d.level <> :level
    )
    SELECT a.id, a.name, a.parent_id, p.name AS parent_name
    FROM admin_area a JOIN d ON d.id = a.id
    LEFT JOIN admin_area p ON p.id = a.parent_id
    WHERE a.level = :level AND a.active
"""

VALUES_SQL = """
    SELECT DISTINCT ON (o.geo_id, i.code) o.geo_id, i.code, o.value, o.value_type,
           o.verification_status, o.period, d.key AS dataset
    FROM observation o JOIN indicator i ON i.id = o.indicator_id
    JOIN dataset d ON d.id = o.dataset_id
    WHERE o.geo_level = :level AND o.geo_id = ANY(:ids) AND i.code = ANY(:codes)
      AND o.value IS NOT NULL AND o.verification_status <> 'retired'
    ORDER BY o.geo_id, i.code,
             (o.verification_status IN ('source_verified', 'field_verified')) DESC,
             o.period DESC, o.updated_at DESC
"""

POP_SQL = """
    SELECT DISTINCT ON (o.geo_id) o.geo_id, o.value FROM observation o
    JOIN indicator i ON i.id = o.indicator_id
    WHERE i.code = 'population.modelled_total' AND o.geo_level = :level AND o.geo_id = ANY(:ids)
    ORDER BY o.geo_id, o.period DESC
"""


class NeedsError(ValueError):
    pass


def models(session: Session) -> list[dict]:
    rows = session.execute(
        text(
            "SELECT s.code AS sector, s.name AS sector_name, i.code, i.name, i.unit, "
            "i.higher_is_worse FROM indicator i JOIN sector s ON s.id = i.sector_id"
        )
    ).mappings()
    meta = {r["code"]: dict(r) for r in rows}
    sectors = session.execute(text("SELECT code, name FROM sector ORDER BY sort_order")).all()
    out = []
    for code, name in sectors:
        spec = NEED_MODELS.get(code, [])
        out.append(
            {
                "sector": code,
                "sector_name": name,
                "indicators": [
                    {
                        "code": c,
                        "weight": w,
                        "name": meta.get(c, {}).get("name", c),
                        "unit": meta.get(c, {}).get("unit"),
                        "higher_is_worse": meta.get(c, {}).get("higher_is_worse"),
                    }
                    for c, w in spec
                ],
                "has_model": bool(spec),
            }
        )
    return out


def _percentiles(values: dict[int, float], higher_is_worse: bool) -> dict[int, float]:
    """Deprivation percentile per area: 100 = most underserved; ties share the average rank."""
    n = len(values)
    if n == 1:
        return dict.fromkeys(values, 50.0)
    ordered = sorted(values.items(), key=lambda kv: kv[1] if higher_is_worse else -kv[1])
    out: dict[int, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        pct = ((i + j) / 2) / (n - 1) * 100
        for k in range(i, j + 1):
            out[ordered[k][0]] = pct
        i = j + 1
    return out


def _confidence_label(c: float) -> str:
    return "high" if c >= 0.6 else "medium" if c >= 0.35 else "low"


def _statement(comp: dict, scope_label: str, level_plural: str) -> str:
    worse = round(comp["percentile"])
    direction = "higher" if comp["higher_is_worse"] else "lower"
    return (
        f"{comp['name']}: {comp['value']:g} {comp['unit'] or ''}".rstrip()
        + f" ({direction} is worse); worse than {worse}% of {level_plural} in {scope_label} "
        f"with data (median {comp['scope_median']:g})."
    )


def assess(session: Session, sector: str, level: str, scope_id: int) -> dict[str, Any]:
    scope = (
        session.execute(
            text("SELECT id, name, level FROM admin_area WHERE id = :id AND active"),
            {"id": scope_id},
        )
        .mappings()
        .first()
    )
    if scope is None:
        raise NeedsError(f"no active area {scope_id}")
    order = ["country", "state", "lga", "ward"]
    if order.index(level) <= order.index(scope["level"]):
        raise NeedsError(f"{level} areas cannot be compared inside a {scope['level']}")
    model_list = {m["sector"]: m for m in models(session)}
    if sector not in model_list:
        raise NeedsError(f"unknown sector {sector!r}")
    model = model_list[sector]
    areas = [
        dict(r)
        for r in session.execute(
            text(SCOPE_AREAS_SQL), {"scope": scope_id, "level": level}
        ).mappings()
    ]
    ids = [a["id"] for a in areas]
    level_plural = {"state": "states", "lga": "LGAs", "ward": "wards"}[level]
    level_name = {"state": "state", "lga": "LGA", "ward": "ward"}[level]
    base = {
        "sector": sector,
        "sector_name": model["sector_name"],
        "level": level,
        "scope": dict(scope),
        "model": model["indicators"],
        "method": "relative; see docs/methodology.md",
    }
    if not model["has_model"]:
        return base | {
            "status": "no_model",
            "message": f"No open indicator for {model['sector_name'].lower()} is loaded, so "
            "access gaps in this sector cannot be scored. See the data gaps.",
            "areas": [],
            "indicators": [],
        }
    codes = [i["code"] for i in model["indicators"]]
    by_ind: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in session.execute(
        text(VALUES_SQL), {"level": level, "ids": ids, "codes": codes}
    ).mappings():
        by_ind[r["code"]][r["geo_id"]] = dict(r)
    pops = dict(session.execute(text(POP_SQL), {"level": level, "ids": ids}).all())

    coarser = dict(
        session.execute(
            text(
                "SELECT i.code, string_agg(DISTINCT o.geo_level, ', ') FROM observation o "
                "JOIN indicator i ON i.id = o.indicator_id WHERE i.code = ANY(:codes) "
                "AND o.geo_level <> :level GROUP BY i.code"
            ),
            {"codes": codes, "level": level},
        ).all()
    )
    indicators, pct, medians = [], {}, {}
    for ind in model["indicators"]:
        vals = {gid: r["value"] for gid, r in by_ind[ind["code"]].items()}
        usable = len(vals) >= MIN_AREAS_TO_RANK and ind["higher_is_worse"] is not None
        reason = None
        if not vals and ind["code"] in coarser:
            reason = (
                f"measured only at {coarser[ind['code']].replace('lga', 'LGA')} level; one value covers many "
                f"{level_plural}, so it cannot tell them apart (shown as context on profiles)"
            )
        elif not vals:
            reason = f"no values at {level_name} level in this scope"
        elif len(vals) < MIN_AREAS_TO_RANK:
            reason = f"only {len(vals)} {level_plural} have a value; too few to compare"
        if usable:
            pct[ind["code"]] = _percentiles(vals, ind["higher_is_worse"])
            medians[ind["code"]] = median(vals.values())
        indicators.append(ind | {"areas_with_value": len(vals), "used": usable, "reason": reason})

    total_w = sum(i["weight"] for i in model["indicators"])
    results = []
    for a in areas:
        comps, missing, wsum, qsum, ssum = [], [], 0.0, 0.0, 0.0
        for ind in model["indicators"]:
            c = ind["code"]
            row = by_ind[c].get(a["id"])
            if c in pct and row is not None:
                q = VALUE_TYPE_QUALITY.get(row["value_type"], 0.5) * VERIFICATION_QUALITY.get(
                    row["verification_status"], 0.9
                )
                comp = {
                    "indicator": c,
                    "name": ind["name"],
                    "unit": ind["unit"],
                    "higher_is_worse": ind["higher_is_worse"],
                    "weight": ind["weight"],
                    "value": row["value"],
                    "percentile": round(pct[c][a["id"]], 1),
                    "scope_median": medians[c],
                    "value_type": row["value_type"],
                    "verification_status": row["verification_status"],
                    "period": row["period"],
                    "dataset": row["dataset"],
                }
                comp["statement"] = _statement(comp, scope["name"], level_plural)
                comps.append(comp)
                wsum += ind["weight"]
                ssum += ind["weight"] * comp["percentile"]
                qsum += ind["weight"] * q
            else:
                missing.append(
                    {
                        "indicator": c,
                        "name": ind["name"],
                        "weight": ind["weight"],
                        "reason": "no value for this area"
                        if c in pct
                        else next(i["reason"] for i in indicators if i["code"] == c),
                    }
                )
        coverage = wsum / total_w if total_w else 0.0
        enough = coverage >= MIN_COVERAGE and comps
        quality = qsum / wsum if wsum else 0.0
        confidence = coverage * quality
        comps.sort(key=lambda x: -x["percentile"] * x["weight"])
        results.append(
            {
                "id": a["id"],
                "name": a["name"],
                "parent_name": a["parent_name"],
                "population": pops.get(a["id"]),
                "score": round(ssum / wsum, 1) if enough else None,
                "coverage": round(coverage, 2),
                "confidence": round(confidence, 2) if enough else None,
                "confidence_label": _confidence_label(confidence) if enough else "insufficient",
                "components": comps,
                "missing": missing,
            }
        )
    scored = sorted(
        (r for r in results if r["score"] is not None), key=lambda r: (-r["score"], r["name"])
    )
    for rank, r in enumerate(scored, 1):
        r["rank"] = rank
    unscored = sorted((r for r in results if r["score"] is None), key=lambda r: r["name"])
    for r in unscored:
        r["rank"] = None
    status = "ok" if scored else "insufficient"
    return base | {
        "status": status,
        "message": None
        if scored
        else "Not enough data is loaded to compare these areas in this sector. The indicators "
        "below show what is missing.",
        "indicators": indicators,
        "areas_in_scope": len(areas),
        "areas_scored": len(scored),
        "areas": scored + unscored,
    }


def area_summary(session: Session, area_id: int) -> dict[str, Any]:
    """Gap scores for one area in every sector, compared with its siblings in the same state
    (states are compared with all states)."""
    a = (
        session.execute(
            text(
                """
            WITH RECURSIVE up AS (
              SELECT id, level, parent_id FROM admin_area WHERE id = :id
              UNION ALL SELECT p.id, p.level, p.parent_id FROM admin_area p JOIN up ON p.id = up.parent_id)
            SELECT (SELECT level FROM up WHERE id = :id) AS level,
                   (SELECT id FROM up WHERE level = 'state') AS state_id,
                   (SELECT id FROM up WHERE level = 'country') AS country_id
            """
            ),
            {"id": area_id},
        )
        .mappings()
        .first()
    )
    if a is None or a["level"] is None:
        raise NeedsError(f"no area {area_id}")
    if a["level"] == "country":
        raise NeedsError("the country has nothing to be compared with")
    scope = a["country_id"] if a["level"] == "state" else a["state_id"]
    out = []
    for m in models(session):
        res = assess(session, m["sector"], a["level"], scope)
        mine = next((r for r in res["areas"] if r["id"] == area_id), None)
        out.append(
            {
                "sector": m["sector"],
                "sector_name": m["sector_name"],
                "status": res["status"],
                "scope": res["scope"],
                "areas_scored": res.get("areas_scored", 0),
                "result": mine,
                "message": res["message"],
            }
        )
    return {"area_id": area_id, "level": a["level"], "sectors": out}
