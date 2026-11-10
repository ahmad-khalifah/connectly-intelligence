"""Load facilities from an OpenStreetMap extract (.osm.pbf or .osm) using tag rules.

GDAL's OSM driver exposes a few tags as columns and the rest in `other_tags`
('"amenity"=>"bank","name:en"=>"..."'). Both are merged, then the manifest's rules map
tags to facility kinds. The first matching rule wins. Areas (e.g. a mapped hospital
compound) are stored at their representative point.

OpenStreetMap coverage is uneven: a missing feature does not mean the facility is absent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyogrio
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.ingest.boundaries import area_shape, find_active_area
from connectly.ingest.common import (
    LoadError,
    LoadReport,
    clean_name,
    finish_run,
    is_missing,
    manifest_fingerprint,
    repair_polygonal,
    resolve_file,
    skip_if_loaded,
    start_run,
    upsert_dataset,
)
from connectly.ingest.fetch import describe_local_file
from connectly.ingest.manifest import Manifest
from connectly.ingest.points import FACILITY_UPSERT, link_to_admin
from connectly.models import FACILITY_KINDS

TAG_RE = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')
BASE_COLUMNS = {"osm_id", "osm_way_id", "other_tags", "geometry"}


def parse_other_tags(value: object) -> dict[str, str]:
    if is_missing(value) or not value:
        return {}
    return {k.replace('\\"', '"'): v.replace('\\"', '"') for k, v in TAG_RE.findall(str(value))}


def match_rule(tags: dict[str, str], rules: list[dict]) -> dict | None:
    for rule in rules:
        value = tags.get(rule["tag"])
        if value is None:
            continue
        values = rule.get("values")
        if values is None or value in values:
            if all(tags.get(k) in v for k, v in (rule.get("also") or {}).items()):
                return rule
    return None


def prepare_osm(
    path: Path, manifest: Manifest, within: BaseGeometry | None
) -> tuple[list[dict], LoadReport]:
    cfg = manifest.osm or {}
    rules = cfg.get("rules") or []
    for r in rules:
        if r.get("kind") not in FACILITY_KINDS:
            raise LoadError(f"OSM rule {r} has invalid kind")
    report = LoadReport(dataset_key=manifest.key, status="running")
    layers = cfg.get("layers", ["points", "multipolygons"])
    bbox = tuple(within.bounds) if within is not None else None
    within_prepared = prep(within) if within is not None else None
    rows: dict[str, dict] = {}
    for layer in layers:
        try:
            gdf = pyogrio.read_dataframe(path, layer=layer, bbox=bbox)
        except Exception as e:  # noqa: BLE001
            raise LoadError(f"could not read layer {layer!r} of {path}: {e}") from e
        report.rows_read += len(gdf)
        if gdf.crs is not None and gdf.crs.to_epsg() not in (4326, None):
            gdf = gdf.to_crs(4326)
        cols = [c for c in gdf.columns if c not in BASE_COLUMNS]
        for rec in gdf.itertuples(index=False):
            rec = rec._asdict()
            tags = {c: str(rec[c]) for c in cols if not is_missing(rec.get(c)) and rec.get(c)}
            tags |= parse_other_tags(rec.get("other_tags"))
            rule = match_rule(tags, rules)
            if rule is None:
                continue
            geom = rec.get("geometry")
            if not isinstance(geom, BaseGeometry) or geom.is_empty:
                continue
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                poly, _ = repair_polygonal(geom)
                if poly is None:
                    continue
                point = poly.representative_point()
            else:
                point = geom.centroid if geom.geom_type != "Point" else geom
            if within_prepared is not None and not within_prepared.contains(point):
                report.rows_out_of_scope += 1
                continue
            if not is_missing(rec.get("osm_way_id")) and rec.get("osm_way_id"):
                code = f"way/{rec['osm_way_id']}"
            elif not is_missing(rec.get("osm_id")) and rec.get("osm_id"):
                prefix = "node" if layer == "points" else "relation"
                code = f"{prefix}/{rec['osm_id']}"
            else:
                continue
            rows[code] = {
                "source_code": code,
                "name": clean_name(tags.get("name")),
                "kind": rule["kind"],
                "subtype": rule.get("subtype") or f"{rule['tag']}={tags[rule['tag']]}",
                "operational_status": None,
                "ownership": clean_name(tags.get("operator:type")),
                "point": point,
                "attributes": {k: v for k, v in tags.items() if len(v) < 500},
            }
    report.warnings.append(
        "OpenStreetMap coverage is uneven; absence of a mapped feature is not evidence of absence"
    )
    return list(rows.values()), report


def load_osm(
    session: Session,
    manifest: Manifest,
    file: Path | None = None,
    within_state: str | None = None,
    force: bool = False,
    raw_dir: Path | None = None,
) -> LoadReport:
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
    rows, report = prepare_osm(path, manifest, within)
    if not rows:
        raise LoadError("no OpenStreetMap features matched the manifest's rules")
    ids = []
    for r in rows:
        ids.append(
            session.execute(
                FACILITY_UPSERT,
                {
                    "kind": r["kind"],
                    "subtype": r["subtype"],
                    "name": r["name"],
                    "source_code": r["source_code"],
                    "dataset_id": ds.id,
                    "wkb": shapely.to_wkb(r["point"]),
                    "operational_status": None,
                    "ownership": r["ownership"],
                    "attributes": json.dumps(r["attributes"]),
                },
            ).scalar_one()
        )
    if within_state is None:
        session.execute(
            text("DELETE FROM facility WHERE dataset_id = :ds AND NOT (id = ANY(:ids))"),
            {"ds": ds.id, "ids": ids},
        )
    covered = (
        session.execute(
            text(
                "SELECT id FROM admin_area WHERE level = 'state' AND active"
                + (" AND id = :sid" if within_state else "")
            ),
            {"sid": within_sid} if within_state else {},
        )
        .scalars()
        .all()
    )
    ds.extra = {**(ds.extra or {}), "coverage_state_ids": list(covered)}
    unlinked = link_to_admin(session, "facility", ds.id)
    if unlinked:
        report.warnings.append(f"{unlinked} features fall outside every loaded LGA")
    counts = session.execute(
        text("SELECT kind, count(*) FROM facility WHERE dataset_id = :ds GROUP BY kind"),
        {"ds": ds.id},
    ).all()
    report.warnings.append("loaded by kind: " + ", ".join(f"{k} {n}" for k, n in counts))
    report.rows_loaded = len(rows)
    total = sum(n for _, n in counts)
    finish_run(session, run, ds, report, retrieved.sha256, params, total)
    return report
