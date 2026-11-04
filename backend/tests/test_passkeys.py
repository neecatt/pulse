from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import ADMIN
from tests.softauthn import SoftAuthenticator

ORIGIN = "http://test"  # the test client's address


async def register(client: AsyncClient, authenticator: SoftAuthenticator, name: str) -> dict:  # type: ignore[type-arg]
    started = (await client.post("/api/auth/passkeys/register/options")).json()
    assert started["options"]["rp"]["id"] == "test"
    credential = authenticator.create(started["options"])
    response = await client.post(
        "/api/auth/passkeys/register/verify",
        json={"challenge_id": started["challenge_id"], "credential": credential, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def sign_in(client: AsyncClient, authenticator: SoftAuthenticator, **kwargs: str):  # type: ignore[no-untyped-def]
    started = (await client.post("/api/auth/passkeys/login/options")).json()
    assert started["options"].get("allowCredentials", []) == []  # no username needed
    credential = authenticator.get(started["options"], **kwargs)
    return await client.post(
        "/api/auth/passkeys/login/verify",
        json={"challenge_id": started["challenge_id"], "credential": credential},
    )


async def test_register_then_sign_in_without_username(
    client: AsyncClient, anon: AsyncClient
) -> None:
    phone = SoftAuthenticator(ORIGIN)
    added = await register(client, phone, "iPhone Safari")
    assert added["name"] == "iPhone Safari" and added["last_used_at"] is None

    response = await sign_in(anon, phone)
    assert response.status_code == 200, response.text
    assert response.json()["username"] == ADMIN["username"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert (await anon.get("/api/jobs")).status_code == 200

    listed = (await client.get("/api/auth/passkeys")).json()
    assert len(listed) == 1 and listed[0]["last_used_at"] is not None


async def test_passkey_from_another_site_is_rejected(
    client: AsyncClient, anon: AsyncClient
) -> None:
    phone = SoftAuthenticator(ORIGIN)
    await register(client, phone, "phone")
    phished = await sign_in(anon, phone, origin="https://evil.example")
    assert phished.status_code == 401
    assert (await anon.get("/api/jobs")).status_code == 401


async def test_challenges_are_single_use(client: AsyncClient, anon: AsyncClient) -> None:
    phone = SoftAuthenticator(ORIGIN)
    await register(client, phone, "phone")
    started = (await anon.post("/api/auth/passkeys/login/options")).json()
    credential = phone.get(started["options"])
    body = {"challenge_id": started["challenge_id"], "credential": credential}
    assert (await anon.post("/api/auth/passkeys/login/verify", json=body)).status_code == 200
    replay = await anon.post("/api/auth/passkeys/login/verify", json=body)
    assert replay.status_code == 400


async def test_unknown_or_removed_passkey_cannot_sign_in(
    client: AsyncClient, anon: AsyncClient
) -> None:
    stranger = SoftAuthenticator(ORIGIN)
    stranger.create({"rp": {"id": "test"}, "user": {"id": "AA"}, "challenge": "AA"})
    assert (await sign_in(anon, stranger)).status_code == 401

    phone = SoftAuthenticator(ORIGIN)
    added = await register(client, phone, "phone")
    assert (await client.delete(f"/api/auth/passkeys/{added['id']}")).status_code == 204
    assert (await sign_in(anon, phone)).status_code == 401


async def test_passkeys_are_per_user(app: FastAPI, client: AsyncClient) -> None:
    phone = SoftAuthenticator(ORIGIN)
    added = await register(client, phone, "phone")
    app.state.services.settings.allow_signup = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as bob:
        await bob.post("/api/auth/signup", json={"username": "bob", "password": "b" * 12})
        assert (await bob.get("/api/auth/passkeys")).json() == []
        assert (await bob.delete(f"/api/auth/passkeys/{added['id']}")).status_code == 404


async def test_registration_needs_sign_in_and_a_fresh_challenge(
    client: AsyncClient, anon: AsyncClient
) -> None:
    assert (await anon.post("/api/auth/passkeys/register/options")).status_code == 401
    started = (await client.post("/api/auth/passkeys/register/options")).json()
    credential = SoftAuthenticator(ORIGIN).create(started["options"])
    stale = await client.post(
        "/api/auth/passkeys/register/verify",
        json={"challenge_id": "made-up", "credential": credential},
    )
    assert stale.status_code == 400


async def test_public_url_pins_the_passkey_domain(app: FastAPI, client: AsyncClient) -> None:
    app.state.services.settings.public_url = "https://pulse.example.org"
    options = (await client.post("/api/auth/passkeys/register/options")).json()["options"]
    assert options["rp"]["id"] == "pulse.example.org"
