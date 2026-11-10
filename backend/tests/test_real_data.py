"""Checks against the real boundaries loaded into the development database.

Run after `connectly bootstrap`. Skipped automatically when the data is not loaded.
These compare the loaded data with independently known facts (e.g. Adamawa has 21 LGAs).
"""

import os

import pytest
from sqlalchemy import create_engine, text

from connectly.core.config import get_settings

pytestmark = pytest.mark.real_data

ADAMAWA_LGAS = {
    "Demsa",
    "Fufore",
    "Ganye",
    "Girei",
    "Gombi",
    "Guyuk",
    "Hong",
    "Jada",
    "Lamurde",
    "Madagali",
    "Maiha",
    "Mayo-Belwa",
    "Michika",
    "Mubi North",
    "Mubi South",
    "Numan",
    "Shelleng",
    "Song",
    "Toungo",
    "Yola North",
    "Yola South",
}


@pytest.fixture(scope="module")
def dev():
    url = os.environ.get("CONNECTLY_DATABASE_URL", get_settings().database_url)
    if "connectly_test" in url:
        pytest.skip("real-data checks never run against the synthetic test database")
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            n = conn.execute(
                text("SELECT count(*) FROM admin_area WHERE level = 'lga' AND active")
            ).scalar()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"development database not reachable: {e}")
    if not n:
        pytest.skip("real boundaries not loaded; run `connectly bootstrap`")
    with eng.connect() as conn:
        yield conn
    eng.dispose()


def q(conn, sql, **params):
    return conn.execute(text(sql), params)


def test_national_counts(dev):
    counts = dict(
        q(dev, "SELECT level, count(*) FROM admin_area WHERE active GROUP BY level").all()
    )
    assert counts["country"] == 1
    assert counts["state"] == 37  # 36 states + FCT
    assert counts["lga"] == 774


def test_adamawa_has_its_21_lgas(dev):
    names = set(
        q(
            dev,
            "SELECT c.name FROM admin_area c JOIN admin_area s ON s.id = c.parent_id "
            "WHERE s.name = 'Adamawa' AND c.active",
        ).scalars()
    )
    assert names == ADAMAWA_LGAS


def test_every_lga_sits_inside_one_state(dev):
    worst = q(
        dev,
        "SELECT min(parent_overlap), count(*) FILTER (WHERE parent_id IS NULL) "
        "FROM admin_area WHERE level = 'lga' AND active",
    ).one()
    assert worst[1] == 0
    assert worst[0] >= 0.95


def test_lgas_tile_the_states(dev):
    lga_km2, state_km2 = q(
        dev,
        "SELECT (SELECT sum(area_km2) FROM admin_area WHERE level='lga' AND active), "
        "(SELECT sum(area_km2) FROM admin_area WHERE level='state' AND active)",
    ).one()
    assert abs(lga_km2 - state_km2) / state_km2 < 0.01


def test_all_geometries_valid(dev):
    assert q(dev, "SELECT bool_and(ST_IsValid(geom)) FROM admin_area WHERE active").scalar()


def test_loaded_boundaries_have_verified_licence_and_checksum(dev):
    rows = q(
        dev,
        "SELECT key, licence, licence_verified, file_sha256 FROM dataset "
        "WHERE status = 'loaded' AND coalesce(extra->>'kind', '') <> 'derived'",
    ).all()
    assert rows
    for key, licence, verified, sha in rows:
        assert licence and verified and sha and len(sha) == 64, key
