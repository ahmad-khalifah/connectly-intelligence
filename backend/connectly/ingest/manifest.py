"""Dataset manifests: the declared source, licence and field mapping for each dataset.

A manifest is the single place where a dataset's provenance is written down. The loader
copies it into the `dataset` table so the database is self-describing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

MANIFEST_DIR = Path(__file__).parent / "manifests"


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    url: str | None = None


@dataclass(frozen=True)
class DownloadSpec:
    mode: str  # "http" or "manual"
    url: str | None = None
    file_name: str | None = None
    metadata_url: str | None = None
    instructions: str | None = None


@dataclass(frozen=True)
class Manifest:
    key: str
    kind: str
    level: str
    source: SourceSpec
    title: str
    download: DownloadSpec
    fields: dict[str, list[str]]
    distributor: str | None = None
    version: str | None = None
    publication_date: date | None = None
    source_update_text: str | None = None
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
    path: Path | None = field(default=None, compare=False)

    def field_candidates(self, name: str) -> list[str]:
        return list(self.fields.get(name) or [])


REQUIRED = ("key", "kind", "level", "source", "title", "download", "fields")


def load_manifest(path: Path) -> Manifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise ManifestError(f"{path.name}: missing keys {missing}")
    if raw["kind"] != "admin_boundaries":
        raise ManifestError(f"{path.name}: unsupported kind {raw['kind']!r}")
    if raw["download"].get("mode") not in ("http", "manual"):
        raise ManifestError(f"{path.name}: download.mode must be 'http' or 'manual'")
    if raw["download"]["mode"] == "http" and not raw["download"].get("url"):
        raise ManifestError(f"{path.name}: http downloads need download.url")
    for required_field in ("name", "code"):
        if not raw["fields"].get(required_field):
            raise ManifestError(f"{path.name}: fields.{required_field} needs at least one column")

    pub = raw.get("publication_date")
    if isinstance(pub, str):
        pub = date.fromisoformat(pub)

    known = {f for f in Manifest.__dataclass_fields__}
    extra = {k: v for k, v in raw.items() if k in known} | {
        "source": SourceSpec(**raw["source"]),
        "download": DownloadSpec(**raw["download"]),
        "publication_date": pub,
        "path": path,
    }
    unknown = set(raw) - known
    if unknown:
        raise ManifestError(f"{path.name}: unknown keys {sorted(unknown)}")
    return Manifest(**extra)


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
