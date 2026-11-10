"""Community profiles: everything known about a place, field by field, with provenance.

A profile never fills a gap. Each field is either a sourced value (with dataset, period,
value type and verification status) or an explicit "not available" with the reason.
Values measured at a larger area (e.g. a state survey) are shown as context for the
smaller area, labelled with the level they were measured at; they are never presented as
the smaller area's own value.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.models import CLAIM_ATTRIBUTES

LEVEL_ORDER = ("ward", "lga", "state", "country")

LATEST_SQL = text(
    """
    SELECT DISTINCT ON (o.indicator_id, o.geo_level, o.geo_id)
           i.code, i.name AS indicator_name, i.unit, i.higher_is_worse, s.code AS sector,
           o.geo_level, o.geo_id, o.period, o.value, o.value_text, o.lower_bound,
           o.upper_bound, o.interval_note, o.value_type, o.verification_status,
           o.source_reference, o.note, o.updated_at,
           d.key AS dataset_key, d.title AS dataset_title, d.licence,
           d.extra->>'attribution' AS attribution
    FROM observation o
    JOIN indicator i ON i.id = o.indicator_id
    LEFT JOIN sector s ON s.id = i.sector_id
    JOIN dataset d ON d.id = o.dataset_id
    WHERE (o.geo_level, o.geo_id) IN (SELECT * FROM unnest(CAST(:levels AS text[]), CAST(:ids AS int[])))
    ORDER BY o.indicator_id, o.geo_level, o.geo_id,
             -- prefer verified, then measured over derived/modelled, then the newest period
             (o.verification_status IN ('source_verified', 'field_verified')) DESC,
             o.period DESC, o.updated_at DESC
    """
)


def ancestors(session: Session, area_id: int) -> list[dict]:
    """The area and its ancestors, smallest first."""
    return [
        dict(r)
        for r in session.execute(
            text(
                """
                WITH RECURSIVE chain AS (
                  SELECT id, level, name, parent_id, 0 AS depth FROM admin_area WHERE id = :id
                  UNION ALL
                  SELECT p.id, p.level, p.name, p.parent_id, c.depth + 1
                  FROM admin_area p JOIN chain c ON p.id = c.parent_id
                )
                SELECT id, level, name FROM chain ORDER BY depth
                """
            ),
            {"id": area_id},
        ).mappings()
    ]


def observations_for(session: Session, chain: list[dict]) -> list[dict]:
    if not chain:
        return []
    rows = session.execute(
        LATEST_SQL,
        {"levels": [a["level"] for a in chain], "ids": [a["id"] for a in chain]},
    ).mappings()
    return [dict(r) for r in rows]


def _value_out(r: dict, own_level: str, chain_names: dict[tuple[str, int], str]) -> dict:
    return {
        "indicator": r["code"],
        "name": r["indicator_name"],
        "unit": r["unit"],
        "sector": r["sector"],
        "value": r["value"],
        "value_text": r["value_text"],
        "lower_bound": r["lower_bound"],
        "upper_bound": r["upper_bound"],
        "interval_note": r["interval_note"],
        "period": r["period"],
        "value_type": r["value_type"],
        "verification_status": r["verification_status"],
        "measured_at_level": r["geo_level"],
        "measured_at_area": chain_names.get((r["geo_level"], r["geo_id"])),
        "is_context": r["geo_level"] != own_level,
        "higher_is_worse": r["higher_is_worse"],
        "dataset": r["dataset_key"],
        "dataset_title": r["dataset_title"],
        "licence": r["licence"],
        "attribution": r["attribution"],
        "source_reference": r["source_reference"],
        "note": r["note"],
        "updated_at": r["updated_at"],
    }


def facility_summary(session: Session, level: str, area_id: int) -> list[dict]:
    col = {"state": "state_id", "lga": "lga_id", "ward": "ward_id"}.get(level)
    if col is None:
        return []
    rows = session.execute(
        text(
            f"""
            SELECT f.kind, count(*) AS total,
                   count(*) FILTER (WHERE f.operational_status IS NOT NULL) AS with_status,
                   array_agg(DISTINCT d.key) AS datasets
            FROM facility f JOIN dataset d ON d.id = f.dataset_id
            WHERE f.{col} = :id GROUP BY f.kind ORDER BY f.kind
            """
        ),
        {"id": area_id},
    ).mappings()
    return [dict(r) for r in rows]


def facility_coverage(session: Session, state_id: int | None) -> dict[str, list[str]]:
    """Facility kinds → datasets whose coverage includes this state."""
    if state_id is None:
        return {}
    rows = session.execute(
        text(
            """
            SELECT DISTINCT f.kind, d.key, d.extra->'coverage_state_ids' AS cov
            FROM facility f JOIN dataset d ON d.id = f.dataset_id
            """
        )
    ).all()
    out: dict[str, list[str]] = {}
    for kind, key, cov in rows:
        if cov is None or state_id in (cov or []):
            out.setdefault(kind, []).append(key)
    return out


def claims_for(session: Session, subject_type: str, subject_id: int) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT c.id, c.subject_type, c.subject_id, c.attribute, c.value_text, c.value_codes,
                   c.value_type, c.source_description, c.source_url, c.observed_on,
                   c.verification_status, c.verification_note, c.verified_at, c.is_active,
                   c.created_by_id, cu.full_name AS created_by, vu.full_name AS verified_by,
                   c.created_at, c.updated_at
            FROM claim c
            LEFT JOIN app_user cu ON cu.id = c.created_by_id
            LEFT JOIN app_user vu ON vu.id = c.verified_by_id
            WHERE c.subject_type = :t AND c.subject_id = :i AND c.is_active
            ORDER BY c.attribute, c.updated_at DESC
            """
        ),
        {"t": subject_type, "i": subject_id},
    ).mappings()
    return [dict(r) | {"attribute_label": CLAIM_ATTRIBUTES.get(r["attribute"])} for r in rows]


def area_profile(session: Session, area_id: int) -> dict[str, Any] | None:
    area = (
        session.execute(
            text(
                """
            SELECT a.id, a.level, a.name, a.area_km2, a.updated_at, a.dataset_id,
                   ST_X(ST_PointOnSurface(a.geom)) AS lon, ST_Y(ST_PointOnSurface(a.geom)) AS lat
            FROM admin_area a WHERE a.id = :id AND a.active
            """
            ),
            {"id": area_id},
        )
        .mappings()
        .first()
    )
    if area is None:
        return None
    chain = ancestors(session, area_id)
    names = {(a["level"], a["id"]): a["name"] for a in chain}
    by_level = {a["level"]: a for a in chain}
    obs = observations_for(session, chain)
    own = [_value_out(r, area["level"], names) for r in obs if r["geo_level"] == area["level"]]
    context = [_value_out(r, area["level"], names) for r in obs if r["geo_level"] != area["level"]]

    sectors = (
        session.execute(text("SELECT code, name, is_priority FROM sector ORDER BY sort_order"))
        .mappings()
        .all()
    )
    defined = (
        session.execute(
            text(
                "SELECT i.code, i.name, s.code AS sector FROM indicator i "
                "LEFT JOIN sector s ON s.id = i.sector_id"
            )
        )
        .mappings()
        .all()
    )
    have = {v["indicator"] for v in own} | {v["indicator"] for v in context}
    missing = [dict(d) for d in defined if d["code"] not in have]

    state_id = by_level.get("state", {}).get("id")
    gaps = (
        session.execute(
            text(
                """
            SELECT g.code, g.title, g.description, s.code AS sector, g.needs_field_verification
            FROM data_gap g LEFT JOIN sector s ON s.id = g.sector_id
            WHERE g.status <> 'resolved' ORDER BY g.code
            """
            )
        )
        .mappings()
        .all()
    )
    settlements = None
    if area["level"] in ("ward", "lga", "state"):
        col = {"ward": "ward_id", "lga": "lga_id", "state": "state_id"}[area["level"]]
        settlements = session.scalar(
            text(f"SELECT count(*) FROM settlement WHERE {col} = :id"), {"id": area_id}
        )
    pop = next((v for v in own if v["indicator"] == "population.modelled_total"), None)
    urban = next((v for v in own if v["indicator"] == "geo.urban_flag"), None)
    last_updated = max(
        [area["updated_at"]] + [v["updated_at"] for v in own if v["updated_at"]], default=None
    )
    return {
        "id": area["id"],
        "level": area["level"],
        "name": area["name"],
        "state": by_level.get("state", {}).get("name"),
        "lga": by_level.get("lga", {}).get("name"),
        "coordinates": {"lon": area["lon"], "lat": area["lat"], "kind": "point inside area"},
        "area_km2": area["area_km2"],
        "population": pop,
        "urban_classification": urban,
        "indicators": own,
        "context_indicators": context,
        "missing_indicators": missing,
        "facilities": facility_summary(session, area["level"], area_id),
        "facility_coverage": facility_coverage(session, state_id),
        "settlement_count": settlements,
        "claims": claims_for(session, "admin_area", area_id),
        "data_gaps": [dict(g) for g in gaps],
        "sectors": [dict(s) for s in sectors],
        "last_updated": last_updated,
    }
