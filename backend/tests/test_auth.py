from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from connectly.api.main import create_app
from connectly.core import security
from connectly.core.config import Settings
from connectly.models import User
from tests.conftest import TEST_PASSWORD, auth_header, make_user


@pytest.fixture
def app_client(engine, session):
    return TestClient(create_app(engine))


def login(client, email, password=TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_health_is_public_and_data_needs_sign_in(app_client):
    assert app_client.get("/health").status_code == 200
    for path in ("/api/v1/stats", "/api/v1/areas", "/api/v1/claims", "/api/v1/indicators"):
        r = app_client.get(path)
        assert r.status_code == 401, path
        assert r.headers["www-authenticate"] == "Bearer"


def test_security_headers(app_client):
    h = app_client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"


def test_login_and_me(app_client, session):
    user = make_user(session, "researcher", email="ada@example.test")
    r = login(app_client, "  ADA@example.test ")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "researcher"
    assert "password_hash" not in body["user"]
    me = app_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.json()["email"] == "ada@example.test"
    session.refresh(user)
    assert user.last_login_at is not None
    actions = session.scalars(text("SELECT action FROM audit_log")).all()
    assert actions == ["login"]


def test_wrong_password_and_unknown_email_look_the_same(app_client, session):
    make_user(session, email="ada@example.test")
    a = login(app_client, "ada@example.test", "wrong-password-123")
    b = login(app_client, "nobody@example.test", "wrong-password-123")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_account_locks_after_repeated_failures(app_client, session):
    user = make_user(session, email="ada@example.test")
    for _ in range(5):
        assert login(app_client, "ada@example.test", "wrong-password-123").status_code == 401
    # Locked: even the right password is refused.
    assert login(app_client, "ada@example.test").status_code == 429
    session.refresh(user)
    assert user.locked_until is not None
    # Lock expires.
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert login(app_client, "ada@example.test").status_code == 200


def test_per_address_limit(app_client, session, monkeypatch):
    monkeypatch.setattr(
        "connectly.api.routers.auth.get_settings",
        lambda: Settings(login_ip_limit=3, login_ip_window_seconds=60),
    )
    for _ in range(3):
        login(app_client, "x@example.test", "wrong-password-123")
    assert login(app_client, "x@example.test", "wrong-password-123").status_code == 429


def test_disabled_account_cannot_sign_in_or_use_old_token(app_client, session):
    user = make_user(session, email="ada@example.test")
    headers = auth_header(user)
    assert app_client.get("/api/v1/stats", headers=headers).status_code == 200
    user.is_active = False
    session.commit()
    assert login(app_client, "ada@example.test").status_code == 401
    assert app_client.get("/api/v1/stats", headers=headers).status_code == 401


def test_tampered_expired_and_foreign_tokens(app_client, session):
    user = make_user(session)
    good = auth_header(user)["Authorization"].split()[1]
    header, payload, sig = good.split(".")
    bad_sig = ".".join([header, payload, sig[:-2] + ("AA" if sig[-2:] != "AA" else "BB")])
    expired = jwt.encode(
        {"sub": str(user.id), "tv": 0, "iat": 0, "exp": 1, "iss": "connectly-intelligence"},
        security.signing_key(),
        algorithm="HS256",
    )
    other_key = jwt.encode(
        {"sub": str(user.id), "tv": 0, "iat": 0, "exp": 2**31, "iss": "connectly-intelligence"},
        "x" * 40,
        algorithm="HS256",
    )
    none_alg = jwt.encode(
        {"sub": str(user.id), "tv": 0, "iat": 0, "exp": 2**31, "iss": "connectly-intelligence"},
        None,
        algorithm="none",
    )
    for token in (bad_sig, expired, other_key, none_alg, "garbage"):
        r = app_client.get("/api/v1/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token


def test_logout_everywhere_revokes_tokens(app_client, session):
    user = make_user(session)
    headers = auth_header(user)
    assert app_client.post("/api/v1/auth/logout-all", headers=headers).status_code == 204
    assert app_client.get("/api/v1/stats", headers=headers).status_code == 401


def test_temporary_password_must_be_changed(app_client, session):
    user = make_user(session, email="ada@example.test", must_change_password=True)
    token = login(app_client, "ada@example.test").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert app_client.get("/api/v1/stats", headers=headers).status_code == 403
    assert app_client.get("/api/v1/auth/me", headers=headers).json()["must_change_password"]

    weak = app_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422 and "12 characters" in weak.json()["detail"]
    wrong = app_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "nope-nope-nope", "new_password": "a-much-better-passphrase"},
    )
    assert wrong.status_code == 400

    r = app_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": TEST_PASSWORD, "new_password": "a-much-better-passphrase"},
    )
    assert r.status_code == 200
    new_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert app_client.get("/api/v1/stats", headers=new_headers).status_code == 200
    # The old token was revoked by the change.
    assert app_client.get("/api/v1/auth/me", headers=headers).status_code == 401
    session.refresh(user)
    assert not user.must_change_password
    assert security.verify_password("a-much-better-passphrase", user.password_hash)


def test_password_rules():
    assert security.password_problems("a-much-better-passphrase") == []
    assert security.password_problems("aaaaaaaaaaaaaaaa")  # too few different characters
    assert security.password_problems("adekola-secret-1", "adekola@example.test")


def test_production_requires_a_strong_secret():
    with pytest.raises(security.InsecureConfiguration):
        security.signing_key(Settings(environment="production", secret_key=None))
    with pytest.raises(security.InsecureConfiguration):
        security.signing_key(Settings(secret_key="too-short"))
    assert security.signing_key(Settings(secret_key="k" * 40)) == "k" * 40


def test_passwords_are_hashed_with_argon2(session):
    user = make_user(session)
    assert user.password_hash.startswith("$argon2id$")
    assert TEST_PASSWORD not in user.password_hash


# ------------------------------------------------------------------ administration


def test_only_admins_manage_users(app_client, session):
    viewer = make_user(session, "viewer")
    researcher = make_user(session, "researcher")
    for u in (viewer, researcher):
        assert app_client.get("/api/v1/users", headers=auth_header(u)).status_code == 403
        assert app_client.get("/api/v1/audit", headers=auth_header(u)).status_code == 403


def test_admin_creates_user_with_temporary_password(app_client, session):
    admin = make_user(session, "admin")
    h = auth_header(admin)
    r = app_client.post(
        "/api/v1/users",
        headers=h,
        json={"email": "New.Person@Example.org", "full_name": "New Person", "role": "researcher"},
    )
    assert r.status_code == 201
    temp = r.json()["temporary_password"]
    assert r.json()["user"]["email"] == "new.person@example.org"
    assert r.json()["user"]["must_change_password"]
    assert login(app_client, "new.person@example.org", temp).status_code == 200
    dup = app_client.post(
        "/api/v1/users",
        headers=h,
        json={"email": "new.person@example.org", "full_name": "Again", "role": "viewer"},
    )
    assert dup.status_code == 409
    bad_role = app_client.post(
        "/api/v1/users",
        headers=h,
        json={"email": "x@example.org", "full_name": "X Y", "role": "superuser"},
    )
    assert bad_role.status_code == 422
    log = app_client.get("/api/v1/audit", headers=h, params={"entity_type": "user"}).json()
    assert any(e["action"] == "create" and e["actor"] == admin.email for e in log)
    # The temporary password is never written to the audit log.
    assert temp not in str(log)


def test_role_change_revokes_sessions_and_is_audited(app_client, session):
    admin = make_user(session, "admin")
    user = make_user(session, "researcher")
    old = auth_header(user)
    r = app_client.patch(
        f"/api/v1/users/{user.id}", headers=auth_header(admin), json={"role": "viewer"}
    )
    assert r.status_code == 200 and r.json()["role"] == "viewer"
    assert app_client.get("/api/v1/stats", headers=old).status_code == 401
    entry = app_client.get(
        "/api/v1/audit", headers=auth_header(admin), params={"action": "update"}
    ).json()[0]
    assert entry["changes"] == {"before": {"role": "researcher"}, "after": {"role": "viewer"}}


def test_last_admin_cannot_be_removed(app_client, session):
    admin = make_user(session, "admin")
    h = auth_header(admin)
    assert (
        app_client.patch(
            f"/api/v1/users/{admin.id}", headers=h, json={"role": "viewer"}
        ).status_code
        == 409
    )
    assert (
        app_client.patch(
            f"/api/v1/users/{admin.id}", headers=h, json={"is_active": False}
        ).status_code
        == 409
    )
    second = make_user(session, "admin")
    assert (
        app_client.patch(
            f"/api/v1/users/{second.id}", headers=h, json={"role": "viewer"}
        ).status_code
        == 200
    )


def test_admin_resets_password(app_client, session):
    admin = make_user(session, "admin")
    user = make_user(session, "viewer", email="ada@example.test")
    old = auth_header(user)
    r = app_client.post(f"/api/v1/users/{user.id}/reset-password", headers=auth_header(admin))
    assert r.status_code == 200
    assert app_client.get("/api/v1/stats", headers=old).status_code == 401
    assert login(app_client, "ada@example.test").status_code == 401
    assert login(app_client, "ada@example.test", r.json()["temporary_password"]).status_code == 200
    session.expire_all()
    assert session.get(User, user.id).must_change_password
