import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from connectly.api.main import create_app
from connectly.ingest import points
from connectly.services.profiles import area_profile
from tests.test_community_ingest import points_manifest, seeded, wards  # noqa: F401


@pytest.fixture
def client(engine, seeded, wards, tmp_path, make_manifest):  # noqa: F811
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": "H1",
                    "name": "Clinic A",
                    "type": "PHC",
                    "status": "Functional",
                },
                "geometry": {"type": "Point", "coordinates": [10.2, 10.0]},
            },
        ],
    }
    path = tmp_path / "hf.geojson"
    path.write_text(json.dumps(fc))
    points.load_points(
        seeded, points_manifest(make_manifest, "t-hf2", facility_kind="health"), file=path
    )
    seeded.execute(
        text(
            "INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, value_type, "
            "dataset_id, source_reference) SELECT i.id, 'state', a.id, '2023', 61.5, 'measured', "
            "(SELECT id FROM dataset WHERE key = 't-wards'), 'synthetic' FROM indicator i, admin_area a "
            "WHERE i.code = 'finance.formal_inclusion_adults_pct' AND a.name = 'West'"
        )
    )
    seeded.commit()
    return TestClient(create_app(engine))


def area_id(session, name, level="ward"):
    return session.scalar(
        text("SELECT id FROM admin_area WHERE name = :n AND level = :l"), {"n": name, "l": level}
    )


def test_profile_separates_own_values_from_context(client, seeded):
    p = client.get(f"/api/v1/areas/{area_id(seeded, 'Alpha')}/profile").json()
    assert (p["name"], p["lga"], p["state"]) == ("Alpha", "West North", "West")
    assert p["population"]["value"] == 10000
    assert p["population"]["value_type"] == "modelled"
    ctx = {v["indicator"]: v for v in p["context_indicators"]}
    fin = ctx["finance.formal_inclusion_adults_pct"]
    assert fin["is_context"] and fin["measured_at_level"] == "state"
    assert fin["measured_at_area"] == "West"
    assert "finance.formal_inclusion_adults_pct" not in {v["indicator"] for v in p["indicators"]}
    assert p["facilities"][0]["kind"] == "health" and p["facilities"][0]["total"] == 1
    missing = {m["code"] for m in p["missing_indicators"]}
    assert "health.facilities_per_10k" in missing


def test_profile_404(client):
    assert client.get("/api/v1/areas/999999/profile").status_code == 404


def test_choropleth_lists_missing_areas(client, seeded):
    west_north = area_id(seeded, "West North", "lga")
    r = client.get(
        "/api/v1/choropleth",
        params={"indicator": "population.modelled_total", "level": "ward", "parent_id": west_north},
    ).json()
    assert {v["name"] for v in r["values"]} == {"Alpha", "Beta"}
    assert r["missing"] == []
    assert (
        client.get(
            "/api/v1/choropleth", params={"indicator": "population.modelled_total", "level": "ward"}
        ).status_code
        == 400
    )


def test_facilities_and_points_layer(client, seeded):
    wid = area_id(seeded, "Alpha")
    f = client.get("/api/v1/facilities", params={"area_id": wid}).json()
    assert f["total"] == 1 and f["items"][0]["name"] == "Clinic A"
    g = client.get("/api/v1/geojson/points", params={"area_id": wid}).json()
    assert g["features"][0]["properties"]["kind"] == "health"
    assert g["attribution"] == ["Synthetic test data"]


def test_indicator_catalogue_counts(client):
    cat = {i["code"]: i for i in client.get("/api/v1/indicators").json()}
    assert cat["population.modelled_total"]["values_by_level"]["ward"] == 3


def test_profile_service_returns_none_for_unknown(seeded):
    assert area_profile(seeded, 424242) is None
