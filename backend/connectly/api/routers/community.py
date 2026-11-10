"""Community intelligence: profiles, indicators, choropleth values, facilities, settlements."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.api.deps import get_session
from connectly.models import FACILITY_KINDS
from connectly.services.profiles import area_profile

router = APIRouter(prefix="/api/v1", tags=["community"])

AreaLevel = Literal["state", "lga", "ward"]
FacilityKind = Literal[FACILITY_KINDS]  # type: ignore[valid-type]
COL = {"state": "state_id", "lga": "lga_id", "ward": "ward_id"}


def _area_level(session: Session, area_id: int) -> str:
    level = session.scalar(
        text("SELECT level FROM admin_area WHERE id = :id AND active"), {"id": area_id}
    )
    if level is None:
        raise HTTPException(404, f"no active area with id {area_id}")
    return level


@router.get("/areas/{area_id}/profile")
def profile(area_id: int, session: Session = Depends(get_session)) -> dict:
    """Everything known about an area, each field with its provenance and value type."""
    p = area_profile(session, area_id)
    if p is None:
        raise HTTPException(404, f"no active area with id {area_id}")
    return p


@router.get("/indicators")
def indicators(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT i.code, i.name, i.unit, i.higher_is_worse, i.description, i.method,
                   s.code AS sector,
                   coalesce(jsonb_object_agg(c.geo_level, c.n) FILTER (WHERE c.geo_level IS NOT NULL),
                            '{}'::jsonb) AS values_by_level
            FROM indicator i
            LEFT JOIN sector s ON s.id = i.sector_id
            LEFT JOIN (SELECT indicator_id, geo_level, count(*) AS n FROM observation
                       GROUP BY 1, 2) c ON c.indicator_id = i.id
            GROUP BY i.id, s.code ORDER BY s.code NULLS FIRST, i.code
            """
        )
    ).mappings()
    return [dict(r) for r in rows]


@router.get("/choropleth")
def choropleth(
    indicator: str,
    level: AreaLevel,
    parent_id: int | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Latest value of one indicator for every area of `level` (optionally under a parent).

    Only values measured at that level are returned; areas without one are listed as
    missing rather than coloured with a parent's value.
    """
    ind = (
        session.execute(
            text("SELECT id, code, name, unit, higher_is_worse FROM indicator WHERE code = :c"),
            {"c": indicator},
        )
        .mappings()
        .first()
    )
    if ind is None:
        raise HTTPException(404, f"unknown indicator {indicator!r}")
    if level in ("lga", "ward") and parent_id is None:
        raise HTTPException(400, f"parent_id is required for level {level!r}")
    params = {"ind": ind["id"], "level": level, "parent": parent_id}
    parent_filter = "AND a.parent_id = :parent" if parent_id is not None else ""
    rows = session.execute(
        text(
            f"""
            SELECT a.id, a.name, o.value, o.lower_bound, o.upper_bound, o.period,
                   o.value_type, o.verification_status, d.key AS dataset
            FROM admin_area a
            LEFT JOIN LATERAL (
                SELECT * FROM observation o
                WHERE o.indicator_id = :ind AND o.geo_level = :level AND o.geo_id = a.id
                ORDER BY (o.verification_status IN ('source_verified','field_verified')) DESC,
                         o.period DESC, o.updated_at DESC
                LIMIT 1
            ) o ON true
            LEFT JOIN dataset d ON d.id = o.dataset_id
            WHERE a.level = :level AND a.active {parent_filter}
            ORDER BY a.name
            """
        ),
        params,
    ).mappings()
    rows = [dict(r) for r in rows]
    values = sorted(r["value"] for r in rows if r["value"] is not None)
    breaks = []
    if len(values) >= 5:
        breaks = [values[int(len(values) * q / 5)] for q in range(1, 5)]
    return {
        "indicator": dict(ind),
        "level": level,
        "values": [r for r in rows if r["value"] is not None],
        "missing": [{"id": r["id"], "name": r["name"]} for r in rows if r["value"] is None],
        "quintile_breaks": breaks,
    }


@router.get("/facilities")
def facilities(
    area_id: int,
    kind: FacilityKind | None = None,
    limit: int = Query(500, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> dict:
    level = _area_level(session, area_id)
    if level not in COL:
        raise HTTPException(400, "choose a state, LGA or ward")
    params = {"id": area_id, "kind": kind, "limit": limit}
    kind_filter = "AND f.kind = :kind" if kind else ""
    rows = session.execute(
        text(
            f"""
            SELECT f.id, f.kind, f.subtype, f.name, f.operational_status, f.ownership,
                   f.verification_status, ST_X(f.geom) AS lon, ST_Y(f.geom) AS lat,
                   d.key AS dataset, d.extra->>'attribution' AS attribution
            FROM facility f JOIN dataset d ON d.id = f.dataset_id
            WHERE f.{COL[level]} = :id {kind_filter}
            ORDER BY f.kind, f.name NULLS LAST LIMIT :limit
            """
        ),
        params,
    ).mappings()
    items = [dict(r) for r in rows]
    total = session.scalar(
        text(f"SELECT count(*) FROM facility f WHERE f.{COL[level]} = :id {kind_filter}"),
        params,
    )
    return {"total": total, "items": items}


@router.get("/geojson/points")
def points_geojson(
    area_id: int,
    layer: Literal["facilities", "settlements"] = "facilities",
    kind: FacilityKind | None = None,
    limit: int = Query(5000, ge=1, le=20000),
    session: Session = Depends(get_session),
) -> dict:
    """Facility or settlement points inside an area, for a map layer."""
    level = _area_level(session, area_id)
    if level not in COL:
        raise HTTPException(400, "choose a state, LGA or ward")
    if layer == "facilities":
        kind_filter = "AND f.kind = :kind" if kind else ""
        sql = f"""
            SELECT f.id, ST_AsGeoJSON(f.geom, 6) AS g, f.name, f.kind, f.subtype,
                   f.operational_status AS status, d.key AS dataset
            FROM facility f JOIN dataset d ON d.id = f.dataset_id
            WHERE f.{COL[level]} = :id {kind_filter} LIMIT :limit
        """
    else:
        sql = f"""
            SELECT s.id, ST_AsGeoJSON(s.point, 6) AS g, s.name, s.settlement_type AS kind,
                   NULL AS subtype, s.verification_status AS status, d.key AS dataset
            FROM settlement s LEFT JOIN dataset d ON d.id = s.dataset_id
            WHERE s.{COL[level]} = :id LIMIT :limit
        """
    rows = session.execute(text(sql), {"id": area_id, "kind": kind, "limit": limit}).mappings()
    feats = [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": json.loads(r["g"]),
            "properties": {k: r[k] for k in ("id", "name", "kind", "subtype", "status", "dataset")},
        }
        for r in rows
    ]
    attribution = (
        session.execute(
            text(
                "SELECT DISTINCT d.extra->>'attribution' FROM dataset d "
                "WHERE d.key = ANY(:keys) AND d.extra->>'attribution' IS NOT NULL"
            ),
            {
                "keys": list(
                    {f["properties"]["dataset"] for f in feats if f["properties"]["dataset"]}
                )
            },
        )
        .scalars()
        .all()
    )
    return {"type": "FeatureCollection", "features": feats, "attribution": list(attribution)}


@router.get("/settlements")
def settlements(
    area_id: int,
    q: str | None = Query(None, min_length=2),
    limit: int = Query(200, ge=1, le=2000),
    session: Session = Depends(get_session),
) -> dict:
    level = _area_level(session, area_id)
    if level not in COL:
        raise HTTPException(400, "choose a state, LGA or ward")
    params = {"id": area_id, "q": f"%{q}%" if q else None, "limit": limit}
    q_filter = "AND s.name ILIKE :q" if q else ""
    rows = session.execute(
        text(
            f"""
            SELECT s.id, s.name, s.settlement_type, s.verification_status,
                   ST_X(s.point) AS lon, ST_Y(s.point) AS lat, w.name AS ward, d.key AS dataset
            FROM settlement s LEFT JOIN admin_area w ON w.id = s.ward_id
            LEFT JOIN dataset d ON d.id = s.dataset_id
            WHERE s.{COL[level]} = :id {q_filter}
            ORDER BY s.name NULLS LAST LIMIT :limit
            """
        ),
        params,
    ).mappings()
    total = session.scalar(
        text(f"SELECT count(*) FROM settlement s WHERE s.{COL[level]} = :id {q_filter}"), params
    )
    return {"total": total, "items": [dict(r) for r in rows]}


@router.get("/settlements/{settlement_id}")
def settlement(settlement_id: int, session: Session = Depends(get_session)) -> dict:
    r = (
        session.execute(
            text(
                """
            SELECT s.id, s.name, s.source_name, s.settlement_type, s.verification_status,
                   s.source_note, ST_X(s.point) AS lon, ST_Y(s.point) AS lat, s.ward_id,
                   s.lga_id, s.state_id, s.updated_at, d.key AS dataset, d.title AS dataset_title,
                   d.licence, d.extra->>'attribution' AS attribution,
                   CASE WHEN s.extent IS NULL THEN NULL
                        ELSE ST_Area(s.extent::geography) / 1e6 END AS extent_km2
            FROM settlement s LEFT JOIN dataset d ON d.id = s.dataset_id WHERE s.id = :id
            """
            ),
            {"id": settlement_id},
        )
        .mappings()
        .first()
    )
    if r is None:
        raise HTTPException(404, f"no settlement {settlement_id}")
    nearest = session.execute(
        text(
            """
            SELECT DISTINCT ON (f.kind) f.kind, f.id, f.name, f.subtype,
                   ST_Distance(f.geom::geography, s.point::geography) / 1000.0 AS km,
                   d.key AS dataset
            FROM settlement s
            JOIN facility f ON ST_DWithin(f.geom::geography, s.point::geography, 50000)
            JOIN dataset d ON d.id = f.dataset_id
            WHERE s.id = :id
            ORDER BY f.kind, f.geom <-> s.point
            """
        ),
        {"id": settlement_id},
    ).mappings()
    from connectly.services.profiles import claims_for

    return dict(r) | {
        "nearest_facilities_within_50km": [dict(n) for n in nearest],
        "claims": claims_for(session, "settlement", settlement_id),
        "ward_profile_id": r["ward_id"],
    }
