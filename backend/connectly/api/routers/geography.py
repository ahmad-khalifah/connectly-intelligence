"""Administrative hierarchy: browse, search and map geometry.

Only areas from the active dataset for each level are served.
"""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.api import schemas
from connectly.api.deps import get_session
from connectly.ingest.boundaries import CHILD_LEVEL
from connectly.models import ADMIN_LEVELS

router = APIRouter(prefix="/api/v1", tags=["geography"])

Level = Literal["country", "state", "lga", "ward"]

# Default simplification per level, in degrees (~0.001° ≈ 110 m). Detail views can
# ask for full resolution with tolerance=0.
DEFAULT_TOLERANCE = {"country": 0.01, "state": 0.003, "lga": 0.001, "ward": 0.0003}

# Recorded data gaps to show when an area has no children loaded yet.
MISSING_CHILDREN_GAP = {"ward": "geo.wards_not_loaded"}

CHILD_COUNT_SQL = """
    (SELECT count(*) FROM admin_area ch WHERE ch.parent_id = a.id AND ch.active)
"""


@router.get("/areas", response_model=list[schemas.AreaSummary])
def list_areas(
    level: Level | None = None,
    parent_id: int | None = None,
    q: str | None = Query(None, min_length=2, description="Name or alias contains"),
    limit: int = Query(200, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    where = ["a.active"]
    params: dict = {"limit": limit}
    if level:
        where.append("a.level = :level")
        params["level"] = level
    if parent_id is not None:
        where.append("a.parent_id = :parent_id")
        params["parent_id"] = parent_id
    if q:
        where.append(
            "(a.name ILIKE :q OR EXISTS (SELECT 1 FROM place_alias p "
            "WHERE p.admin_area_id = a.id AND p.alias ILIKE :q))"
        )
        params["q"] = f"%{q}%"
    rows = session.execute(
        text(
            f"""
            SELECT a.id, a.level, a.name, a.parent_id, a.area_km2,
                   {CHILD_COUNT_SQL} AS child_count
            FROM admin_area a
            WHERE {" AND ".join(where)}
            ORDER BY array_position(:levels, a.level::text), a.name
            LIMIT :limit
            """
        ),
        params | {"levels": list(ADMIN_LEVELS)},
    ).mappings()
    return [schemas.AreaSummary(**r) for r in rows]


def _area_or_404(session: Session, area_id: int):
    row = (
        session.execute(
            text(
                f"""
            SELECT a.id, a.level, a.name, a.source_name, a.source_code, a.area_km2,
                   a.parent_method, a.parent_overlap, a.active,
                   ST_X(ST_PointOnSurface(a.geom)) AS lon, ST_Y(ST_PointOnSurface(a.geom)) AS lat,
                   ST_XMin(a.geom) AS x0, ST_YMin(a.geom) AS y0,
                   ST_XMax(a.geom) AS x1, ST_YMax(a.geom) AS y1,
                   {CHILD_COUNT_SQL} AS child_count,
                   d.key AS d_key, d.title AS d_title, d.version AS d_version,
                   d.distributor AS d_distributor, d.licence AS d_licence,
                   d.licence_verified AS d_licence_verified,
                   d.extra->>'attribution' AS d_attribution, s.name AS d_source_name
            FROM admin_area a
            JOIN dataset d ON d.id = a.dataset_id
            JOIN source s ON s.id = d.source_id
            WHERE a.id = :id
            """
            ),
            {"id": area_id},
        )
        .mappings()
        .first()
    )
    if row is None or not row["active"]:
        raise HTTPException(404, f"no active area with id {area_id}")
    return row


@router.get("/areas/{area_id}", response_model=schemas.AreaDetail)
def get_area(area_id: int, session: Session = Depends(get_session)):
    row = _area_or_404(session, area_id)
    crumbs = session.execute(
        text(
            """
            WITH RECURSIVE chain AS (
              SELECT id, level, name, parent_id, 0 AS depth FROM admin_area WHERE id = :id
              UNION ALL
              SELECT p.id, p.level, p.name, p.parent_id, c.depth + 1
              FROM admin_area p JOIN chain c ON p.id = c.parent_id
            )
            SELECT id, level, name FROM chain ORDER BY depth DESC
            """
        ),
        {"id": area_id},
    ).mappings()
    aliases = (
        session.execute(
            text("SELECT alias FROM place_alias WHERE admin_area_id = :id ORDER BY alias"),
            {"id": area_id},
        )
        .scalars()
        .all()
    )

    child_level = CHILD_LEVEL.get(row["level"])
    notices: list[schemas.Notice] = []
    if child_level and row["child_count"] == 0:
        gap_code = MISSING_CHILDREN_GAP.get(child_level)
        gap = (
            session.execute(
                text("SELECT code, title, description FROM data_gap WHERE code = :c"),
                {"c": gap_code},
            )
            .mappings()
            .first()
            if gap_code
            else None
        )
        if gap:
            notices.append(schemas.Notice(**gap))
        else:
            notices.append(
                schemas.Notice(
                    code="geo.children_not_loaded",
                    title=f"No {child_level} boundaries loaded for this area",
                    description=f"No {child_level} dataset covering this area is loaded.",
                )
            )
    has_settlements = row["level"] in ("lga", "ward") and session.scalar(
        text(f"SELECT EXISTS (SELECT 1 FROM settlement WHERE {row['level']}_id = :id)"),
        {"id": area_id},
    )
    if row["level"] in ("lga", "ward") and not has_settlements:
        gap = (
            session.execute(
                text(
                    "SELECT code, title, description FROM data_gap WHERE code = :c "
                    "AND status <> 'resolved'"
                ),
                {"c": "geo.settlements_not_loaded"},
            )
            .mappings()
            .first()
        )
        if gap:
            notices.append(schemas.Notice(**gap))

    return schemas.AreaDetail(
        id=row["id"],
        level=row["level"],
        name=row["name"],
        source_name=row["source_name"],
        source_code=row["source_code"],
        area_km2=row["area_km2"],
        centroid=(row["lon"], row["lat"]),
        bbox=(row["x0"], row["y0"], row["x1"], row["y1"]),
        breadcrumbs=[schemas.AreaRef(**c) for c in crumbs],
        child_level=child_level,
        child_count=row["child_count"],
        aliases=list(aliases),
        parent_method=row["parent_method"],
        parent_overlap=row["parent_overlap"],
        dataset=schemas.DatasetRef(
            key=row["d_key"],
            title=row["d_title"],
            version=row["d_version"],
            source_name=row["d_source_name"],
            distributor=row["d_distributor"],
            licence=row["d_licence"],
            licence_verified=row["d_licence_verified"],
            attribution=row["d_attribution"],
        ),
        notices=notices,
    )


@router.get("/areas/{area_id}/children", response_model=list[schemas.AreaSummary])
def get_children(area_id: int, session: Session = Depends(get_session)):
    _area_or_404(session, area_id)
    return list_areas(level=None, parent_id=area_id, q=None, limit=1000, session=session)


def _features(session: Session, where: str, params: dict, tolerance: float) -> list[dict]:
    rows = session.execute(
        text(
            f"""
            SELECT a.id, a.level, a.name, a.parent_id, a.area_km2,
                   ST_AsGeoJSON(
                     CASE WHEN :tol > 0 THEN ST_SimplifyPreserveTopology(a.geom, :tol)
                          ELSE a.geom END, 5) AS geometry
            FROM admin_area a
            WHERE a.active AND {where}
            ORDER BY a.name
            """
        ),
        params | {"tol": tolerance},
    ).mappings()
    return [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": json.loads(r["geometry"]),
            "properties": {
                "id": r["id"],
                "level": r["level"],
                "name": r["name"],
                "parent_id": r["parent_id"],
                "area_km2": round(r["area_km2"], 1) if r["area_km2"] is not None else None,
            },
        }
        for r in rows
    ]


def _attributions(session: Session, where: str, params: dict) -> list[str]:
    return list(
        session.execute(
            text(
                f"""
                SELECT DISTINCT d.extra->>'attribution'
                FROM admin_area a JOIN dataset d ON d.id = a.dataset_id
                WHERE a.active AND {where} AND d.extra->>'attribution' IS NOT NULL
                """
            ),
            params,
        ).scalars()
    )


@router.get("/geojson", response_model=schemas.FeatureCollection)
def geojson(
    level: Level,
    parent_id: int | None = None,
    tolerance: float | None = Query(None, ge=0, le=0.1),
    session: Session = Depends(get_session),
):
    """Simplified boundaries for a map layer: all areas of `level`, optionally under one parent."""
    where = "a.level = :level"
    params: dict = {"level": level}
    if parent_id is not None:
        where += " AND a.parent_id = :parent_id"
        params["parent_id"] = parent_id
    elif level in ("lga", "ward"):
        raise HTTPException(400, f"parent_id is required for level {level!r}")
    tol = DEFAULT_TOLERANCE[level] if tolerance is None else tolerance
    return schemas.FeatureCollection(
        features=_features(session, where, params, tol),
        simplified_tolerance_deg=tol,
        attribution=_attributions(session, where, params),
    )


@router.get("/areas/{area_id}/geojson", response_model=schemas.FeatureCollection)
def area_geojson(
    area_id: int,
    tolerance: float | None = Query(None, ge=0, le=0.1),
    session: Session = Depends(get_session),
):
    row = _area_or_404(session, area_id)
    tol = DEFAULT_TOLERANCE[row["level"]] if tolerance is None else tolerance
    where, params = "a.id = :id", {"id": area_id}
    return schemas.FeatureCollection(
        features=_features(session, where, params, tol),
        simplified_tolerance_deg=tol,
        attribution=_attributions(session, where, params),
    )
