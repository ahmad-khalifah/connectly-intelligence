"""Load administrative boundaries into `admin_area` with full provenance.

Pipeline: read file → check CRS and extent → map fields → repair geometry → reject bad
rows → (optionally) keep only areas inside one state → upsert with stable IDs →
activate → assign parents by spatial overlap → run post-load checks.

Every run is recorded in `ingest_run`, including rejected rows and warnings.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from connectly.ingest.fetch import RetrievedFile, default_file_for, describe_local_file
from connectly.ingest.manifest import Manifest
from connectly.models import PARENT_LEVEL, AdminArea, Dataset, IngestRun, PlaceAlias, Source

# Generous bounding box around Nigeria (lon/lat). Data outside it almost always means a
# wrong or missing coordinate reference system.
NIGERIA_BBOX = (2.0, 3.5, 15.5, 14.5)
CHILD_LEVEL = {parent: child for child, parent in PARENT_LEVEL.items()}
LOW_OVERLAP = 0.95


class LoadError(RuntimeError):
    pass


class FileNotProvidedError(LoadError):
    """The dataset has not been downloaded yet. Nothing was attempted, so not a failure."""


@dataclass
class LoadReport:
    dataset_key: str
    status: str
    run_id: int | None = None
    rows_read: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    rows_out_of_scope: int = 0
    active: bool = False
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- reading


def _pick_column(columns: list[str], candidates: list[str], what: str) -> str:
    for c in candidates:
        if c in columns:
            return c
    lower = {c.lower(): c for c in columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    raise LoadError(
        f"none of the expected {what} columns {candidates} exist in the file. "
        f"Columns found: {columns}. Update `fields.{what}` in the manifest."
    )


def clean_name(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def _clean_code(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    return s or None


def repair_polygonal(geom: BaseGeometry | None) -> tuple[MultiPolygon | None, bool]:
    """Return (MultiPolygon or None, was_repaired)."""
    # GeoPandas returns a NaN float, not None, for features with a null geometry.
    if not isinstance(geom, BaseGeometry) or geom.is_empty:
        return None, False
    repaired = False
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
        repaired = True
    polys: list[Polygon] = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            if isinstance(part, Polygon):
                polys.append(part)
            elif isinstance(part, MultiPolygon):
                polys.extend(part.geoms)
        repaired = True
    polys = [p for p in polys if not p.is_empty and p.area > 0]
    if not polys:
        return None, repaired
    # Drop any Z coordinate; the database stores 2D geometry.
    mp = shapely.force_2d(MultiPolygon(polys))
    return mp, repaired


def _json_safe(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    return str(v)


def prepare_features(
    path: Path,
    manifest: Manifest,
    within: BaseGeometry | None = None,
) -> tuple[list[dict], LoadReport]:
    report = LoadReport(dataset_key=manifest.key, status="running")
    try:
        gdf = gpd.read_file(path)
    except Exception as e:  # noqa: BLE001 - surface any reader error clearly
        raise LoadError(f"could not read {path}: {e}") from e
    report.rows_read = len(gdf)
    if gdf.empty:
        raise LoadError(f"{path} contains no features")

    if gdf.crs is None:
        raise LoadError(
            f"{path} has no coordinate reference system. Re-export it with one (EPSG:4326)."
        )
    if gdf.crs.to_epsg() != 4326:
        report.warnings.append(f"reprojected from {gdf.crs.to_string()} to EPSG:4326")
        gdf = gdf.to_crs(4326)

    minx, miny, maxx, maxy = gdf.total_bounds
    bx0, by0, bx1, by1 = NIGERIA_BBOX
    if minx < bx0 or miny < by0 or maxx > bx1 or maxy > by1:
        raise LoadError(
            f"extent ({minx:.3f}, {miny:.3f}, {maxx:.3f}, {maxy:.3f}) falls outside Nigeria. "
            "The coordinate reference system or axis order is probably wrong."
        )

    columns = [c for c in gdf.columns if c != gdf.geometry.name]
    name_col = _pick_column(columns, manifest.field_candidates("name"), "name")
    code_col = _pick_column(columns, manifest.field_candidates("code"), "code")
    alias_cols = [c for c in manifest.field_candidates("alias_codes") if c in columns]

    within_prepared = prep(within) if within is not None else None
    rows: list[dict] = []
    rejected: list[str] = []
    repaired_count = 0
    for idx, rec in gdf.iterrows():
        name = clean_name(rec[name_col])
        code = _clean_code(rec[code_col])
        if not name or not code:
            rejected.append(f"row {idx}: missing name or code")
            continue
        geom, repaired = repair_polygonal(rec.geometry)
        if geom is None:
            rejected.append(f"row {idx} ({name}): empty or non-polygonal geometry")
            continue
        repaired_count += int(repaired)
        if within_prepared is not None and not within_prepared.contains(
            geom.representative_point()
        ):
            report.rows_out_of_scope += 1
            continue
        attrs = {c: _json_safe(rec[c]) for c in columns}
        aliases = [str(rec[c]).strip() for c in alias_cols if clean_name(rec[c])]
        aliases += (manifest.name_aliases or {}).get(name, [])
        if manifest.rename and name in manifest.rename:
            aliases.append(name)
            name = manifest.rename[name]
        rows.append(
            {
                "name": name,
                "source_name": str(rec[name_col]),
                "source_code": code,
                "geom": geom,
                "attributes": attrs,
                "aliases": aliases,
            }
        )

    codes = [r["source_code"] for r in rows]
    dupes = sorted({c for c in codes if codes.count(c) > 1})
    if dupes:
        raise LoadError(f"duplicate codes in column {code_col!r}: {dupes[:10]}")
    if repaired_count:
        report.warnings.append(f"repaired {repaired_count} invalid geometries with make_valid")
    if rejected:
        report.warnings.append(f"rejected {len(rejected)} rows: " + "; ".join(rejected[:10]))
    report.rows_rejected = len(rejected)
    return rows, report


# --------------------------------------------------------------------------- registry


def upsert_source(session: Session, manifest: Manifest) -> Source:
    src = session.scalar(select(Source).where(Source.key == manifest.source.key))
    if src is None:
        src = Source(key=manifest.source.key)
        session.add(src)
    src.name = manifest.source.name
    src.url = manifest.source.url
    session.flush()
    return src


def upsert_dataset(
    session: Session, manifest: Manifest, retrieved: RetrievedFile | None
) -> Dataset:
    src = upsert_source(session, manifest)
    ds = session.scalar(select(Dataset).where(Dataset.key == manifest.key))
    if ds is None:
        ds = Dataset(key=manifest.key, source_id=src.id, status="registered")
        session.add(ds)
    ds.source_id = src.id
    for attr in (
        "distributor",
        "title",
        "version",
        "publication_date",
        "source_update_text",
        "geographic_coverage",
        "method_summary",
        "limitations",
        "licence",
        "licence_url",
        "licence_verified",
        "commercial_use_allowed",
        "landing_url",
    ):
        setattr(ds, attr, getattr(manifest, attr))
    ds.download_url = manifest.download.url
    ds.extra = {
        # Keep state written by earlier loads (e.g. last_parameters for the skip check).
        **(ds.extra or {}),
        "kind": manifest.kind,
        "level": manifest.level,
        "licence_evidence": manifest.licence_evidence,
        "attribution": manifest.attribution,
        "manifest": manifest.path.name if manifest.path else None,
    }
    if retrieved is not None:
        ds.file_name = retrieved.path.name
        ds.file_bytes = retrieved.bytes
        ds.retrieved_at = retrieved.retrieved_at
        if retrieved.url:
            ds.download_url = retrieved.url
    session.flush()
    return ds


# --------------------------------------------------------------------------- hierarchy


def find_active_area(session: Session, level: str, name: str) -> AdminArea:
    """Find an active area by name or alias, case-insensitively."""
    q = text(
        """
        SELECT a.id FROM admin_area a
        WHERE a.level = :level AND a.active
          AND (lower(a.name) = lower(:name)
               OR EXISTS (SELECT 1 FROM place_alias p
                          WHERE p.admin_area_id = a.id AND lower(p.alias) = lower(:name)))
        """
    )
    ids = session.execute(q, {"level": level, "name": name}).scalars().all()
    if len(ids) == 1:
        return session.get(AdminArea, ids[0])
    names = (
        session.execute(
            text("SELECT name FROM admin_area WHERE level = :level AND active ORDER BY name"),
            {"level": level},
        )
        .scalars()
        .all()
    )
    if not ids:
        raise LoadError(f"no active {level} named {name!r}. Available: {names}")
    raise LoadError(f"{name!r} matches {len(ids)} active {level}s; be more specific")


def area_shape(session: Session, area_id: int) -> BaseGeometry:
    wkb = session.execute(
        text("SELECT ST_AsBinary(geom) FROM admin_area WHERE id = :id"), {"id": area_id}
    ).scalar_one()
    return shapely.from_wkb(bytes(wkb))


def activate_dataset(session: Session, dataset_id: int, level: str) -> None:
    session.execute(
        text("UPDATE admin_area SET active = (dataset_id = :ds) WHERE level = :level"),
        {"ds": dataset_id, "level": level},
    )
    session.execute(
        text(
            """
            UPDATE dataset SET status = 'superseded'
            WHERE id <> :ds AND status = 'loaded'
              AND id IN (SELECT DISTINCT dataset_id FROM admin_area WHERE level = :level)
            """
        ),
        {"ds": dataset_id, "level": level},
    )


def assign_parents(session: Session, level: str) -> int:
    """Link each active area to the active parent it overlaps most. Returns rows linked."""
    parent_level = PARENT_LEVEL.get(level)
    if parent_level is None:
        session.execute(
            text(
                "UPDATE admin_area SET parent_id = NULL, parent_overlap = NULL, "
                "parent_method = 'none' WHERE level = :level AND active"
            ),
            {"level": level},
        )
        return 0
    linked = session.execute(
        text(
            """
            WITH best AS (
              SELECT DISTINCT ON (c.id) c.id AS cid, p.id AS pid,
                     ST_Area(ST_Intersection(c.geom, p.geom)) / NULLIF(ST_Area(c.geom), 0)
                       AS ratio
              FROM admin_area c
              JOIN admin_area p
                ON p.level = :plevel AND p.active
               AND c.geom && p.geom AND ST_Intersects(c.geom, p.geom)
              WHERE c.level = :level AND c.active
              ORDER BY c.id, ratio DESC NULLS LAST
            )
            UPDATE admin_area c
               SET parent_id = best.pid,
                   parent_overlap = LEAST(1.0, best.ratio),
                   parent_method = 'spatial_overlap'
              FROM best
             WHERE c.id = best.cid
            """
        ),
        {"level": level, "plevel": parent_level},
    ).rowcount
    session.execute(
        text(
            """
            UPDATE admin_area c
               SET parent_id = NULL, parent_overlap = NULL, parent_method = 'none'
             WHERE c.level = :level AND c.active
               AND NOT EXISTS (SELECT 1 FROM admin_area p
                               WHERE p.level = :plevel AND p.active
                                 AND c.geom && p.geom AND ST_Intersects(c.geom, p.geom))
            """
        ),
        {"level": level, "plevel": parent_level},
    )
    return linked


def hierarchy_warnings(session: Session, level: str) -> list[str]:
    out: list[str] = []
    if level in PARENT_LEVEL:
        low = session.execute(
            text(
                """
                SELECT c.name, p.name, round(c.parent_overlap::numeric, 3)
                FROM admin_area c LEFT JOIN admin_area p ON p.id = c.parent_id
                WHERE c.level = :level AND c.active
                  AND (c.parent_id IS NULL OR c.parent_overlap < :thr)
                ORDER BY c.parent_overlap NULLS FIRST
                """
            ),
            {"level": level, "thr": LOW_OVERLAP},
        ).all()
        if low:
            sample = ", ".join(f"{c} → {p or 'none'} ({o})" for c, p, o in low[:10])
            out.append(
                f"{len(low)} {level} areas have no parent or lie less than "
                f"{int(LOW_OVERLAP * 100)}% inside their parent: {sample}"
            )
    dupes = session.execute(
        text(
            """
            SELECT name, count(*) FROM admin_area
            WHERE level = :level AND active
            GROUP BY parent_id, name HAVING count(*) > 1
            """
        ),
        {"level": level},
    ).all()
    if dupes:
        out.append(
            f"duplicate {level} names under the same parent: "
            + ", ".join(f"{n} ×{c}" for n, c in dupes[:10])
        )
    return out


# --------------------------------------------------------------------------- loading

UPSERT_SQL = text(
    """
    INSERT INTO admin_area (level, name, source_name, source_code, dataset_id, active,
                            geom, attributes)
    VALUES (:level, :name, :source_name, :source_code, :dataset_id, false,
            ST_Multi(ST_SetSRID(ST_GeomFromWKB(:wkb), 4326)), CAST(:attributes AS jsonb))
    ON CONFLICT ON CONSTRAINT uq_admin_area_dataset_code DO UPDATE
       SET name = EXCLUDED.name,
           source_name = EXCLUDED.source_name,
           geom = EXCLUDED.geom,
           attributes = EXCLUDED.attributes,
           updated_at = now()
    RETURNING id
    """
)


def resolve_file(manifest: Manifest, file: Path | None, raw_dir: Path | None) -> Path:
    if file is not None:
        return file
    found = default_file_for(manifest, raw_dir)
    if found is None:
        if manifest.download.mode == "http":
            raise FileNotProvidedError(
                f"no local copy of {manifest.key}; run `connectly ingest fetch "
                f"{manifest.key}` first or pass --file"
            )
        raise FileNotProvidedError(
            f"{manifest.key} must be downloaded by hand and passed with --file.\n"
            f"{manifest.download.instructions or ''}\nPage: {manifest.landing_url}"
        )
    return found


def load_boundaries(
    session: Session,
    manifest: Manifest,
    file: Path | None = None,
    within_state: str | None = None,
    activate: str = "auto",
    force: bool = False,
    raw_dir: Path | None = None,
) -> LoadReport:
    if activate not in ("auto", "yes", "no"):
        raise ValueError("activate must be 'auto', 'yes' or 'no'")
    path = resolve_file(manifest, file, raw_dir)
    retrieved = describe_local_file(path, url=manifest.download.url)
    params = {"file": path.name, "within_state": within_state, "activate": activate}

    ds = upsert_dataset(session, manifest, retrieved)
    already_loaded = (
        ds.status in ("loaded", "superseded")
        and ds.file_sha256 == retrieved.sha256
        and (ds.extra or {}).get("last_parameters") == params
    )
    if already_loaded and not force:
        run = IngestRun(
            dataset_id=ds.id,
            status="skipped",
            finished_at=datetime.now(tz=UTC),
            parameters=params,
            warnings=["identical file and parameters already loaded; use --force to reload"],
        )
        session.add(run)
        session.flush()
        return LoadReport(
            dataset_key=manifest.key,
            status="skipped",
            run_id=run.id,
            warnings=run.warnings,
            active=_is_active(session, ds.id, manifest.level),
        )

    run = IngestRun(dataset_id=ds.id, status="running", parameters=params)
    session.add(run)
    session.flush()

    within_geom = None
    if within_state:
        state = find_active_area(session, "state", within_state)
        within_geom = area_shape(session, state.id)
        params["within_state_id"] = state.id

    rows, report = prepare_features(path, manifest, within=within_geom)
    report.run_id = run.id
    if not rows:
        raise LoadError(
            f"no usable features after filtering (read {report.rows_read}, "
            f"rejected {report.rows_rejected}, outside scope {report.rows_out_of_scope})"
        )

    loaded_ids: list[int] = []
    for r in rows:
        new_id = session.execute(
            UPSERT_SQL,
            {
                "level": manifest.level,
                "name": r["name"],
                "source_name": r["source_name"],
                "source_code": r["source_code"],
                "dataset_id": ds.id,
                "wkb": shapely.to_wkb(r["geom"]),
                "attributes": json.dumps(r["attributes"]),
            },
        ).scalar_one()
        loaded_ids.append(new_id)
        for alias in r["aliases"]:
            exists = session.scalar(
                select(PlaceAlias.id).where(
                    PlaceAlias.admin_area_id == new_id, PlaceAlias.alias == alias
                )
            )
            if not exists:
                session.add(PlaceAlias(admin_area_id=new_id, alias=alias, source=manifest.key))

    if within_state is None:
        # A full load replaces the dataset: remove areas no longer in the file.
        removed = session.execute(
            text(
                "DELETE FROM admin_area WHERE dataset_id = :ds AND level = :level "
                "AND NOT (id = ANY(:ids))"
            ),
            {"ds": ds.id, "level": manifest.level, "ids": loaded_ids},
        ).rowcount
        if removed:
            report.warnings.append(f"removed {removed} areas no longer present in the file")

    session.execute(
        text(
            "UPDATE admin_area SET area_km2 = ST_Area(geom::geography) / 1e6 WHERE dataset_id = :ds"
        ),
        {"ds": ds.id},
    )

    level = manifest.level
    others_active = session.scalar(
        text(
            "SELECT count(*) FROM admin_area WHERE level = :level AND active AND dataset_id <> :ds"
        ),
        {"level": level, "ds": ds.id},
    )
    should_activate = activate == "yes" or (
        activate == "auto" and (others_active == 0 or _is_active(session, ds.id, level))
    )
    if should_activate:
        activate_dataset(session, ds.id, level)
        assign_parents(session, level)
        child = CHILD_LEVEL.get(level)
        if child:
            assign_parents(session, child)
        report.warnings.extend(hierarchy_warnings(session, level))
    else:
        report.warnings.append(
            f"loaded but NOT active: another dataset is active for level {level!r}. "
            f"Re-run with --activate yes to switch."
        )

    total = session.scalar(
        text("SELECT count(*) FROM admin_area WHERE dataset_id = :ds"), {"ds": ds.id}
    )
    if manifest.expected_count and within_state is None and total != manifest.expected_count:
        report.warnings.append(f"expected {manifest.expected_count} areas, found {total}")

    ds.status = "loaded" if should_activate or ds.status != "superseded" else ds.status
    ds.file_sha256 = retrieved.sha256
    ds.record_count = total
    # Stored for the "already loaded" check; derived ids are left out so runs compare equal.
    ds.extra = {
        **(ds.extra or {}),
        "last_parameters": {k: params[k] for k in ("file", "within_state", "activate")},
    }

    run.status = "succeeded"
    run.finished_at = datetime.now(tz=UTC)
    run.rows_read = report.rows_read
    run.rows_loaded = len(rows)
    run.rows_rejected = report.rows_rejected
    run.warnings = report.warnings
    run.parameters = params
    session.flush()

    report.status = "succeeded"
    report.rows_loaded = len(rows)
    report.active = should_activate
    return report


def _is_active(session: Session, dataset_id: int, level: str) -> bool:
    return bool(
        session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM admin_area WHERE dataset_id = :ds "
                "AND level = :level AND active)"
            ),
            {"ds": dataset_id, "level": level},
        )
    )


def record_failure(session: Session, manifest: Manifest, error: str, params: dict) -> int:
    """Record a failed run in its own transaction, after the load was rolled back."""
    ds = upsert_dataset(session, manifest, None)
    if ds.status == "registered":
        ds.status = "failed"
    run = IngestRun(
        dataset_id=ds.id,
        status="failed",
        finished_at=datetime.now(tz=UTC),
        error=error[:4000],
        parameters=params,
    )
    session.add(run)
    session.flush()
    return run.id
