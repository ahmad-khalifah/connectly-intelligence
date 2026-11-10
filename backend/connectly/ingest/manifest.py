"""Dataset manifests: the declared source, licence and field mapping for each dataset.

A manifest is the single place where a dataset's provenance is written down. Loaders copy
it into the `dataset` table so the database is self-describing.

Kinds:
  admin_boundaries   polygons for one administrative level
  settlements        settlement points or extents
  facilities         point infrastructure from a table or vector file
  osm_facilities     point infrastructure from an OpenStreetMap extract (.osm.pbf)
  indicator_table    values from a CSV transcribed from a published report
  dhs_api            values from the DHS Program indicator API
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

MANIFEST_DIR = Path(__file__).parent / "manifests"

KINDS = (
    "admin_boundaries",
    "settlements",
    "facilities",
    "osm_facilities",
    "indicator_table",
    "dhs_api",
)
DOWNLOAD_MODES = ("http", "manual", "api")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    url: str | None = None


@dataclass(frozen=True)
class DownloadSpec:
    mode: str  # "http", "manual" or "api"
    url: str | None = None
    file_name: str | None = None
    metadata_url: str | None = None
    instructions: str | None = None
    # For archives: the member to extract and load.
    extract: str | None = None
    # Expected SHA-256 of the downloaded file, when the publisher states one.
    sha256: str | None = None


@dataclass(frozen=True)
class Manifest:
    key: str
    kind: str
    source: SourceSpec
    title: str
    download: DownloadSpec
    level: str | None = None
    fields: dict[str, list[str]] = field(default_factory=dict)
    distributor: str | None = None
    version: str | None = None
    publication_date: date | None = None
    source_update_text: str | None = None
    reference_period: str | None = None
    geographic_coverage: str | None = None
    method_summary: str | None = None
    limitations: str | None = None
    licence: str | None = None
    licence_url: str | None = None
    licence_verified: bool = False
    licence_evidence: str | None = None
    commercial_use_allowed: bool | None = None
    attribution: str | None = None
    landing_url: str | None = None
    expected_count: int | None = None
    # Extra names for specific areas, e.g. {"Abuja Federal Capital Territory": ["FCT"]}.
    name_aliases: dict[str, list[str]] | None = None
    # Display-name standardisation, e.g. {"the Federal Republic of Nigeria": "Nigeria"}.
    # The original stays in source_name and is added as an alias.
    rename: dict[str, str] | None = None
    # CRS to assume when the file declares none (e.g. TopoJSON, which is lon/lat by spec).
    # The extent check still runs, so a wrong assumption is caught.
    assume_crs: str | None = None
    assume_crs_reason: str | None = None
    # Attribute columns to store as indicator observations (see observations.py).
    observations: list[dict[str, Any]] | None = None
    # Extra validation, e.g. ancestor code checks.
    checks: list[dict[str, Any]] | None = None
    # Kind-specific configuration.
    points: dict[str, Any] | None = None
    osm: dict[str, Any] | None = None
    table: dict[str, Any] | None = None
    api: dict[str, Any] | None = None
    path: Path | None = field(default=None, compare=False)

    def field_candidates(self, name: str) -> list[str]:
        return list(self.fields.get(name) or [])


COMMON_REQUIRED = ("key", "kind", "source", "title", "download", "licence", "attribution")
KIND_REQUIRED: dict[str, tuple[str, ...]] = {
    "admin_boundaries": ("level", "fields"),
    "settlements": ("fields", "points"),
    "facilities": ("fields", "points"),
    "osm_facilities": ("osm",),
    "indicator_table": ("table",),
    "dhs_api": ("api",),
}


def _validate(raw: dict, name: str) -> None:
    missing = [k for k in COMMON_REQUIRED if k not in raw]
    if missing:
        raise ManifestError(f"{name}: missing keys {missing}")
    kind = raw["kind"]
    if kind not in KINDS:
        raise ManifestError(f"{name}: unsupported kind {kind!r}; expected one of {KINDS}")
    missing = [k for k in KIND_REQUIRED[kind] if not raw.get(k)]
    if missing:
        raise ManifestError(f"{name}: kind {kind!r} needs {missing}")
    mode = raw["download"].get("mode")
    if mode not in DOWNLOAD_MODES:
        raise ManifestError(f"{name}: download.mode must be one of {DOWNLOAD_MODES}")
    if mode == "http" and not raw["download"].get("url"):
        raise ManifestError(f"{name}: http downloads need download.url")
    if kind == "admin_boundaries":
        for f in ("name", "code"):
            if not raw["fields"].get(f):
                raise ManifestError(f"{name}: fields.{f} needs at least one column")
    if kind in ("settlements", "facilities") and not raw["fields"].get("code"):
        raise ManifestError(f"{name}: fields.code needs at least one column")
    if raw.get("licence_verified") and not raw.get("licence_evidence"):
        raise ManifestError(f"{name}: licence_verified needs licence_evidence")
    if raw.get("commercial_use_allowed") and not raw.get("licence_verified"):
        raise ManifestError(f"{name}: commercial use cannot be allowed on an unverified licence")
    for obs in raw.get("observations") or []:
        for k in ("indicator", "value", "value_type", "period"):
            if k not in obs:
                raise ManifestError(f"{name}: each observations entry needs {k!r}")


def load_manifest(path: Path) -> Manifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestError(f"{path.name}: not a mapping")
    _validate(raw, path.name)

    pub = raw.get("publication_date")
    if isinstance(pub, str):
        pub = date.fromisoformat(pub)

    known = set(Manifest.__dataclass_fields__)
    unknown = set(raw) - known
    if unknown:
        raise ManifestError(f"{path.name}: unknown keys {sorted(unknown)}")
    values = {k: v for k, v in raw.items() if k in known} | {
        "source": SourceSpec(**raw["source"]),
        "download": DownloadSpec(**raw["download"]),
        "publication_date": pub,
        "path": path,
    }
    return Manifest(**values)


def all_manifests(directory: Path = MANIFEST_DIR) -> dict[str, Manifest]:
    manifests = {}
    for path in sorted(directory.glob("*.yaml")):
        m = load_manifest(path)
        if m.key in manifests:
            raise ManifestError(f"duplicate manifest key {m.key!r}")
        manifests[m.key] = m
    return manifests


def get_manifest(key: str, directory: Path = MANIFEST_DIR) -> Manifest:
    manifests = all_manifests(directory)
    if key not in manifests:
        raise ManifestError(f"no manifest named {key!r}; known: {sorted(manifests)}")
    return manifests[key]
