"""Shared ingestion building blocks: reading, validation, dataset registry and run records."""

from __future__ import annotations

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
from sqlalchemy import select
from sqlalchemy.orm import Session

from connectly.ingest.fetch import RetrievedFile, default_file_for
from connectly.ingest.manifest import Manifest
from connectly.models import Dataset, IngestRun, Source

# Generous bounding box around Nigeria (lon/lat). Data outside it almost always means a
# wrong or missing coordinate reference system.
NIGERIA_BBOX = (2.0, 3.5, 15.5, 14.5)


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


# --------------------------------------------------------------------------- values


def pick_column(columns: list[str], candidates: list[str], what: str) -> str:
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


def optional_column(columns: list[str], candidates: list[str]) -> str | None:
    try:
        return pick_column(columns, candidates, "-") if candidates else None
    except LoadError:
        return None


def is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA


def clean_name(value: object) -> str | None:
    if is_missing(value):
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def clean_code(value: object) -> str | None:
    if is_missing(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    return s or None


def to_float(value: object) -> float | None:
    if is_missing(value):
        return None
    try:
        f = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def json_safe(v: object) -> object:
    if is_missing(v):
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if hasattr(v, "item"):  # numpy scalars
        return v.item()
    return str(v)


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
    return shapely.force_2d(MultiPolygon(polys)), repaired


# --------------------------------------------------------------------------- reading


def check_extent(gdf: gpd.GeoDataFrame) -> None:
    minx, miny, maxx, maxy = gdf.total_bounds
    bx0, by0, bx1, by1 = NIGERIA_BBOX
    if minx < bx0 or miny < by0 or maxx > bx1 or maxy > by1:
        raise LoadError(
            f"extent ({minx:.3f}, {miny:.3f}, {maxx:.3f}, {maxy:.3f}) falls outside Nigeria. "
            "The coordinate reference system or axis order is probably wrong."
        )


def ensure_wgs84(gdf: gpd.GeoDataFrame, manifest: Manifest, report: LoadReport, path: Path):
    if gdf.crs is None:
        if not manifest.assume_crs:
            raise LoadError(
                f"{path} has no coordinate reference system. Re-export it with one "
                "(EPSG:4326), or set assume_crs in the manifest with a reason."
            )
        gdf = gdf.set_crs(manifest.assume_crs)
        report.warnings.append(
            f"file declares no CRS; assumed {manifest.assume_crs}"
            + (f" ({manifest.assume_crs_reason})" if manifest.assume_crs_reason else "")
        )
    if gdf.crs.to_epsg() != 4326:
        report.warnings.append(f"reprojected from {gdf.crs.to_string()} to EPSG:4326")
        gdf = gdf.to_crs(4326)
    return gdf


def read_vector(
    path: Path, manifest: Manifest, report: LoadReport, layer: str | None = None
) -> gpd.GeoDataFrame:
    try:
        gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    except Exception as e:  # noqa: BLE001 - surface any reader error clearly
        raise LoadError(f"could not read {path}: {e}") from e
    report.rows_read = len(gdf)
    if gdf.empty:
        raise LoadError(f"{path} contains no features")
    gdf = ensure_wgs84(gdf, manifest, report, path)
    check_extent(gdf)
    return gdf


def resolve_file(manifest: Manifest, file: Path | None, raw_dir: Path | None) -> Path:
    if file is not None:
        if not Path(file).exists():
            raise FileNotProvidedError(f"file not found: {file}")
        return Path(file)
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


DATASET_FIELDS = (
    "distributor",
    "title",
    "version",
    "publication_date",
    "source_update_text",
    "reference_period",
    "geographic_coverage",
    "method_summary",
    "limitations",
    "licence",
    "licence_url",
    "licence_verified",
    "commercial_use_allowed",
    "landing_url",
)


def upsert_dataset(
    session: Session, manifest: Manifest, retrieved: RetrievedFile | None
) -> Dataset:
    src = upsert_source(session, manifest)
    ds = session.scalar(select(Dataset).where(Dataset.key == manifest.key))
    if ds is None:
        ds = Dataset(key=manifest.key, source_id=src.id, status="registered")
        session.add(ds)
    ds.source_id = src.id
    for attr in DATASET_FIELDS:
        setattr(ds, attr, getattr(manifest, attr))
    ds.download_url = manifest.download.url or (manifest.api or {}).get("base_url")
    ds.extra = {
        # Keep state written by earlier loads (e.g. last_parameters for the skip check).
        **(ds.extra or {}),
        "kind": manifest.kind,
        "level": manifest.level,
        "licence_evidence": manifest.licence_evidence,
        "attribution": manifest.attribution,
        "manifest": manifest.path.name if manifest.path else None,
        "download_mode": manifest.download.mode,
        "download_instructions": manifest.download.instructions,
        "priority": manifest.priority,
        "declared_coverage_states": manifest.coverage_states,
    }
    if retrieved is not None:
        ds.file_name = retrieved.path.name
        ds.file_bytes = retrieved.bytes
        ds.retrieved_at = retrieved.retrieved_at
        if retrieved.url:
            ds.download_url = retrieved.url
    session.flush()
    return ds


def manifest_fingerprint(manifest: Manifest) -> str | None:
    """Checksum of the manifest file: a changed manifest means the data must be reloaded."""
    if manifest.path is None or not Path(manifest.path).exists():
        return None
    import hashlib

    return hashlib.sha256(Path(manifest.path).read_bytes()).hexdigest()[:16]


def skip_if_loaded(
    session: Session, ds: Dataset, sha256: str | None, params: dict, force: bool
) -> IngestRun | None:
    """Record and return a 'skipped' run if this exact input was already loaded."""
    same = (
        ds.status in ("loaded", "superseded")
        and ds.file_sha256 == sha256
        and (ds.extra or {}).get("last_parameters") == params
    )
    if not same or force:
        return None
    run = IngestRun(
        dataset_id=ds.id,
        status="skipped",
        finished_at=datetime.now(tz=UTC),
        parameters=params,
        warnings=["identical input and parameters already loaded; use --force to reload"],
    )
    session.add(run)
    session.flush()
    return run


def start_run(session: Session, ds: Dataset, params: dict) -> IngestRun:
    run = IngestRun(dataset_id=ds.id, status="running", parameters=params)
    session.add(run)
    session.flush()
    return run


def finish_run(
    session: Session,
    run: IngestRun,
    ds: Dataset,
    report: LoadReport,
    sha256: str | None,
    params: dict,
    record_count: int,
    status: str = "loaded",
) -> None:
    ds.status = status
    ds.file_sha256 = sha256
    ds.record_count = record_count
    ds.extra = {**(ds.extra or {}), "last_parameters": params}
    run.status = "succeeded"
    run.finished_at = datetime.now(tz=UTC)
    run.rows_read = report.rows_read
    run.rows_loaded = report.rows_loaded
    run.rows_rejected = report.rows_rejected
    run.warnings = report.warnings
    session.flush()
    report.status = "succeeded"
    report.run_id = run.id


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
