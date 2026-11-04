from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from pulse.auth.passwords import hash_password, verify_password
from pulse.config import Settings
from pulse.main import create_app
from tests.conftest import ADMIN, setup_body


def test_password_hashing() -> None:
    stored = hash_password("s3cret-password")
    assert stored.startswith("scrypt$")
    assert verify_password("s3cret-password", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "garbage")
    assert hash_password("same") != hash_password("same")  # salted


async def test_api_requires_sign_in(anon: AsyncClient) -> None:
    for path in ("/api/jobs", "/api/accounts", "/api/runs", "/api/stream", "/api/auth/me"):
        assert (await anon.get(path)).status_code == 401, path
    assert (await anon.get("/api/health")).status_code == 200  # stays public
    assert (await anon.get("/api/agent/script")).status_code == 200


async def test_first_run_setup_needs_the_logged_code(app: FastAPI, anon: AsyncClient) -> None:
    wrong = await anon.post("/api/auth/setup", json=ADMIN | {"setup_code": "0000-0000-0000"})
    assert wrong.status_code == 403
    code = app.state.services.setup_code
    relaxed = code.lower().replace("-", " ")  # typed loosely still works
    assert (
        await anon.post("/api/auth/setup", json=ADMIN | {"setup_code": relaxed})
    ).status_code == 201


async def test_first_run_setup_then_locked(app: FastAPI, anon: AsyncClient) -> None:
    assert (await anon.get("/api/auth/status")).json() == {
        "setup_required": True,
        "signup_allowed": False,
        "user": None,
    }
    created = await anon.post("/api/auth/setup", json=setup_body(app))
    assert created.status_code == 201
    assert created.json()["is_admin"] is True
    assert "httponly" in created.headers["set-cookie"].lower()
    assert "samesite=lax" in created.headers["set-cookie"].lower()
    assert (await anon.get("/api/auth/me")).json()["username"] == "admin"
    assert (await anon.get("/api/auth/status")).json()["user"]["username"] == "admin"

    again = await anon.post(
        "/api/auth/setup", json=setup_body(app, {"username": "eve", "password": "x" * 12})
    )
    assert again.status_code == 409
    assert (await anon.get("/api/auth/status")).json()["setup_required"] is False


async def test_login_logout(client: AsyncClient, anon: AsyncClient) -> None:
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/jobs")).status_code == 401

    wrong = await anon.post("/api/auth/login", json=ADMIN | {"password": "nope"})
    assert wrong.status_code == 401
    assert (await anon.post("/api/auth/login", json=ADMIN)).status_code == 200
    assert (await anon.get("/api/jobs")).status_code == 200


async def test_weak_credentials_are_rejected(app: FastAPI, anon: AsyncClient) -> None:
    short = await anon.post(
        "/api/auth/setup", json=setup_body(app, {"username": "admin", "password": "short"})
    )
    assert short.status_code == 422
    bad_name = await anon.post(
        "/api/auth/setup", json=setup_body(app, {"username": "a b", "password": "x" * 12})
    )
    assert bad_name.status_code == 422


async def test_failed_logins_are_rate_limited(client: AsyncClient, anon: AsyncClient) -> None:
    for _ in range(10):
        await anon.post("/api/auth/login", json=ADMIN | {"password": "wrong-guess"})
    blocked = await anon.post("/api/auth/login", json=ADMIN)  # even the right password
    assert blocked.status_code == 429


async def test_password_change_signs_out_other_devices(
    client: AsyncClient, anon: AsyncClient
) -> None:
    await anon.post("/api/auth/login", json=ADMIN)
    sessions = (await client.get("/api/auth/sessions")).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1

    wrong = await client.post(
        "/api/auth/password", json={"current_password": "nope", "new_password": "x" * 12}
    )
    assert wrong.status_code == 403
    new = {"current_password": ADMIN["password"], "new_password": "a brand new password"}
    assert (await client.post("/api/auth/password", json=new)).status_code == 204

    assert (await anon.get("/api/jobs")).status_code == 401  # other device signed out
    assert (await client.get("/api/jobs")).status_code == 200  # this one stays


async def test_users_only_see_their_own_data(app: FastAPI, settings: Settings) -> None:
    settings.allow_signup = True
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as alice,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob,
    ):
        await alice.post(
            "/api/auth/setup", json=setup_body(app, {"username": "alice", "password": "x" * 12})
        )
        signup = await bob.post("/api/auth/signup", json={"username": "bob", "password": "y" * 12})
        assert signup.status_code == 201 and signup.json()["is_admin"] is False

        account = await alice.post(
            "/api/accounts", json={"username": "alice", "host": "cluster.example.org"}
        )
        assert (await bob.get("/api/accounts")).json() == []
        assert (await bob.delete(f"/api/accounts/{account.json()['id']}")).status_code == 404


async def test_signup_disabled_by_default(client: AsyncClient, anon: AsyncClient) -> None:
    response = await anon.post("/api/auth/signup", json={"username": "eve", "password": "x" * 12})
    assert response.status_code == 403


async def test_cross_site_writes_are_blocked(client: AsyncClient) -> None:
    body = {"username": "alice", "host": "cluster.example.org"}
    evil = await client.post("/api/accounts", json=body, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    same = await client.post("/api/accounts", json=body, headers={"Origin": "http://test"})
    assert same.status_code == 201
    reads = await client.get("/api/accounts", headers={"Origin": "https://evil.example"})
    assert reads.status_code == 200  # CORS, not this check, governs reads


@pytest.fixture
def env_admin_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'env.db'}",
        admin_username="root",
        admin_password=SecretStr("from-the-env-file"),
        _env_file=None,  # type: ignore[call-arg]
    )


async def test_admin_from_environment(env_admin_settings: Settings) -> None:
    app = create_app(env_admin_settings, run_poller=False)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        assert (await http.get("/api/auth/status")).json()["setup_required"] is False
        login = await http.post(
            "/api/auth/login", json={"username": "root", "password": "from-the-env-file"}
        )
        me = login.json()
        assert me["is_admin"] and me["password_from_env"]
        change = await http.post(
            "/api/auth/password",
            json={"current_password": "from-the-env-file", "new_password": "x" * 12},
        )
        assert change.status_code == 409  # managed by the environment

    # Changing the variable and restarting replaces the password and signs out.
    env_admin_settings.admin_password = SecretStr("rotated-in-env-file")
    app2 = create_app(env_admin_settings, run_poller=False)
    async with (
        app2.router.lifespan_context(app2),
        AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as http2,
    ):
        old = await http2.post(
            "/api/auth/login", json={"username": "root", "password": "from-the-env-file"}
        )
        assert old.status_code == 401
        new = await http2.post(
            "/api/auth/login", json={"username": "root", "password": "rotated-in-env-file"}
        )
        assert new.status_code == 200


async def test_security_headers(anon: AsyncClient) -> None:
    response = await anon.get("/api/health")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in response.headers  # plain http here


async def test_hsts_over_https(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as https:
        response = await https.get("/api/health")
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_short_admin_password_is_rejected_at_startup() -> None:
    with pytest.raises(ValueError, match="at least 10 characters") as error:
        Settings(admin_username="admin", admin_password="tooShort!", _env_file=None)  # type: ignore[call-arg]
    assert "tooShort!" not in str(error.value)  # the secret never reaches logs


async def test_no_setup_code_once_an_admin_is_configured(env_admin_settings: Settings) -> None:
    app = create_app(env_admin_settings, run_poller=False)
    async with app.router.lifespan_context(app):
        assert app.state.services.setup_code is None


def test_port_follows_platform_port_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "4321")  # e.g. injected by Railway
    assert Settings(_env_file=None).port == 4321  # type: ignore[call-arg]
    monkeypatch.setenv("PULSE_PORT", "9000")  # an explicit PULSE_PORT wins
    assert Settings(_env_file=None).port == 9000  # type: ignore[call-arg]
