"""A public site (PULSE_DEMO): demo guests on simulated clusters next to real
accounts, and sign-up with just a passkey."""

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from pulse.config import Settings
from pulse.constants import DEMO_GUEST_TTL_SECONDS
from pulse.main import create_app
from pulse.models import LoginSession, utcnow
from pulse.services import demo
from pulse.services.container import Services
from pulse.slurm import AccountRef, AccountSnapshot, HostKeys, WithSimulated, create_slurm_client
from pulse.slurm.base import Cursors
from pulse.slurm.mock import MockSlurmClient
from tests.conftest import FakeClock
from tests.softauthn import SoftAuthenticator


class RealClusters:
    """Stands in for SSH: records every account it's asked to reach."""

    def __init__(self) -> None:
        self.reached: list[str] = []

    def public_key_for(self, user_id: int) -> str | None:
        return "ssh-ed25519 AAAA"

    async def check(self, account: AccountRef) -> HostKeys:
        self.reached.append(account.host)
        return HostKeys()

    async def snapshot(self, account: AccountRef, cursors: Cursors) -> AccountSnapshot:
        self.reached.append(account.host)
        return AccountSnapshot(jobs=[], telemetry={})

    async def close(self) -> None:
        return None


@pytest.fixture
def real() -> RealClusters:
    return RealClusters()


@pytest.fixture
async def site(settings: Settings, clock: FakeClock, real: RealClusters) -> AsyncIterator[FastAPI]:
    settings.demo = True
    settings.allow_signup = True
    application = create_app(
        settings,
        slurm_client=WithSimulated(real, MockSlurmClient(clock)),
        clock=clock,
        run_poller=False,
    )
    async with application.router.lifespan_context(application):
        yield application


def new_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_guest_gets_simulated_clusters_and_never_reaches_real_ones(
    site: FastAPI, real: RealClusters, clock: FakeClock
) -> None:
    services: Services = site.state.services
    async with new_client(site) as guest:
        status = (await guest.get("/api/auth/status")).json()
        assert status["demo"] is True and status["user"] is None
        me = (await guest.post("/api/auth/demo")).json()
        assert me["is_guest"] is True and me["username"].startswith("guest-")
        accounts = (await guest.get("/api/accounts")).json()
        assert {a["cluster"] for a in accounts} == {"LUMI", "Leonardo"}

        # Even an account the guest adds with a real host stays simulated.
        added = await guest.post("/api/accounts", json={"username": "me", "host": "lumi.csc.fi"})
        assert added.status_code == 201
        assert (await guest.post(f"/api/accounts/{added.json()['id']}/check")).json()["ok"]
        await services.poller.poll_all()
        clock.advance(600)
        await services.poller.poll_all()
        assert real.reached == []
        jobs = (await guest.get("/api/jobs")).json()
        assert {j["state"] for j in jobs} >= {"RUNNING", "PENDING"}  # a live story at once
        assert (await guest.get("/api/events")).json()  # and things already happened

        # Temporary: no password or passkey to keep it.
        assert (
            await guest.post("/api/auth/password", json={"new_password": "a long password"})
        ).status_code == 403
        assert (await guest.post("/api/auth/passkeys/register/options")).status_code == 403

        # Gone after a day, with everything in it.
        clock.advance(DEMO_GUEST_TTL_SECONDS)
        await services.poller.poll_all()
        assert (await guest.get("/api/auth/me")).status_code == 401


async def test_real_accounts_on_a_demo_site_use_real_clusters(
    site: FastAPI, real: RealClusters
) -> None:
    services: Services = site.state.services
    async with new_client(site) as user:
        signed_up = await user.post(
            "/api/auth/signup", json={"username": "ada", "password": "a long password"}
        )
        assert signed_up.json()["is_guest"] is False
        await user.post("/api/accounts", json={"username": "ada", "host": "lumi.csc.fi"})
        await services.poller.poll_all()
    assert real.reached == ["lumi.csc.fi"]


async def test_guests_are_their_own_sandboxes(site: FastAPI, real: RealClusters) -> None:
    services: Services = site.state.services
    async with new_client(site) as one, new_client(site) as two:
        await one.post("/api/auth/demo")
        await two.post("/api/auth/demo")
        await services.poller.poll_all()
        theirs = {a["id"] for a in (await two.get("/api/accounts")).json()}
        mine = {a["id"] for a in (await one.get("/api/accounts")).json()}
        assert mine and theirs and not mine & theirs
        mine_jobs = {j["id"] for j in (await one.get("/api/jobs")).json()}
        assert mine_jobs and not mine_jobs & {j["id"] for j in (await two.get("/api/jobs")).json()}


async def test_no_demo_unless_enabled(anon: AsyncClient) -> None:
    assert (await anon.post("/api/auth/demo")).status_code == 404


async def signup_with_passkey(client: AsyncClient, key: SoftAuthenticator, username: str):  # type: ignore[no-untyped-def]
    started = await client.post("/api/auth/passkeys/signup/options", json={"username": username})
    if started.status_code != 200:
        return started
    credential = key.create(started.json()["options"])
    return await client.post(
        "/api/auth/passkeys/signup/verify",
        json={"challenge_id": started.json()["challenge_id"], "credential": credential},
    )


async def test_sign_up_with_just_a_passkey(site: FastAPI) -> None:
    phone = SoftAuthenticator("http://test")
    async with new_client(site) as first:
        created = await signup_with_passkey(first, phone, "grace")
        assert created.status_code == 201, created.text
        assert created.json()["has_password"] is False and created.json()["is_guest"] is False
        assert [p["name"] for p in (await first.get("/api/auth/passkeys")).json()] == ["Passkey"]

        # A backup password can be added later, without a current one.
        assert (
            await first.post("/api/auth/password", json={"new_password": "a long password"})
        ).status_code == 204
        assert (await first.get("/api/auth/me")).json()["has_password"] is True

    async with new_client(site) as later:
        started = (await later.post("/api/auth/passkeys/login/options")).json()
        credential = phone.get(started["options"])
        signed_in = await later.post(
            "/api/auth/passkeys/login/verify",
            json={"challenge_id": started["challenge_id"], "credential": credential},
        )
        assert signed_in.json()["username"] == "grace"
        password = await later.post(
            "/api/auth/login", json={"username": "grace", "password": "a long password"}
        )
        assert password.status_code == 200

    async with new_client(site) as someone_else:
        taken = await signup_with_passkey(someone_else, SoftAuthenticator("http://test"), "grace")
        assert taken.status_code == 409


async def test_passkey_sign_up_follows_the_sign_up_switch(anon: AsyncClient) -> None:
    refused = await signup_with_passkey(anon, SoftAuthenticator("http://test"), "grace")
    assert refused.status_code == 403  # sign-ups are off by default


async def test_an_account_without_a_password_cannot_be_signed_into_with_one(
    site: FastAPI,
) -> None:
    async with new_client(site) as first:
        await signup_with_passkey(first, SoftAuthenticator("http://test"), "grace")
    async with new_client(site) as guesser:
        for attempt in ("", "a long password"):
            response = await guesser.post(
                "/api/auth/login", json={"username": "grace", "password": attempt}
            )
            assert response.status_code == 401


async def test_the_oldest_guests_make_way_when_there_are_too_many(
    site: FastAPI, monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    monkeypatch.setattr(demo, "DEMO_MAX_GUESTS", 2)
    clients = [new_client(site) for _ in range(3)]
    for c in clients:
        assert (await c.post("/api/auth/demo")).status_code == 201
        clock.advance(1)
    alive = [(await c.get("/api/auth/me")).status_code for c in clients]
    assert alive == [401, 200, 200]
    for c in clients:
        await c.aclose()


async def test_guests_cannot_mint_real_accounts_or_upload_data(site: FastAPI) -> None:
    services: Services = site.state.services
    services.settings.allow_signup = False  # a demo-only site
    async with new_client(site) as guest:
        await guest.post("/api/auth/demo")
        # Invite links create real accounts even with sign-ups off: not for guests.
        assert (await guest.post("/api/teams", json={"name": "Lab"})).status_code == 403
        assert (await guest.post("/api/teams/mine/invites")).status_code == 403
        # No agent token, so no uploads into the server.
        agent = await guest.post(
            "/api/accounts", json={"username": "me", "host": "x.example", "connection": "agent"}
        )
        assert agent.status_code == 403
        # A few clusters, not thousands to poll.
        added = [
            (
                await guest.post("/api/accounts", json={"username": f"u{i}", "host": "x.example"})
            ).status_code
            for i in range(4)
        ]
        assert added == [201, 201, 201, 409]  # two came with the demo


async def test_new_accounts_are_capped_across_all_addresses(
    settings: Settings, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-address limits can be dodged behind a proxy that passes on a forged
    X-Forwarded-For; the total cap still holds."""
    monkeypatch.setattr("pulse.main.NEW_ACCOUNTS_PER_WINDOW", 2)
    settings.demo = settings.allow_signup = True
    application = create_app(
        settings, slurm_client=MockSlurmClient(clock), clock=clock, run_poller=False
    )
    async with application.router.lifespan_context(application), new_client(application) as c:
        demos = [(await c.post("/api/auth/demo")).status_code for _ in range(3)]
        assert demos == [201, 201, 429]
        signups = [
            (
                await c.post(
                    "/api/auth/signup", json={"username": f"user{i}", "password": "p" * 12}
                )
            ).status_code
            for i in range(3)
        ]
        assert signups == [201, 201, 429]  # counted apart from guests


async def test_demo_accounts_are_polled_only_while_someone_watches(
    site: FastAPI, clock: FakeClock
) -> None:
    services: Services = site.state.services
    async with new_client(site) as guest:
        me = (await guest.post("/api/auth/demo")).json()
        await services.poller.poll_all(force=False)  # first look: filled at once
        polled = {a["id"]: a["last_polled_at"] for a in (await guest.get("/api/accounts")).json()}
        clock.advance(3600)
        await services.poller.poll_all(force=False)
        after = {a["id"]: a["last_polled_at"] for a in (await guest.get("/api/accounts")).json()}
        assert after == polled  # nobody watching: nothing polled
        async with services.broadcaster.subscribe(me["id"]):
            await services.poller.poll_all(force=False)
        watched = {a["id"]: a["last_polled_at"] for a in (await guest.get("/api/accounts")).json()}
        assert all(watched[i] != polled[i] for i in polled)


def test_simulated_accounts_never_go_over_ssh_even_with_demo_off(settings: Settings) -> None:
    settings.slurm_backend = "ssh"
    settings.demo = False
    assert isinstance(create_slurm_client(settings), WithSimulated)


async def test_guests_expire_even_after_demo_is_switched_off(
    site: FastAPI, clock: FakeClock
) -> None:
    services: Services = site.state.services
    async with new_client(site) as guest:
        await guest.post("/api/auth/demo")
        services.settings.demo = False
        clock.advance(DEMO_GUEST_TTL_SECONDS + 1)
        await services.poller.poll_all()
        assert (await guest.get("/api/auth/me")).status_code == 401


async def test_a_first_password_needs_a_recent_sign_in(site: FastAPI) -> None:
    services: Services = site.state.services
    async with new_client(site) as user:
        await signup_with_passkey(user, SoftAuthenticator("http://test"), "grace")
        async with services.sessions() as session:  # the sign-in was 11 minutes ago
            await session.execute(
                update(LoginSession).values(created_at=utcnow() - timedelta(minutes=11))
            )
            await session.commit()
        stale = await user.post("/api/auth/password", json={"new_password": "a long password"})
        assert stale.status_code == 403
        assert "sign in again" in stale.json()["detail"]
