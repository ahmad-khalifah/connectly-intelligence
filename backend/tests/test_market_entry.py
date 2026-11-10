import pytest
from sqlalchemy import text

from tests.test_matching import m  # noqa: F401  (fixture: West LGAs, facility, languages, solutions)


@pytest.fixture
def me(m, session):
    ds = session.scalar(text("SELECT id FROM dataset WHERE key = 't-lgas'"))
    for name, v in (("West North", 25), ("West South", 9), ("Border", 4), ("West Central", 2)):
        session.execute(
            text(
                "INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, value_type, "
                "dataset_id, source_reference) SELECT id, 'lga', :g, '2024', :v, 'derived', :d, 'synthetic' "
                "FROM indicator WHERE code = 'health.nearest_facility_km_ward_point'"
            ),
            {"g": m["ids"][name], "v": v, "d": ds},
        )
    session.commit()
    return m


def post(m, **body):
    return m["c"].post("/api/v1/market-entry", headers=m["h"], json=body)


def test_market_entry_within_state(me):
    r = post(
        me,
        sector="health",
        need="health.telemedicine",
        product_name="Test product",
        internet_requirement="sms_ussd",
        device_requirement="basic_phone",
        power_requirement="none",
        languages=["ha"],
        distribution_channels=["health_facilities"],
        target_groups=["patients"],
        objective="pilot",
        budget_ngn=5_000_000,
        state_ids=[me["ids"]["West"]],
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["level"] == "lga" and len(d["candidates"]) == 4
    assert d["candidates"][0]["name"] == "West North"  # worst served on both health indicators
    keys = [s["key"] for s in d["sections"]]
    assert keys == [
        "areas",
        "segments",
        "demand",
        "competition",
        "community_organisations",
        "partners",
        "distribution",
        "languages",
        "communication",
        "acquisition",
        "risks",
        "strategy",
    ]
    sec = {s["key"]: s["items"] for s in d["sections"]}
    assert sec["demand"][0]["kind"] == "gap"  # demand is never estimated
    assert any("SMS Clinic" in i["text"] for i in sec["competition"])
    assert sec["languages"][0]["kind"] == "fact" and "Hausa" in sec["languages"][0]["text"]
    assert any("not compared with entry costs" in i["text"] for i in sec["risks"])
    assert (
        sec["strategy"][0]["kind"] == "recommendation"
        and "West North" in sec["strategy"][0]["text"]
    )
    assert {i["kind"] for s in d["sections"] for i in s["items"]} <= {
        "fact",
        "derived",
        "recommendation",
        "gap",
    }


def test_market_entry_from_directory_record_nationally(me, session):
    sid = session.scalar(text("SELECT id FROM solution WHERE name = 'App Clinic'"))
    d = post(me, sector="health", solution_id=sid).json()
    assert d["level"] == "state" and d["product"]["internet_requirement"] == "mobile_3g"
    strat = next(s for s in d["sections"] if s["key"] == "strategy")["items"][0]
    assert strat["kind"] in ("recommendation", "gap")


def test_market_entry_validation(me):
    assert post(me, sector="nope").status_code == 422
    assert post(me, sector="health", internet_requirement="6g").status_code == 422
    assert post(me, sector="health", languages=["xx"]).status_code == 422
    assert post(me, sector="health", objective="conquer").status_code == 422
    assert post(me, sector="health", state_ids=[me["ids"]["West North"]]).status_code == 422
    assert post(me, sector="health", solution_id=999999).status_code == 422


def test_no_recommendation_without_evidence_of_need(me):
    # East has no health indicators: areas are listed but not scored or recommended.
    d = post(me, sector="health", need="health.telemedicine", state_ids=[me["ids"]["East"]]).json()
    assert all(c["score"] is None and not c["need_evidenced"] for c in d["candidates"])
    sec = {s["key"]: s["items"] for s in d["sections"]}
    assert sec["areas"][0]["kind"] == "gap" and sec["strategy"][0]["kind"] == "gap"
