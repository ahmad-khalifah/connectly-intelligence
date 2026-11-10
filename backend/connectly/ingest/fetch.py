"""Download datasets and record exactly what was retrieved."""

from __future__ import annotations

import hashlib
import json
import zipfile
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
    """The file that will be loaded, and the checksum of what was downloaded.

    For archives, `path` is the extracted member and `sha256` is the archive's checksum
    (the value a publisher can state); `loaded_sha256` is the extracted file's.
    """

    path: Path
    sha256: str
    bytes: int
    url: str | None
    retrieved_at: datetime
    loaded_sha256: str | None = None

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
    digest = sha256_of(path)
    if side.exists():
        info = json.loads(side.read_text())
        # The sidecar is only trusted while the file is unchanged.
        if info.get("loaded_sha256", info.get("sha256")) == digest:
            return RetrievedFile(
                path=path,
                sha256=info["sha256"],
                bytes=info.get("bytes", path.stat().st_size),
                url=info.get("url") or url,
                retrieved_at=datetime.fromisoformat(info["retrieved_at"]),
                loaded_sha256=digest,
            )
    return RetrievedFile(
        path=path,
        sha256=digest,
        bytes=path.stat().st_size,
        url=url,
        retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        loaded_sha256=digest,
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


def extract_member(archive: Path, member: str, target_dir: Path) -> Path:
    """Extract one named member from a zip archive, refusing unsafe paths."""
    name = Path(member).name
    if not name or name != member.split("/")[-1] or ".." in Path(member).parts:
        raise FetchError(f"unsafe archive member name {member!r}")
    with zipfile.ZipFile(archive) as zf:
        if member not in zf.namelist():
            raise FetchError(f"{archive.name} has no member {member!r}; has {zf.namelist()[:20]}")
        info = zf.getinfo(member)
        if info.file_size > 5 * 1024**3:
            raise FetchError(f"{member} is larger than 5 GB; refusing to extract")
        out = target_dir / name
        with zf.open(member) as src, out.open("wb") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                dst.write(chunk)
    return out


def fetch(manifest: Manifest, raw_dir: Path | None = None) -> RetrievedFile:
    """Download a dataset (http manifests only) into data/raw/<key>/."""
    spec = manifest.download
    if spec.mode != "http":
        raise FetchError(
            f"{manifest.key} is not a direct download (mode {spec.mode!r}).\n"
            f"{spec.instructions or ''}\nPage: {manifest.landing_url}"
        )
    settings = get_settings()
    target_dir = (raw_dir or settings.raw_dir) / manifest.key
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / (spec.file_name or Path(spec.url).name)
    _download(spec.url, dest, settings.download_timeout)
    digest = sha256_of(dest)
    if spec.sha256 and digest != spec.sha256:
        dest.unlink()
        raise FetchError(
            f"checksum mismatch for {dest.name}: expected {spec.sha256}, got {digest}. "
            "The file changed at the source or the download was corrupted."
        )
    if spec.metadata_url:
        _download(spec.metadata_url, target_dir / Path(spec.metadata_url).name, 60.0)

    loaded = extract_member(dest, spec.extract, target_dir) if spec.extract else dest
    result = RetrievedFile(
        path=loaded,
        sha256=digest,
        bytes=dest.stat().st_size,
        url=spec.url,
        retrieved_at=datetime.now(tz=UTC),
        loaded_sha256=sha256_of(loaded),
    )
    sidecar_path(loaded).write_text(json.dumps(result.to_json(), indent=2))
    return result


def default_file_for(manifest: Manifest, raw_dir: Path | None = None) -> Path | None:
    """Where `fetch` would have saved the file to load, if it exists."""
    spec = manifest.download
    name = Path(spec.extract).name if spec.extract else spec.file_name
    if not name:
        return None
    p = (raw_dir or get_settings().raw_dir) / manifest.key / name
    return p if p.exists() else None
