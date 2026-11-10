import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape
from sqlalchemy import text

from connectly.api.main import create_app
from connectly.taxonomy.seed import seed_reference_data


@pytest.fixture
def client(engine, session, synthetic_hierarchy):
    seed_reference_data(session)
    session.commit()
    return TestClient(create_app(engine))


def ids(client, **params):
    return {a["name"]: a["id"] for a in client.get("/api/v1/areas", params=params).json()}


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["migration"] == "0001"


def test_stats_match_database(client, session):
    s = client.get("/api/v1/stats").json()
    assert s["areas_by_level"] == {"country": 1, "state": 2, "lga": 6, "ward": 0}
    assert s["settlements"] is None
    assert s["observations"] == 0
    assert s["sectors"] == 8
    assert s["open_data_gaps"] == session.scalar(
        text("SELECT count(*) FROM data_gap WHERE status <> 'resolved'")
    )


def test_list_filters_and_search(client):
    states = client.get("/api/v1/areas", params={"level": "state"}).json()
    assert [s["name"] for s in states] == ["East", "West"]
    assert {s["child_count"] for s in states} == {2, 4}
    # Alias search finds the state by its code.
    assert [a["name"] for a in client.get("/api/v1/areas", params={"q": "T-E"}).json()] == ["East"]


def test_area_detail_has_breadcrumbs_provenance_and_notices(client):
    lga_id = ids(client, level="lga")["West North"]
    d = client.get(f"/api/v1/areas/{lga_id}").json()
    assert [b["name"] for b in d["breadcrumbs"]] == ["Testland", "West", "West North"]
    assert d["child_level"] == "ward" and d["child_count"] == 0
    assert d["dataset"]["key"] == "t-lgas"
    assert d["dataset"]["licence"] == "CC BY 4.0"
    codes = [n["code"] for n in d["notices"]]
    assert "geo.wards_not_loaded" in codes
    assert "geo.settlements_not_loaded" in codes
    lon, lat = d["centroid"]
    assert 10 <= lon <= 11 and 9 <= lat <= 11


def test_children_endpoint(client):
    west = ids(client, level="state")["West"]
    names = sorted(a["name"] for a in client.get(f"/api/v1/areas/{west}/children").json())
    assert names == ["Border", "West Central", "West North", "West South"]


def test_geojson_layer_is_valid(client):
    west = ids(client, level="state")["West"]
    fc = client.get("/api/v1/geojson", params={"level": "lga", "parent_id": west}).json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 4
    assert fc["attribution"] == ["Synthetic test data"]
    for f in fc["features"]:
        assert shape(f["geometry"]).is_valid
        assert f["properties"]["level"] == "lga"


def test_geojson_requires_parent_for_small_levels(client):
    assert client.get("/api/v1/geojson", params={"level": "lga"}).status_code == 400


def test_unknown_area_is_404(client):
    assert client.get("/api/v1/areas/999999").status_code == 404


def test_datasets_and_gaps(client):
    ds = {d["key"]: d for d in client.get("/api/v1/datasets").json()}
    assert ds["t-states"]["record_count"] == 2
    assert ds["t-states"]["source_name"] == "Synthetic test source"
    gaps = client.get("/api/v1/data-gaps", params={"sector": "finance"}).json()
    assert {g["code"] for g in gaps} == {"finance.agent_locations", "finance.state_level_only"}


def test_sectors_report_zero_observations(client):
    sectors = {s["code"]: s for s in client.get("/api/v1/sectors").json()}
    assert len(sectors) == 8
    assert {c for c, s in sectors.items() if s["is_priority"]} == {
        "health",
        "connectivity",
        "finance",
    }
    assert all(s["observation_count"] == 0 for s in sectors.values())
