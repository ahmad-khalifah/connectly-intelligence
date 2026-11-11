"""Nationwide coverage rules.

A dataset produces values only in the states it covers, a national file is never assumed to
cover every state, and overlapping datasets are never double-counted.
"""

import dataclasses
import json

import pytest
from sqlalchemy import text

from connectly.ingest import derive, points
from connectly.ingest.common import LoadError
from connectly.models import Dataset
from tests.test_community_ingest import obs, points_manifest, seeded, wards  # noqa: F401

PER_10K = {d.indicator: d for d in derive.DERIVATIONS}["health.facilities_per_10k"]

# Synthetic layout (tests/conftest.py): wards Alpha and Beta are in state West,
# Gamma is in state East. Alpha has a modelled population of 10,000.
IN_ALPHA = [("A1", 10.25, 10.0), ("A2", 10.3, 10.1)]
IN_GAMMA = [("G1", 13.0, 8.0)]


def load(session, tmp_path, make_manifest, key, pts, **manifest_kw):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": c, "name": c, "type": "PHC", "status": None},
                "geometry": {"type": "Point", "coordinates": [x, y]},
            }
            for c, x, y in pts
        ],
    }
    path = tmp_path / f"{key}.geojson"
    path.write_text(json.dumps(fc))
    m = points_manifest(make_manifest, key, facility_kind="health")
    if manifest_kw:
        m = dataclasses.replace(m, **manifest_kw)
    return points.load_points(session, m, file=path)


def coverage_names(session, key):
    ds = session.query(Dataset).filter_by(key=key).one()
    return sorted(
        session.execute(
            text("SELECT name FROM admin_area WHERE id = ANY(:i)"),
            {"i": ds.extra["coverage_state_ids"]},
        ).scalars()
    ), ds.extra["coverage_method"]


def test_national_file_covers_only_states_with_records(seeded, wards, tmp_path, make_manifest):
    report = load(seeded, tmp_path, make_manifest, "t-west-only", IN_ALPHA)
    assert coverage_names(seeded, "t-west-only") == (
        ["West"],
        "states with at least one record in the file",
    )
    assert any("covers 1 of 2 states; not covered: East" in w for w in report.warnings)
    derive.run_derivation(seeded, PER_10K)
    per = obs(seeded, "health.facilities_per_10k", "ward")
    assert per["Alpha"].value == pytest.approx(2.0)
    # East has no records in this file: "no data", never zero.
    assert "Gamma" not in per


def test_declared_coverage_wins_and_flags_records_outside(seeded, wards, tmp_path, make_manifest):
    report = load(
        seeded, tmp_path, make_manifest, "t-declared", IN_ALPHA + IN_GAMMA, coverage_states=["T-E"]
    )
    assert coverage_names(seeded, "t-declared") == (["East"], "declared by the publisher")
    assert any("outside the declared coverage (West)" in w for w in report.warnings)
    derive.run_derivation(seeded, PER_10K)
    per = obs(seeded, "health.facilities_per_10k", "ward")
    assert "Alpha" not in per and "Gamma" in per


def test_unknown_declared_state_stops_the_load(seeded, wards, tmp_path, make_manifest):
    with pytest.raises(LoadError, match="match no single loaded state"):
        load(seeded, tmp_path, make_manifest, "t-bad", IN_ALPHA, coverage_states=["Atlantis"])


def test_overlapping_sources_use_one_dataset_per_state(seeded, wards, tmp_path, make_manifest):
    # A preferred source covering West, and a broader source that repeats the same two
    # West clinics and adds one in East.
    load(seeded, tmp_path, make_manifest, "t-primary", IN_ALPHA, priority=10)
    load(
        seeded,
        tmp_path,
        make_manifest,
        "t-secondary",
        [(f"S-{c}", x, y) for c, x, y in IN_ALPHA] + IN_GAMMA,
        priority=50,
    )
    derive.run_derivation(seeded, PER_10K)
    per = obs(seeded, "health.facilities_per_10k", "ward")
    # Two clinics per 10,000 people, not four: West uses only the preferred source.
    assert per["Alpha"].value == pytest.approx(2.0)
    # East is still covered, by the only source that covers it.
    assert "Gamma" in per
    out = seeded.query(Dataset).filter_by(key="derived-health.facilities_per_10k").one()
    assert out.extra["sources_by_state"] == {
        "East": {"facilities": "t-secondary"},
        "West": {"facilities": "t-primary"},
    }


def test_partial_boundary_release_activates_only_in_its_states(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    from connectly.ingest.boundaries import load_boundaries
    from tests.conftest import LGAS, write_geojson

    # A newer LGA release for West only (codes changed, same shapes).
    west = [f for f in LGAS if f["properties"]["shapeName"].startswith("West")]
    for f in west:
        f["properties"]["shapeID"] = "NEW-" + f["properties"]["shapeID"]
    path = write_geojson(tmp_path / "west-lgas.geojson", west)
    report = load_boundaries(
        session, make_manifest("t-lgas-west-v2", "lga"), file=path, activate="yes"
    )
    assert any("activated in 1 of 2 states" in w for w in report.warnings)

    active = dict(
        session.execute(
            text(
                "SELECT a.name, d.key FROM admin_area a JOIN dataset d ON d.id = a.dataset_id "
                "WHERE a.level = 'lga' AND a.active"
            )
        ).all()
    )
    # West now uses the new release; East keeps its LGAs from the original dataset.
    assert active["West North"] == "t-lgas-west-v2"
    assert active["East North"] == "t-lgas" and active["East South"] == "t-lgas"
    # The old dataset is still in use in East, so it is not marked superseded.
    status = session.scalar(text("SELECT status FROM dataset WHERE key = 't-lgas'"))
    assert status == "loaded"


def test_coverage_endpoint_reports_each_state(seeded, wards, tmp_path, make_manifest, engine):
    from fastapi.testclient import TestClient

    from connectly.api.main import create_app
    from tests.conftest import auth_header, make_user

    load(seeded, tmp_path, make_manifest, "t-west-only", IN_ALPHA)
    seeded.commit()
    client = TestClient(create_app(engine))
    client.headers.update(auth_header(make_user(seeded)))
    body = client.get("/api/v1/coverage").json()
    assert body["states_total"] == 2
    layers = {layer["code"]: layer["states_covered"] for layer in body["layers"]}
    assert layers["health"] == 1 and layers["settlements"] == 0
    by_state = {s["name"]: s["layers"] for s in body["states"]}
    assert by_state["West"]["health"] == {"covered": True, "records": 2, "source": "t-west-only"}
    assert by_state["East"]["health"] == {"covered": False, "records": 0, "source": None}
