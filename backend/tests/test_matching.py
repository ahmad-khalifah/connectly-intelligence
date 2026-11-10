import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from connectly.api.main import create_app
from tests.conftest import auth_header, make_user
from tests.test_directory import ORG, solution


@pytest.fixture
def m(engine, session, synthetic_hierarchy):
    from connectly.taxonomy.seed import seed_reference_data

    seed_reference_data(session)
    session.commit()
    ids = dict(session.execute(text("SELECT name, id FROM admin_area")).all())
    ds = session.scalar(text("SELECT id FROM dataset WHERE key = 't-lgas'"))

    def put(code, level, name, value):
        session.execute(
            text(
                "INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, "
                "value_type, dataset_id, source_reference) SELECT id, :l, :g, '2024', :v, "
                "'measured', :d, 'synthetic' FROM indicator WHERE code = :c"
            ),
            {"c": code, "l": level, "g": ids[name], "v": value, "d": ds},
        )

    for name, v in (("West North", 0.2), ("West South", 2), ("Border", 3), ("West Central", 4)):
        put("health.facilities_per_10k", "lga", name, v)
    put("connectivity.households_mobile_phone_pct", "state", "West", 60)
    put("energy.households_electricity_pct", "state", "West", 40)
    session.execute(
        text(
            "INSERT INTO facility (kind, source_code, dataset_id, geom, lga_id, state_id) VALUES "
            "('health', 'F1', :d, ST_SetSRID(ST_MakePoint(10.5, 10), 4326), :l, :s)"
        ),
        {"d": ds, "l": ids["West North"], "s": ids["West"]},
    )
    session.execute(
        text(
            "INSERT INTO claim (subject_type, subject_id, attribute, value_text, value_codes, "
            "value_type, source_description) VALUES ('admin_area', :s, 'languages', "
            "'Hausa and Fulfulde', ARRAY['ha','ff'], 'measured', 'synthetic')"
        ),
        {"s": ids["West"]},
    )
    session.commit()

    c = TestClient(create_app(engine))
    admin = auth_header(make_user(session, "admin"))
    org = c.post("/api/v1/organisations", headers=admin, json=ORG).json()

    def add(publish=True, **kw):
        s = c.post(f"/api/v1/organisations/{org['id']}/solutions", headers=admin, json=solution(**kw))
        assert s.status_code == 201, s.text
        if publish:
            c.post(f"/api/v1/solutions/{s.json()['id']}/status", headers=admin, json={"status": "published"})

    add(
        name="SMS Clinic",
        need_codes=["health.telemedicine"],
        internet_requirement="sms_ussd",
        device_requirement="basic_phone",
        power_requirement="none",
        languages=["ha"],
        distribution_channels=["health_facilities"],
        pricing_model="free",
        price_min_ngn=None,
        price_max_ngn=None,
        beneficiary_groups=["patients"],
        literacy_requirement="none",
        coverage=[{"area_id": ids["West"]}],
    )
    add(
        name="App Clinic",
        need_codes=["health.telemedicine"],
        internet_requirement="mobile_3g",
        device_requirement="smartphone",
        power_requirement="grid",
        languages=["en"],
        distribution_channels=["direct_digital"],
        pricing_model="subscription",
        price_min_ngn=5000,
        price_max_ngn=5000,
        beneficiary_groups=["health_workers"],
    )
    add(name="Records", need_codes=["health.health_records"])
    add(name="Wallet", sector="finance", need_codes=["finance.digital_payments"])
    add(name="Unpublished", need_codes=["health.telemedicine"], publish=False)
    return {"c": c, "ids": ids, "h": auth_header(make_user(session, "viewer"))}


def run(m, **body):
    r = m["c"].post("/api/v1/matching", headers=m["h"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_needs_from_gap_evidence_and_ranking(m):
    r = run(m, area_id=m["ids"]["West North"], sector="health", target_groups=["patients"], max_price_ngn=3000)
    assert r["needs_basis"] == "gap_evidence"
    assert "health.telemedicine" in {n["code"] for n in r["target_needs"]}
    assert r["gap_evidence"] and "worse than 100%" in r["gap_evidence"][0]
    names = [x["solution"]["name"] for x in r["results"]]
    assert names == ["SMS Clinic", "App Clinic"]  # unpublished and other sectors are not considered
    assert [e["name"] for e in r["excluded"]] == ["Records"]

    sms = {c["key"]: c for c in r["results"][0]["criteria"]}
    assert sms["language"]["score"] == 1.0 and "Hausa" in sms["language"]["reason"]
    assert sms["availability"]["score"] == 1.0
    assert sms["distribution"]["score"] == 1.0 and "1 health facilities" in sms["distribution"]["reason"]
    assert sms["affordability"]["score"] == 1.0
    assert sms["suitability"]["score"] == 1.0

    app = {c["key"]: c for c in r["results"][1]["criteria"]}
    assert app["language"]["score"] == 0.2
    assert app["availability"]["score"] is None  # coverage not stated: unknown, not a fail
    assert app["affordability"]["score"] == 0.5  # ₦5,000 vs ₦3,000 ceiling
    assert "smartphone ownership is not measured" in app["connectivity"]["reason"]
    assert app["feasibility"]["score"] == pytest.approx((0.4 + 0.6) / 2)
    assert r["results"][1]["confidence"] < r["results"][0]["confidence"]
    assert any("Coverage not stated" in c for c in r["results"][1]["cautions"])


def test_selected_need_and_unclear_needs(m):
    r = run(m, area_id=m["ids"]["East North"], sector="health")
    assert r["status"] == "needs_unclear" and r["results"] == []
    r = run(m, area_id=m["ids"]["East North"], sector="health", need="health.health_records")
    assert r["needs_basis"] == "selected"
    assert [x["solution"]["name"] for x in r["results"]] == ["Records"]
    assert r["results"][0]["availability"] == "unknown"


def test_language_unknown_without_area_data(m):
    r = run(m, area_id=m["ids"]["East North"], sector="health", need="health.telemedicine")
    lang = next(c for c in r["results"][0]["criteria"] if c["key"] == "language")
    assert lang["score"] is None and "No languages are recorded" in lang["reason"]


def test_validation(m):
    c, h = m["c"], m["h"]
    assert c.post("/api/v1/matching", headers=h, json={"area_id": 999999, "sector": "health"}).status_code == 404
    assert c.post("/api/v1/matching", headers=h, json={"area_id": m["ids"]["West"], "sector": "x"}).status_code == 422
    bad = {"area_id": m["ids"]["West"], "sector": "health", "target_groups": ["aliens"]}
    assert c.post("/api/v1/matching", headers=h, json=bad).status_code == 422
