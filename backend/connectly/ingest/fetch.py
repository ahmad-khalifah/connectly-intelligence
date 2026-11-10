"""Download datasets and record exactly what was retrieved."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from connectly.core.config import get_settings
from connectly.ingest.manifest import Manifest


class FetchError(RuntimeError):
    pass


@dataclass
class RetrievedFile:
    path: Path
    sha256: str
    bytes: int
    url: str | None
    retrieved_at: datetime

    def to_json(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        d["retrieved_at"] = self.retrieved_at.isoformat()
        return d


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + ".provenance.json")


def describe_local_file(path: Path, url: str | None = None) -> RetrievedFile:
    """Provenance for a file the user supplied, or one fetched earlier."""
    if not path.exists():
        raise FetchError(f"file not found: {path}")
    side = sidecar_path(path)
    if side.exists():
        info = json.loads(side.read_text())
        digest = sha256_of(path)
        if info.get("sha256") == digest:
            return RetrievedFile(
                path=path,
                sha256=digest,
                bytes=path.stat().st_size,
                url=info.get("url") or url,
                retrieved_at=datetime.fromisoformat(info["retrieved_at"]),
            )
    return RetrievedFile(
        path=path,
        sha256=sha256_of(path),
        bytes=path.stat().st_size,
        url=url,
        retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
    )


def _download(url: str, dest: Path, timeout: float) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as r:
        if r.status_code != 200:
            raise FetchError(f"GET {url} returned HTTP {r.status_code}")
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)


def fetch(manifest: Manifest, raw_dir: Path | None = None) -> RetrievedFile:
    """Download a dataset (http manifests only) into data/raw/<key>/."""
    spec = manifest.download
    if spec.mode != "http":
        raise FetchError(
            f"{manifest.key} must be downloaded by hand.\n{spec.instructions or ''}\n"
            f"Page: {manifest.landing_url}"
        )
    settings = get_settings()
    target_dir = (raw_dir or settings.raw_dir) / manifest.key
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / (spec.file_name or Path(spec.url).name)
    _download(spec.url, dest, settings.download_timeout)
    if spec.metadata_url:
        _download(spec.metadata_url, target_dir / Path(spec.metadata_url).name, 60.0)

    result = RetrievedFile(
        path=dest,
        sha256=sha256_of(dest),
        bytes=dest.stat().st_size,
        url=spec.url,
        retrieved_at=datetime.now(tz=UTC),
    )
    sidecar_path(dest).write_text(json.dumps(result.to_json(), indent=2))
    return result


def default_file_for(manifest: Manifest, raw_dir: Path | None = None) -> Path | None:
    """Where `fetch` would have saved the file, if it exists."""
    if not manifest.download.file_name:
        return None
    p = (raw_dir or get_settings().raw_dir) / manifest.key / manifest.download.file_name
    return p if p.exists() else None
