import pytest

from tests.conftest import auth_header, make_user
from tests.test_matching import m  # noqa: F401


@pytest.fixture
def r(m, session):
    return m | {
        "author": auth_header(make_user(session, "researcher")),
        "other": auth_header(make_user(session, "viewer")),
        "admin": auth_header(make_user(session, "admin")),
    }


def create(r, kind, params, who="author"):
    return r["c"].post("/api/v1/reports", headers=r[who], json={"kind": kind, "params": params})


@pytest.mark.parametrize(
    "kind, params",
    [
        (
            "brief",
            lambda ids: {"area_id": ids["West North"], "sector": "health", "question": "Hausa"},
        ),
        ("needs", lambda ids: {"sector": "health", "level": "lga", "scope_id": ids["West"]}),
        (
            "matching",
            lambda ids: {
                "area_id": ids["West North"],
                "sector": "health",
                "need": "health.telemedicine",
            },
        ),
        (
            "market_entry",
            lambda ids: {
                "sector": "health",
                "need": "health.telemedicine",
                "state_ids": [ids["West"]],
                "internet_requirement": "sms_ussd",
            },
        ),
    ],
)
def test_save_and_export(r, kind, params):
    res = create(r, kind, params(r["ids"]))
    assert res.status_code == 201, res.text
    rep = res.json()
    assert rep["kind"] == kind and rep["title"]
    full = r["c"].get(f"/api/v1/reports/{rep['id']}", headers=r["author"]).json()
    assert full["result"]
    pdf = r["c"].get(f"/api/v1/reports/{rep['id']}/pdf", headers=r["author"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 3000
    assert f"connectly-{rep['id']}-" in pdf.headers["content-disposition"]


def test_access_and_delete(r):
    rep = create(
        r, "needs", {"sector": "health", "level": "lga", "scope_id": r["ids"]["West"]}
    ).json()
    c = r["c"]
    assert c.get(f"/api/v1/reports/{rep['id']}", headers=r["other"]).status_code == 404
    assert c.get(f"/api/v1/reports/{rep['id']}/pdf", headers=r["other"]).status_code == 404
    assert c.get("/api/v1/reports", headers=r["other"]).json() == []
    assert [x["id"] for x in c.get("/api/v1/reports", headers=r["admin"]).json()] == [rep["id"]]
    assert c.delete(f"/api/v1/reports/{rep['id']}", headers=r["other"]).status_code == 404
    assert c.delete(f"/api/v1/reports/{rep['id']}", headers=r["author"]).status_code == 204
    assert c.get("/api/v1/reports", headers=r["author"]).json() == []


def test_bad_parameters(r):
    assert create(r, "needs", {"sector": "health"}).status_code == 422
    assert create(r, "matching", {"area_id": r["ids"]["West"], "sector": "nope"}).status_code == 422
    assert (
        r["c"]
        .post("/api/v1/reports", headers=r["author"], json={"kind": "poem", "params": {}})
        .status_code
        == 422
    )
