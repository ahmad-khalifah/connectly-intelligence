"""Administrative hierarchy: browse, search and map geometry.

Only areas from the active dataset for each level are served.
"""

import json
from typing import Literal

import shapely
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
NATIONAL_TOLERANCE = 0.005  # for LGAs or wards drawn for the whole country

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


DESCENDANTS_SQL = (
    "WITH RECURSIVE d AS (SELECT id FROM admin_area WHERE id = :within_id "
    "UNION ALL SELECT c.id FROM admin_area c JOIN d ON c.parent_id = d.id) SELECT id FROM d"
)


# Simplifying each area on its own moves a shared border differently on each side, which
# draws neighbours overlapping (and leaves gaps) on the map. All returned areas are
# simplified together as one coverage instead, so each shared border stays identical.
# Done with Shapely (bundled GEOS >= 3.12) so it works on any PostGIS version.
COORD_PRECISION = 1e-5  # ~1 m; applied to every vertex identically


def simplify_coverage(geoms: list, tolerance: float) -> list:
    if tolerance > 0 and geoms:
        geoms = list(shapely.coverage_simplify(geoms, tolerance))
    return [shapely.set_precision(g, COORD_PRECISION) for g in geoms]


def _features(session: Session, where: str, params: dict, tolerance: float) -> list[dict]:
    rows = (
        session.execute(
            text(
                f"""
            SELECT a.id, a.level, a.name, a.parent_id, a.area_km2,
                   ST_AsBinary(a.geom) AS wkb
            FROM admin_area a
            WHERE a.active AND {where}
            ORDER BY a.name
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    shapes = simplify_coverage([shapely.from_wkb(bytes(r["wkb"])) for r in rows], tolerance)
    return [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": None if g.is_empty else json.loads(shapely.to_geojson(g)),
            "properties": {
                "id": r["id"],
                "level": r["level"],
                "name": r["name"],
                "parent_id": r["parent_id"],
                "area_km2": round(r["area_km2"], 1) if r["area_km2"] is not None else None,
            },
        }
        for r, g in zip(rows, shapes, strict=True)
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
    within_id: int | None = Query(None, description="Any ancestor, e.g. a state for its wards"),
    tolerance: float | None = Query(None, ge=0, le=0.1),
    session: Session = Depends(get_session),
):
    """Simplified boundaries for a map layer: all areas of `level`, optionally under one parent
    (`parent_id`) or anywhere inside one larger area (`within_id`)."""
    where = "a.level = :level"
    params: dict = {"level": level}
    if parent_id is not None:
        where += " AND a.parent_id = :parent_id"
        params["parent_id"] = parent_id
    elif within_id is not None:
        where += f" AND a.id IN ({DESCENDANTS_SQL})"
        params["within_id"] = within_id
    elif level in ("lga", "ward"):
        raise HTTPException(400, f"parent_id or within_id is required for level {level!r}")
    tol = DEFAULT_TOLERANCE[level] if tolerance is None else tolerance
    if tolerance is None and within_id is not None:
        # A whole-country map of small areas is drawn at national zoom, where ~0.5 km of
        # detail is invisible; coarser simplification keeps the payload small.
        within_level = session.scalar(
            text("SELECT level FROM admin_area WHERE id = :i"), {"i": within_id}
        )
        if within_level == "country":
            tol = max(tol, NATIONAL_TOLERANCE)
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
