"""Load point and extent datasets into `settlement` or `facility`.

Supports vector files (GeoJSON, GeoPackage, Shapefile, zipped) and CSV/CSV.gz tables with
longitude/latitude columns. Each record is linked to the active ward, LGA and state it lies
in by point-in-polygon, so the explorer and scoring never depend on name matching.

Manifest `points` keys:
  target: facility | settlement
  facility_kind: health | education | financial | telecom | ...  (facility targets)
  kind_column / kind_values: optional per-row kind mapping
  lon, lat: candidate column names for tables
  layer: layer name inside a multi-layer file
  csv_names: column names to use when a CSV has no header row
  filters: [{column: mcc, in: ["621"]}]   keep only matching rows
  code_compose: [radio, mcc, net, area, cell]  build the code from several columns
  dedupe_round: 4      collapse records at the same rounded position (e.g. cells → sites)
  dedupe_by: [radio]   ...and the same values in these columns
fields: name, code, subtype, status, ownership, settlement_type (candidate column lists)
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.ingest.boundaries import area_shape, find_active_area
from connectly.ingest.common import (
    LoadError,
    LoadReport,
    check_extent,
    clean_code,
    clean_name,
    ensure_wgs84,
    finish_run,
    json_safe,
    manifest_fingerprint,
    optional_column,
    pick_column,
    read_vector,
    repair_polygonal,
    resolve_file,
    skip_if_loaded,
    start_run,
    to_float,
    upsert_dataset,
)
from connectly.ingest.coverage import CoverageError, compute_coverage
from connectly.ingest.fetch import describe_local_file
from connectly.ingest.manifest import Manifest
from connectly.models import FACILITY_KINDS

TABLE_SUFFIXES = (".csv", ".csv.gz", ".tsv", ".txt")


def _is_table(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(s) for s in TABLE_SUFFIXES)


def _read_table(path: Path, manifest: Manifest, report: LoadReport) -> gpd.GeoDataFrame:
    cfg = manifest.points or {}
    sep = "\t" if path.name.lower().endswith(".tsv") else ","
    names = cfg.get("csv_names")
    header: int | None = 0
    if names:
        opener = gzip.open if path.name.lower().endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            first = f.readline().strip().split(sep)
        # Use the supplied names only when the first row is data, not a header.
        if not set(n.lower() for n in names) & set(c.strip().lower() for c in first):
            header = None
        else:
            names = None
    try:
        df = pd.read_csv(
            path,
            sep=sep,
            dtype=str,
            header=header,
            names=names,
            keep_default_na=False,
            na_values=[""],
        )
    except Exception as e:  # noqa: BLE001
        raise LoadError(f"could not read {path}: {e}") from e
    report.rows_read = len(df)
    if df.empty:
        raise LoadError(f"{path} contains no rows")
    cols = list(df.columns)
    lon_col = pick_column(cols, cfg.get("lon", ["longitude", "lon", "x"]), "lon")
    lat_col = pick_column(cols, cfg.get("lat", ["latitude", "lat", "y"]), "lat")
    lon = df[lon_col].map(to_float)
    lat = df[lat_col].map(to_float)
    bad = lon.isna() | lat.isna()
    if bad.any():
        report.warnings.append(f"rejected {int(bad.sum())} rows without numeric coordinates")
        report.rows_rejected += int(bad.sum())
    df = df[~bad]
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(lon[~bad], lat[~bad]), crs="EPSG:4326")
    return gdf


def _apply_filters(gdf: gpd.GeoDataFrame, manifest: Manifest, report: LoadReport):
    for f in (manifest.points or {}).get("filters") or []:
        col = pick_column(list(gdf.columns), [f["column"]], f["column"])
        allowed = {str(v) for v in f["in"]}
        keep = gdf[col].astype(str).str.strip().isin(allowed)
        report.warnings.append(
            f"filter {col} in {sorted(allowed)}: kept {int(keep.sum())} of {len(gdf)} rows"
        )
        gdf = gdf[keep]
    return gdf


def _kind_for(row, cfg: dict) -> str | None:
    if cfg.get("kind_column"):
        raw = clean_name(row.get(cfg["kind_column"]))
        mapped = (cfg.get("kind_values") or {}).get(raw) if raw else None
        return mapped or cfg.get("facility_kind")
    return cfg.get("facility_kind")


def prepare_points(
    path: Path, manifest: Manifest, within: BaseGeometry | None
) -> tuple[list[dict], LoadReport]:
    cfg = manifest.points or {}
    report = LoadReport(dataset_key=manifest.key, status="running")
    if _is_table(path):
        gdf = _read_table(path, manifest, report)
        gdf = _apply_filters(gdf, manifest, report)
        if gdf.empty:
            raise LoadError("no rows left after filters")
        # Tables declare their own lon/lat; still refuse coordinates outside Nigeria.
        outside = ~gdf.geometry.within(shapely.box(2.0, 3.5, 15.5, 14.5))
        if outside.any():
            report.warnings.append(f"rejected {int(outside.sum())} rows outside Nigeria")
            report.rows_rejected += int(outside.sum())
            gdf = gdf[~outside]
    else:
        gdf = read_vector(path, manifest, report, layer=cfg.get("layer"))
        gdf = _apply_filters(gdf, manifest, report)
    if gdf.empty:
        raise LoadError("no usable rows")
    gdf = ensure_wgs84(gdf, manifest, report, path)
    check_extent(gdf)

    cols = [c for c in gdf.columns if c != gdf.geometry.name]
    compose = cfg.get("code_compose")
    code_col = None if compose else pick_column(cols, manifest.field_candidates("code"), "code")
    if compose:
        for c in compose:
            pick_column(cols, [c], "code_compose")
    name_col = optional_column(cols, manifest.field_candidates("name"))
    subtype_col = optional_column(cols, manifest.field_candidates("subtype"))
    status_col = optional_column(cols, manifest.field_candidates("status"))
    owner_col = optional_column(cols, manifest.field_candidates("ownership"))
    stype_col = optional_column(cols, manifest.field_candidates("settlement_type"))
    target = cfg.get("target", "facility")
    if target == "facility" and not (cfg.get("facility_kind") or cfg.get("kind_column")):
        raise LoadError("facility manifests need points.facility_kind or points.kind_column")

    within_prepared = prep(within) if within is not None else None
    rows: list[dict] = []
    seen_sites: set[tuple] = set()
    rejected = 0
    dedupe_round = cfg.get("dedupe_round")
    dedupe_by = cfg.get("dedupe_by") or []
    for _idx, rec in gdf.iterrows():
        geom = rec.geometry
        extent = None
        if not isinstance(geom, BaseGeometry) or geom.is_empty:
            rejected += 1
            continue
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            extent, _ = repair_polygonal(geom)
            if extent is None:
                rejected += 1
                continue
            point = extent.representative_point()
        elif geom.geom_type == "Point":
            point = Point(geom.x, geom.y)
        elif geom.geom_type == "MultiPoint":
            point = geom.centroid
        else:
            rejected += 1
            continue
        if within_prepared is not None and not within_prepared.contains(point):
            report.rows_out_of_scope += 1
            continue
        if compose:
            parts = [clean_code(rec[c]) or "" for c in compose]
            code = "-".join(parts)
        else:
            code = clean_code(rec[code_col])
        if dedupe_round is not None:
            key = (round(point.x, dedupe_round), round(point.y, dedupe_round)) + tuple(
                clean_code(rec[c]) for c in dedupe_by
            )
            if key in seen_sites:
                continue
            seen_sites.add(key)
            code = "site-" + "-".join(str(k) for k in key)
        if not code:
            rejected += 1
            continue
        row = {
            "source_code": code,
            "name": clean_name(rec[name_col]) if name_col else None,
            "point": point,
            "extent": extent,
            "attributes": {c: json_safe(rec[c]) for c in cols},
        }
        if target == "facility":
            kind = _kind_for(rec, cfg)
            if kind not in FACILITY_KINDS:
                rejected += 1
                continue
            row |= {
                "kind": kind,
                "subtype": clean_name(rec[subtype_col]) if subtype_col else cfg.get("subtype"),
                "operational_status": clean_name(rec[status_col]) if status_col else None,
                "ownership": clean_name(rec[owner_col]) if owner_col else None,
            }
        else:
            row["settlement_type"] = clean_name(rec[stype_col]) if stype_col else None
        rows.append(row)

    codes = [r["source_code"] for r in rows]
    if len(codes) != len(set(codes)):
        dupes = pd.Series(codes)[pd.Series(codes).duplicated()].unique()[:10]
        raise LoadError(f"duplicate codes: {list(dupes)}; set code_compose or dedupe options")
    if rejected:
        report.warnings.append(f"rejected {rejected} rows (missing code, geometry or kind)")
    if dedupe_round is not None:
        report.warnings.append(
            f"collapsed records to {len(rows)} distinct sites (rounded to {dedupe_round} dp)"
        )
    report.rows_rejected += rejected
    return rows, report


FACILITY_UPSERT = text(
    """
    INSERT INTO facility (kind, subtype, name, source_code, dataset_id, geom,
                          operational_status, ownership, attributes)
    VALUES (:kind, :subtype, :name, :source_code, :dataset_id,
            ST_SetSRID(ST_GeomFromWKB(:wkb), 4326), :operational_status, :ownership,
            CAST(:attributes AS jsonb))
    ON CONFLICT ON CONSTRAINT uq_facility_dataset_code DO UPDATE
       SET kind = EXCLUDED.kind, subtype = EXCLUDED.subtype, name = EXCLUDED.name,
           geom = EXCLUDED.geom, operational_status = EXCLUDED.operational_status,
           ownership = EXCLUDED.ownership, attributes = EXCLUDED.attributes,
           updated_at = now()
    RETURNING id
    """
)

SETTLEMENT_UPSERT = text(
    """
    INSERT INTO settlement (name, source_name, source_code, dataset_id, settlement_type,
                            point, extent, attributes)
    VALUES (:name, :name, :source_code, :dataset_id, :settlement_type,
            ST_SetSRID(ST_GeomFromWKB(:wkb), 4326),
            CASE WHEN CAST(:extent_wkb AS bytea) IS NULL THEN NULL
                 ELSE ST_Multi(ST_SetSRID(ST_GeomFromWKB(CAST(:extent_wkb AS bytea)), 4326)) END,
            CAST(:attributes AS jsonb))
    ON CONFLICT ON CONSTRAINT uq_settlement_dataset_code DO UPDATE
       SET name = EXCLUDED.name, source_name = EXCLUDED.source_name,
           settlement_type = EXCLUDED.settlement_type, point = EXCLUDED.point,
           extent = EXCLUDED.extent, attributes = EXCLUDED.attributes, updated_at = now()
    RETURNING id
    """
)


def link_to_admin(session: Session, table: str, dataset_id: int | None = None) -> int:
    """Set ward_id / lga_id / state_id by point-in-polygon against active areas."""
    geom = "geom" if table == "facility" else "point"
    scope = "AND t.dataset_id = :ds" if dataset_id is not None else ""
    params = {"ds": dataset_id}
    # Start from scratch so no link to a since-replaced area survives.
    session.execute(
        text(
            f"UPDATE {table} t SET ward_id = NULL, lga_id = NULL, state_id = NULL "
            f"WHERE true {scope}"
        ),
        params,
    )
    session.execute(
        text(
            f"""
            UPDATE {table} t SET ward_id = w.id, lga_id = w.parent_id, state_id = l.parent_id
            FROM admin_area w JOIN admin_area l ON l.id = w.parent_id
            WHERE w.level = 'ward' AND w.active AND ST_Intersects(w.geom, t.{geom}) {scope}
            """
        ),
        params,
    )
    # Where no ward is loaded (or a point falls in a gap), link to LGA and state directly.
    session.execute(
        text(
            f"""
            UPDATE {table} t SET ward_id = NULL, lga_id = l.id, state_id = l.parent_id
            FROM admin_area l
            WHERE t.ward_id IS NULL AND l.level = 'lga' AND l.active
              AND ST_Intersects(l.geom, t.{geom}) {scope}
            """
        ),
        params,
    )
    unlinked = session.scalar(
        text(f"SELECT count(*) FROM {table} t WHERE t.state_id IS NULL {scope}"), params
    )
    return int(unlinked or 0)


def load_points(
    session: Session,
    manifest: Manifest,
    file: Path | None = None,
    within_state: str | None = None,
    force: bool = False,
    raw_dir: Path | None = None,
) -> LoadReport:
    target = (manifest.points or {}).get("target", "facility")
    if target not in ("facility", "settlement"):
        raise LoadError(f"points.target must be facility or settlement, not {target!r}")
    path = resolve_file(manifest, file, raw_dir)
    retrieved = describe_local_file(path, url=manifest.download.url)
    params = {
        "file": path.name,
        "within_state": within_state,
        "manifest": manifest_fingerprint(manifest),
    }
    ds = upsert_dataset(session, manifest, retrieved)
    skipped = skip_if_loaded(session, ds, retrieved.sha256, params, force)
    if skipped:
        return LoadReport(manifest.key, "skipped", run_id=skipped.id, warnings=skipped.warnings)
    run = start_run(session, ds, params)

    within = None
    within_sid = None
    if within_state:
        within_sid = find_active_area(session, "state", within_state).id
        within = area_shape(session, within_sid)
    rows, report = prepare_points(path, manifest, within)
    if not rows:
        raise LoadError(
            f"no usable records (read {report.rows_read}, rejected {report.rows_rejected}, "
            f"outside scope {report.rows_out_of_scope})"
        )

    ids: list[int] = []
    for r in rows:
        base = {
            "name": r["name"],
            "source_code": r["source_code"],
            "dataset_id": ds.id,
            "wkb": shapely.to_wkb(r["point"]),
            "attributes": json.dumps(r["attributes"]),
        }
        if target == "facility":
            ids.append(
                session.execute(
                    FACILITY_UPSERT,
                    base
                    | {
                        "kind": r["kind"],
                        "subtype": r["subtype"],
                        "operational_status": r["operational_status"],
                        "ownership": r["ownership"],
                    },
                ).scalar_one()
            )
        else:
            ids.append(
                session.execute(
                    SETTLEMENT_UPSERT,
                    base
                    | {
                        "settlement_type": r["settlement_type"],
                        "extent_wkb": shapely.to_wkb(r["extent"]) if r["extent"] else None,
                    },
                ).scalar_one()
            )

    table = "facility" if target == "facility" else "settlement"
    if within_state is None:
        removed = session.execute(
            text(f"DELETE FROM {table} WHERE dataset_id = :ds AND NOT (id = ANY(:ids))"),
            {"ds": ds.id, "ids": ids},
        ).rowcount
        if removed:
            report.warnings.append(f"removed {removed} records no longer present in the file")
    unlinked = link_to_admin(session, table, ds.id)
    if unlinked:
        report.warnings.append(f"{unlinked} records fall outside every loaded LGA")
    try:
        coverage = compute_coverage(session, manifest, ds, table, within_sid)
    except CoverageError as e:
        raise LoadError(str(e)) from e
    report.warnings.append(f"coverage: {len(coverage.state_ids)} states ({coverage.method})")
    report.warnings.extend(coverage.warnings)
    total = session.scalar(
        text(f"SELECT count(*) FROM {table} WHERE dataset_id = :ds"), {"ds": ds.id}
    )
    report.rows_loaded = len(rows)
    finish_run(session, run, ds, report, retrieved.sha256, params, int(total))
    return report
