"""Test fixtures.

Tests run against a separate database (CONNECTLY_TEST_DATABASE_URL, default
`connectly_test`) that is wiped before every test. The geometries built here are
synthetic squares used only to exercise the code; they never touch the development
database.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from connectly.core.config import BACKEND_DIR
from connectly.core.db import make_sessionmaker
from connectly.ingest.manifest import Manifest, load_manifest

TEST_DB_URL = os.environ.get(
    "CONNECTLY_TEST_DATABASE_URL",
    "postgresql+psycopg://connectly:connectly@localhost:5432/connectly_test",
)

# Tables owned by PostGIS or Alembic are never wiped.
KEEP_TABLES = ("alembic_version", "spatial_ref_sys")


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if "connectly_test" not in TEST_DB_URL and not os.environ.get("CONNECTLY_ALLOW_ANY_TEST_DB"):
        pytest.exit("refusing to run tests against a database not named *connectly_test*")
    eng = create_engine(TEST_DB_URL, future=True)
    cfg = alembic_config(TEST_DB_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND NOT (tablename = ANY(:keep))"
                ),
                {"keep": list(KEEP_TABLES)},
            )
            .scalars()
            .all()
        )
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    s = make_sessionmaker(engine)()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# --------------------------------------------------------------------------- geometry


def box(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
    }


def feature(name: str | None, code: str | None, geometry: dict | None, **props) -> dict:
    return {
        "type": "Feature",
        "properties": {"shapeName": name, "shapeID": code, **props},
        "geometry": geometry,
    }


def write_geojson(path: Path, features: list[dict], crs: str | None = "EPSG:4326") -> Path:
    fc: dict = {"type": "FeatureCollection", "features": features}
    if crs:
        fc["crs"] = {"type": "name", "properties": {"name": crs}}
    path.write_text(json.dumps(fc))
    return path


# Synthetic layout inside Nigeria's bounding box:
#   country  : lon 10–14, lat 7–11
#   states   : West (10–12), East (12–14)
#   LGAs     : four quadrants per state; "Border" straddles the state line (80% West)
COUNTRY = [feature("Testland", "C1", box(10, 7, 14, 11))]
STATES = [
    feature("West", "S1", box(10, 7, 12, 11), shapeISO="T-W"),
    feature("East", "S2", box(12, 7, 14, 11), shapeISO="T-E"),
]
LGAS = [
    feature("West North", "L1", box(10, 9, 11, 11)),
    feature("West South", "L2", box(10, 7, 11, 9)),
    feature("Border", "L3", box(11, 9, 12.25, 11)),
    feature("West Central", "L4", box(11, 7, 12, 9)),
    feature("East North", "L5", box(12.25, 9, 14, 11)),
    feature("East South", "L6", box(12, 7, 14, 9)),
]


@pytest.fixture
def make_manifest(tmp_path: Path) -> Callable[..., Manifest]:
    def _make(key: str, level: str, **overrides) -> Manifest:
        data = {
            "key": key,
            "kind": "admin_boundaries",
            "level": level,
            "source": {"key": "test-source", "name": "Synthetic test source"},
            "title": f"Synthetic {level} layer for tests",
            "version": "test",
            "licence": "CC BY 4.0",
            "licence_verified": True,
            "licence_evidence": "Synthetic test fixture",
            "commercial_use_allowed": True,
            "attribution": "Synthetic test data",
            "download": {"mode": "manual", "instructions": "test"},
            "fields": {"name": ["shapeName"], "code": ["shapeID"], "alias_codes": ["shapeISO"]},
        } | overrides
        p = tmp_path / f"{key}.yaml"
        p.write_text(yaml.safe_dump(data))
        return load_manifest(p)

    return _make


@pytest.fixture
def synthetic_hierarchy(session, tmp_path, make_manifest):
    """Load country, states and LGAs from the synthetic layout."""
    from connectly.ingest.boundaries import load_boundaries

    reports = {}
    for key, level, feats in (
        ("t-country", "country", COUNTRY),
        ("t-states", "state", STATES),
        ("t-lgas", "lga", LGAS),
    ):
        path = write_geojson(tmp_path / f"{key}.geojson", feats)
        reports[level] = load_boundaries(session, make_manifest(key, level), file=path)
    session.commit()
    return reports


# --------------------------------------------------------------------------- accounts

TEST_PASSWORD = "test-password-not-real-42"


def make_user(session: Session, role: str = "viewer", email: str | None = None, **kw):
    """An account with TEST_PASSWORD (hashing is slow, so the hash is computed once)."""
    from connectly.models import User

    user = User(
        email=email or f"{role}-{os.urandom(3).hex()}@example.test",
        full_name=kw.pop("full_name", f"Test {role}"),
        role=role,
        password_hash=_test_hash(),
        **kw,
    )
    session.add(user)
    session.commit()
    return user


_HASH: list[str] = []


def _test_hash() -> str:
    if not _HASH:
        from connectly.core.security import hash_password

        _HASH.append(hash_password(TEST_PASSWORD))
    return _HASH[0]


def auth_header(user) -> dict[str, str]:
    from connectly.core.security import create_token

    token, _ = create_token(user.id, user.role, user.token_version)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    from connectly.core.security import login_limiter

    login_limiter.reset()
    yield
