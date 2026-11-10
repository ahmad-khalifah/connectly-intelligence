import textwrap

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from connectly.api.main import create_app
from connectly.services.directory import DirectoryError
from connectly.services.directory_import import import_directory
from connectly.taxonomy.seed import seed_reference_data
from tests.conftest import auth_header, make_user


@pytest.fixture
def d(engine, session, synthetic_hierarchy):
    seed_reference_data(session)
    session.commit()
    ids = dict(session.execute(text("SELECT name, id FROM admin_area")).all())
    return {
        "c": TestClient(create_app(engine)),
        "ids": ids,
        "admin": make_user(session, "admin"),
        "viewer": make_user(session, "viewer"),
        "company": make_user(session, "company"),
        "other_company": make_user(session, "company"),
        "session": session,
    }


ORG = {
    "name": "Sahel Health Tech",
    "org_type": "startup",
    "industry": "Digital health",
    "website": "https://sahel.example.org",
    "headquarters": "Yola",
    "headquarters_country": "ng",
    "source_description": "Synthetic record for tests",
}


def solution(**kw):
    return {
        "name": "ClinicLink",
        "sector": "health",
        "need_codes": ["health.telemedicine"],
        "summary": "Remote consultations for primary health centres.",
        "beneficiary_groups": ["patients", "health_facilities"],
        "pricing_model": "subscription",
        "price_min_ngn": 5000,
        "price_max_ngn": 20000,
        "price_unit": "per facility per month",
        "internet_requirement": "mobile_3g",
        "device_requirement": "smartphone",
        "languages": ["en", "ha"],
        "distribution_channels": ["health_facilities"],
        "source_description": "Synthetic record for tests",
    } | kw


def as_(d, who):
    return auth_header(d[who])


def test_vocabularies(d):
    v = d["c"].get("/api/v1/directory/vocabularies", headers=as_(d, "viewer")).json()
    assert v["languages"]["ha"] == "Hausa"
    health = next(s for s in v["sectors"] if s["code"] == "health")
    assert {"code": "health.telemedicine", "name": "Telemedicine"} in health["needs"]


def test_admin_publishes_and_viewer_sees_only_published(d):
    c = d["c"]
    org = c.post("/api/v1/organisations", headers=as_(d, "admin"), json=ORG).json()
    assert org["status"] == "active" and org["headquarters_country"] == "NG"
    assert org["slug"] == "sahel-health-tech"
    body = solution(coverage=[{"area_id": d["ids"]["West"]}])
    sol = c.post(f"/api/v1/organisations/{org['id']}/solutions", headers=as_(d, "admin"), json=body)
    assert sol.status_code == 201, sol.text
    sol = sol.json()
    assert sol["status"] == "draft" and sol["need_codes"] == ["health.telemedicine"]
    assert sol["coverage"][0]["name"] == "West"

    assert c.get("/api/v1/solutions", headers=as_(d, "viewer")).json() == []
    assert c.get(f"/api/v1/solutions/{sol['id']}", headers=as_(d, "viewer")).status_code == 404

    pub = c.post(
        f"/api/v1/solutions/{sol['id']}/status",
        headers=as_(d, "admin"),
        json={"status": "published"},
    ).json()
    assert pub["status"] == "published" and pub["published_at"]
    listed = c.get(
        "/api/v1/solutions", headers=as_(d, "viewer"), params={"sector": "health"}
    ).json()
    assert [s["name"] for s in listed] == ["ClinicLink"]
    assert (
        c.get("/api/v1/solutions", headers=as_(d, "viewer"), params={"sector": "finance"}).json()
        == []
    )


def test_availability_by_area(d):
    c, ids = d["c"], d["ids"]
    org = c.post("/api/v1/organisations", headers=as_(d, "admin"), json=ORG).json()
    specs = {
        "Everywhere": {"nationwide": True},
        "WestOnly": {"coverage": [{"area_id": ids["West"]}]},
        "WestNorthOnly": {"coverage": [{"area_id": ids["West North"]}]},
        "Planned": {"coverage": [{"area_id": ids["East"], "kind": "expansion_interest"}]},
        "NoCoverage": {},
    }
    for name, extra in specs.items():
        s = c.post(
            f"/api/v1/organisations/{org['id']}/solutions",
            headers=as_(d, "admin"),
            json=solution(name=name, **extra),
        ).json()
        c.post(
            f"/api/v1/solutions/{s['id']}/status",
            headers=as_(d, "admin"),
            json={"status": "published"},
        )

    def av(area):
        rows = c.get(
            "/api/v1/solutions", headers=as_(d, "viewer"), params={"area_id": ids[area]}
        ).json()
        return {r["name"]: r["availability"] for r in rows}

    west_north = av("West North")
    assert west_north == {
        "Everywhere": "nationwide",
        "WestOnly": "covers_area",
        "WestNorthOnly": "covers_area",
        "Planned": "not_available",
        "NoCoverage": "unknown",
    }
    west = av("West")
    assert west["WestNorthOnly"] == "covers_part"
    east = av("East North")
    assert east["Planned"] == "expansion_interest" and east["WestOnly"] == "not_available"
    only = c.get(
        "/api/v1/solutions",
        headers=as_(d, "viewer"),
        params={"area_id": ids["East North"], "available_only": True},
    ).json()
    assert [r["name"] for r in only] == ["Everywhere"]


def test_company_self_submission(d):
    c = d["c"]
    org = c.post("/api/v1/organisations", headers=as_(d, "company"), json=ORG).json()
    assert org["status"] == "submitted"
    d["session"].refresh(d["company"])
    assert d["company"].organisation_id == org["id"]
    # A second organisation for the same account is refused.
    assert (
        c.post(
            "/api/v1/organisations", headers=as_(d, "company"), json=ORG | {"name": "Second Org"}
        ).status_code
        == 409
    )
    # Viewers cannot see a submitted organisation.
    assert c.get(f"/api/v1/organisations/{org['id']}", headers=as_(d, "viewer")).status_code == 404

    sol = c.post(
        f"/api/v1/organisations/{org['id']}/solutions", headers=as_(d, "company"), json=solution()
    ).json()
    # Companies cannot publish themselves.
    r = c.post(
        f"/api/v1/solutions/{sol['id']}/status",
        headers=as_(d, "company"),
        json={"status": "published"},
    )
    assert r.status_code == 403
    r = c.post(
        f"/api/v1/solutions/{sol['id']}/status",
        headers=as_(d, "company"),
        json={"status": "submitted"},
    )
    assert r.json()["status"] == "submitted"
    # Another company cannot touch it.
    assert (
        c.put(
            f"/api/v1/solutions/{sol['id']}", headers=as_(d, "other_company"), json=solution()
        ).status_code
        == 403
    )
    # Admin must approve the organisation before publishing.
    r = c.post(
        f"/api/v1/solutions/{sol['id']}/status",
        headers=as_(d, "admin"),
        json={"status": "published"},
    )
    assert r.status_code == 409
    c.post(
        f"/api/v1/organisations/{org['id']}/review",
        headers=as_(d, "admin"),
        json={
            "status": "active",
            "verification_status": "source_verified",
            "note": "Checked CAC registration",
        },
    )
    c.post(
        f"/api/v1/solutions/{sol['id']}/status",
        headers=as_(d, "admin"),
        json={"status": "published"},
    )
    c.post(
        f"/api/v1/solutions/{sol['id']}/verify",
        headers=as_(d, "admin"),
        json={"verification_status": "source_verified", "note": "Matches the company website"},
    )
    # A company edit to a published solution sends it back for review.
    r = c.put(
        f"/api/v1/solutions/{sol['id']}",
        headers=as_(d, "company"),
        json=solution(summary="Remote consultations and referrals for PHCs."),
    ).json()
    assert r["status"] == "submitted" and r["verification_status"] == "unverified"
    assert c.get("/api/v1/solutions", headers=as_(d, "viewer")).json() == []
    # The owner still sees it.
    assert len(c.get("/api/v1/solutions", headers=as_(d, "company")).json()) == 1
    log = c.get("/api/v1/audit", headers=as_(d, "admin"), params={"entity_type": "solution"}).json()
    assert {"create", "status", "verify", "update"} <= {e["action"] for e in log}


def test_rejection_needs_reason_and_viewers_cannot_edit(d):
    c = d["c"]
    org = c.post("/api/v1/organisations", headers=as_(d, "admin"), json=ORG).json()
    sol = c.post(
        f"/api/v1/organisations/{org['id']}/solutions", headers=as_(d, "admin"), json=solution()
    ).json()
    assert (
        c.post(
            f"/api/v1/solutions/{sol['id']}/status",
            headers=as_(d, "admin"),
            json={"status": "rejected"},
        ).status_code
        == 422
    )
    assert (
        c.put(
            f"/api/v1/solutions/{sol['id']}", headers=as_(d, "viewer"), json=solution()
        ).status_code
        == 403
    )
    assert c.post("/api/v1/organisations", headers=as_(d, "viewer"), json=ORG).status_code == 403


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"sector": "space"}, "unknown sector"),
        ({"need_codes": ["health.teleportation"]}, "unknown need codes"),
        ({"languages": ["xx"]}, "languages"),
        ({"internet_requirement": "5g"}, "internet_requirement"),
        ({"price_min_ngn": 10, "price_max_ngn": 5}, "price_max_ngn"),
        ({"price_min_ngn": -1}, "price_min_ngn"),
        ({"source_description": ""}, "source_description"),
        ({"website": "ftp://x"}, "website"),
        ({"coverage": [{"area_id": 999999}]}, "coverage area"),
    ],
)
def test_solution_validation(d, override, fragment):
    c = d["c"]
    org = c.post("/api/v1/organisations", headers=as_(d, "admin"), json=ORG).json()
    r = c.post(
        f"/api/v1/organisations/{org['id']}/solutions",
        headers=as_(d, "admin"),
        json=solution(**override),
    )
    assert r.status_code == 422
    assert fragment in r.text


def test_country_level_coverage_is_refused(d):
    c = d["c"]
    org = c.post("/api/v1/organisations", headers=as_(d, "admin"), json=ORG).json()
    r = c.post(
        f"/api/v1/organisations/{org['id']}/solutions",
        headers=as_(d, "admin"),
        json=solution(coverage=[{"area_id": d["ids"]["Testland"]}]),
    )
    assert r.status_code == 422 and "nationwide" in r.text


def test_company_account_linking(d):
    c = d["c"]
    org = c.post("/api/v1/organisations", headers=as_(d, "admin"), json=ORG).json()
    r = c.post(
        "/api/v1/users",
        headers=as_(d, "admin"),
        json={
            "email": "ops@sahel.example.org",
            "full_name": "Ops",
            "role": "viewer",
            "organisation_id": org["id"],
        },
    )
    assert r.status_code == 422
    r = c.post(
        "/api/v1/users",
        headers=as_(d, "admin"),
        json={
            "email": "ops@sahel.example.org",
            "full_name": "Ops",
            "role": "company",
            "organisation_id": org["id"],
        },
    )
    assert r.status_code == 201 and r.json()["user"]["organisation_id"] == org["id"]


def test_language_claims_need_codes(d):
    c = d["c"]
    researcher = make_user(d["session"], "researcher")
    base = {
        "subject_type": "admin_area",
        "subject_id": d["ids"]["West North"],
        "attribute": "languages",
        "value_text": "Hausa and Fulfulde are widely spoken",
        "value_type": "measured",
        "source_description": "Field visit by the research team",
    }
    assert c.post("/api/v1/claims", headers=auth_header(researcher), json=base).status_code == 422
    assert (
        c.post(
            "/api/v1/claims", headers=auth_header(researcher), json=base | {"value_codes": ["zz"]}
        ).status_code
        == 422
    )
    ok = c.post(
        "/api/v1/claims", headers=auth_header(researcher), json=base | {"value_codes": ["ha", "ff"]}
    )
    assert ok.status_code == 201 and ok.json()["value_codes"] == ["ha", "ff"]
    other = base | {"attribute": "market_days", "value_codes": ["ha"]}
    assert c.post("/api/v1/claims", headers=auth_header(researcher), json=other).status_code == 422


# ------------------------------------------------------------------------- import


def write(tmp_path, body):
    p = tmp_path / "directory.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_import_creates_then_updates(d, tmp_path):
    s = d["session"]
    path = write(
        tmp_path,
        """
        organisations:
          - name: Sahel Health Tech
            org_type: startup
            headquarters_country: NG
            headquarters_state: West
            source_description: Synthetic record for tests
            solutions:
              - name: ClinicLink
                status: published
                sector: health
                need_codes: [health.telemedicine]
                summary: Remote consultations for primary health centres.
                languages: [en, ha]
                source_description: Synthetic record for tests
                coverage:
                  - {state: West}
                  - {state: West, lga: West North, kind: expansion_interest}
        """,
    )
    r = import_directory(s, path)
    s.commit()
    assert (r.organisations_created, r.solutions_created) == (1, 1)
    row = s.execute(text("SELECT status, published_at IS NOT NULL FROM solution")).one()
    assert row == ("published", True)
    assert s.scalar(text("SELECT count(*) FROM solution_coverage")) == 2
    r2 = import_directory(s, path)
    s.commit()
    assert (r2.organisations_updated, r2.solutions_updated, r2.solutions_created) == (1, 1, 0)
    assert s.scalar(text("SELECT count(*) FROM audit_log WHERE action = 'import'")) == 4


def test_import_is_all_or_nothing(d, tmp_path):
    s = d["session"]
    path = write(
        tmp_path,
        """
        organisations:
          - name: Good Org
            org_type: ngo
            source_description: Synthetic record for tests
          - name: Bad Org
            org_type: ngo
            source_description: Synthetic record for tests
            solutions:
              - name: Thing
                sector: health
                summary: A solution with an unknown state in its coverage.
                source_description: Synthetic record for tests
                coverage: [{state: Atlantis}]
        """,
    )
    with pytest.raises(DirectoryError, match="Atlantis"):
        import_directory(s, path)
    s.rollback()
    assert s.scalar(text("SELECT count(*) FROM organisation")) == 0
