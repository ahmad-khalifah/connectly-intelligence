import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from connectly.api.main import create_app
from connectly.services.personal_data import personal_data_found
from tests.conftest import auth_header, make_user


@pytest.fixture
def ctx(engine, session, synthetic_hierarchy):
    client = TestClient(create_app(engine))
    lga = session.scalar(text("SELECT id FROM admin_area WHERE level = 'lga' LIMIT 1"))
    return {
        "client": client,
        "lga": lga,
        "author": make_user(session, "researcher", full_name="Author"),
        "reviewer": make_user(session, "researcher", full_name="Reviewer"),
        "viewer": make_user(session, "viewer"),
        "admin": make_user(session, "admin"),
    }


def claim_body(lga, **kw):
    return {
        "subject_type": "admin_area",
        "subject_id": lga,
        "attribute": "market_days",
        "value_text": "Main market every Thursday",
        "value_type": "measured",
        "source_description": "Field visit by the research team",
        "observed_on": "2026-10",
    } | kw


def post(ctx, who, body):
    return ctx["client"].post("/api/v1/claims", headers=auth_header(ctx[who]), json=body)


def test_viewer_cannot_add_claims(ctx):
    assert post(ctx, "viewer", claim_body(ctx["lga"])).status_code == 403


def test_claim_lifecycle(ctx, session):
    c = ctx["client"]
    r = post(ctx, "author", claim_body(ctx["lga"]))
    assert r.status_code == 201
    claim = r.json()
    assert claim["verification_status"] == "unverified"
    assert claim["created_by"] == "Author"
    cid = claim["id"]

    own = c.post(
        f"/api/v1/claims/{cid}/review",
        headers=auth_header(ctx["author"]),
        json={"status": "field_verified", "note": "I checked it myself"},
    )
    assert own.status_code == 403

    reviewed = c.post(
        f"/api/v1/claims/{cid}/review",
        headers=auth_header(ctx["reviewer"]),
        json={"status": "field_verified", "note": "Confirmed with the market association"},
    ).json()
    assert reviewed["verification_status"] == "field_verified"
    assert reviewed["verified_by"] == "Reviewer"

    # Someone else cannot edit; the author's edit needs a fresh review.
    assert (
        c.patch(
            f"/api/v1/claims/{cid}",
            headers=auth_header(ctx["reviewer"]),
            json={"value_text": "Fridays"},
        ).status_code
        == 403
    )
    edited = c.patch(
        f"/api/v1/claims/{cid}",
        headers=auth_header(ctx["author"]),
        json={"value_text": "Main market every Thursday and Sunday"},
    ).json()
    assert edited["verification_status"] == "unverified"
    assert edited["verified_by"] is None

    retired = c.post(
        f"/api/v1/claims/{cid}/retire",
        headers=auth_header(ctx["admin"]),
        json={"note": "Superseded by the 2027 survey"},
    ).json()
    assert retired["verification_status"] == "retired" and not retired["is_active"]

    history = c.get(f"/api/v1/claims/{cid}/history", headers=auth_header(ctx["viewer"])).json()
    assert [h["action"] for h in history] == ["create", "review", "update", "retire"]
    assert history[2]["changes"]["before"]["verification_status"] == "field_verified"

    listed = c.get(
        "/api/v1/claims",
        headers=auth_header(ctx["viewer"]),
        params={"subject_type": "admin_area", "subject_id": ctx["lga"]},
    ).json()
    assert listed == []  # retired claims are hidden by default


def test_claim_appears_in_profile(ctx):
    post(ctx, "author", claim_body(ctx["lga"]))
    p = (
        ctx["client"]
        .get(f"/api/v1/areas/{ctx['lga']}/profile", headers=auth_header(ctx["viewer"]))
        .json()
    )
    assert p["claims"][0]["attribute_label"] == "Market days"
    assert p["claims"][0]["created_by"] == "Author"
    assert p["claims"][0]["created_by_id"] == ctx["author"].id


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"attribute": "favourite_colour"}, "attribute must be one of"),
        ({"value_type": "ai_generated"}, "value_type"),
        ({"value_type": "modelled"}, "value_type"),
        ({"source_description": ""}, "source_description"),
        ({"source_url": "javascript:alert(1)"}, "source_url"),
        ({"value_text": "Ask the chief on 0803 123 4567"}, "phone number"),
        ({"value_text": "Contact chief@example.com"}, "e-mail address"),
        ({"subject_id": 999999}, "no admin_area"),
    ],
)
def test_claim_validation(ctx, override, fragment):
    r = post(ctx, "author", claim_body(ctx["lga"], **override))
    assert r.status_code in (404, 422)
    assert fragment in str(r.json()["detail"])


def test_personal_data_patterns():
    assert personal_data_found("call +234 803 123 4567") == ["a phone number"]
    assert personal_data_found("08031234567") == ["a phone number"]
    assert personal_data_found("Population 12,867 in 2019; 3 schools; 08:30 opening") == []
    assert personal_data_found("a@b.ng") == ["an e-mail address"]
