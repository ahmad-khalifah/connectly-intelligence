import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from connectly.api.main import create_app
from connectly.services.needs import NeedsError, _percentiles, assess
from connectly.taxonomy.seed import seed_reference_data
from tests.conftest import auth_header, make_user


@pytest.fixture
def ctx(session, synthetic_hierarchy):
    seed_reference_data(session)
    session.commit()
    ids = dict(session.execute(text("SELECT name, id FROM admin_area")).all())
    ds = session.scalar(text("SELECT id FROM dataset WHERE key = 't-lgas'"))

    def put(code, level, name, value, value_type="measured"):
        session.execute(
            text(
                "INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, "
                "value_type, dataset_id, source_reference) SELECT id, :l, :g, '2024', :v, :t, :d, "
                "'synthetic' FROM indicator WHERE code = :c"
            ),
            {"c": code, "l": level, "g": ids[name], "v": value, "t": value_type, "d": ds},
        )

    for name, v in (("West North", 1), ("West South", 2), ("Border", 3), ("West Central", 4)):
        put("connectivity.sites_per_10k", "lga", name, v)
    for name, v in (("West North", 30), ("West South", 20), ("Border", 10)):
        put("connectivity.nearest_tower_km_ward_point", "lga", name, v, "derived")
    put("connectivity.households_mobile_phone_pct", "state", "West", 70)
    session.commit()
    return ids


def test_percentiles_with_ties():
    assert _percentiles({1: 5, 2: 5, 3: 1}, higher_is_worse=True) == {1: 75.0, 2: 75.0, 3: 0.0}
    assert _percentiles({1: 5, 2: 1}, higher_is_worse=False) == {1: 0.0, 2: 100.0}
    assert _percentiles({7: 3}, higher_is_worse=True) == {7: 50.0}


def test_connectivity_ranking(session, ctx):
    r = assess(session, "connectivity", "lga", ctx["West"])
    assert r["status"] == "ok" and r["areas_in_scope"] == 4 and r["areas_scored"] == 4
    by = {a["name"]: a for a in r["areas"]}
    wn = by["West North"]
    assert wn["rank"] == 1 and wn["score"] == 100.0
    assert wn["coverage"] == 0.7
    assert wn["confidence"] == pytest.approx(0.7 * (0.35 * 0.9 + 0.35 * 0.85 * 0.9) / 0.7, abs=0.01)
    assert wn["confidence_label"] == "medium"
    assert by["West South"]["score"] == pytest.approx((66.7 + 50) / 2, abs=0.1)
    wc = by["West Central"]
    assert wc["score"] == 0.0 and wc["confidence_label"] == "low" and wc["rank"] == 4
    assert {m["indicator"] for m in wc["missing"]} == {
        "connectivity.nearest_tower_km_ward_point",
        "connectivity.households_mobile_phone_pct",
    }
    mobile = next(
        i for i in r["indicators"] if i["code"] == "connectivity.households_mobile_phone_pct"
    )
    assert not mobile["used"] and "measured only at state level" in mobile["reason"]
    assert "worse than 100% of LGAs in West" in wn["components"][0]["statement"]


def test_too_little_data_gives_no_score(session, ctx):
    # Only one LGA has a value: too few to rank, so nobody is scored.
    session.execute(
        text(
            "INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, value_type, "
            "dataset_id, source_reference) SELECT i.id, 'lga', :g, '2024', 2, 'measured', "
            "(SELECT id FROM dataset WHERE key='t-lgas'), 'synthetic' FROM indicator i "
            "WHERE i.code = 'commerce.markets_per_10k'"
        ),
        {"g": ctx["West North"]},
    )
    session.commit()
    r = assess(session, "commerce", "lga", ctx["West"])
    assert r["status"] == "insufficient" and all(a["score"] is None for a in r["areas"])
    assert "too few to compare" in r["indicators"][0]["reason"]


def test_sector_without_model(session, ctx):
    r = assess(session, "agriculture", "lga", ctx["West"])
    assert r["status"] == "no_model" and r["areas"] == []


def test_scope_validation(session, ctx):
    with pytest.raises(NeedsError):
        assess(session, "health", "state", ctx["West"])
    with pytest.raises(NeedsError):
        assess(session, "nonsense", "lga", ctx["West"])


def test_api(engine, session, ctx):
    c = TestClient(create_app(engine))
    h = auth_header(make_user(session))
    models = c.get("/api/v1/needs/models", headers=h).json()
    health = next(m for m in models if m["sector"] == "health")
    assert sum(i["weight"] for i in health["indicators"]) == pytest.approx(1.0)
    r = c.get(
        "/api/v1/needs/assessment",
        headers=h,
        params={"sector": "connectivity", "level": "lga", "scope_id": ctx["West"]},
    )
    assert r.status_code == 200 and r.json()["areas"][0]["name"] == "West North"
    s = c.get(f"/api/v1/needs/areas/{ctx['West North']}", headers=h).json()
    conn = next(x for x in s["sectors"] if x["sector"] == "connectivity")
    assert conn["result"]["rank"] == 1 and conn["scope"]["name"] == "West"
    assert c.get("/api/v1/needs/areas/999999", headers=h).status_code == 404
    assert (
        c.get(
            "/api/v1/needs/assessment", params={"sector": "health", "level": "lga", "scope_id": 1}
        ).status_code
        == 401
    )


def test_geojson_within_ancestor(engine, session, ctx):
    c = TestClient(create_app(engine))
    h = auth_header(make_user(session))
    r = c.get("/api/v1/geojson", headers=h, params={"level": "lga", "within_id": ctx["Testland"]})
    assert len(r.json()["features"]) == 6
    assert c.get("/api/v1/geojson", headers=h, params={"level": "lga"}).status_code == 400
