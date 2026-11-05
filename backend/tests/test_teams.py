"""Teams: invites, sharing accounts read-only, live updates and alerts for members."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from pulse.models import TeamInvite
from pulse.services import notifier as notifier_module
from pulse.services.container import Services
from tests.conftest import FakeClock

MEMBER = {"username": "bob", "password": "bob's long password"}
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/bob", "keys": {"p256dh": "k", "auth": "a"}}


def new_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def member(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with new_client(app) as c:
        yield c


async def invite(owner: AsyncClient) -> str:
    response = await owner.post("/api/teams/mine/invites")
    assert response.status_code == 201, response.text
    token: str = response.json()["token"]
    return token


async def team_with_member(owner: AsyncClient, member: AsyncClient) -> None:
    """The owner creates a team; the member joins through an invite link."""
    assert (await owner.post("/api/teams", json={"name": "Vision lab"})).status_code == 201
    token = await invite(owner)
    info = await member.get(f"/api/teams/invites/{token}")
    assert info.json() == {"team": "Vision lab", "owner": "admin"}
    joined = await member.post(f"/api/teams/invites/{token}/signup", json=MEMBER)
    assert joined.status_code == 201, joined.text  # works with sign-ups disabled


async def polled_account(owner: AsyncClient, services: Services, clock: FakeClock) -> int:
    account = await owner.post(
        "/api/accounts", json={"cluster": "LUMI", "username": "alice", "host": "lumi.example.org"}
    )
    account_id: int = account.json()["id"]
    await services.poller.poll_account(account_id)
    clock.advance(300)
    await services.poller.poll_account(account_id)
    return account_id


async def test_members_see_only_what_is_shared(
    client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    jobs = (await client.get("/api/jobs")).json()
    assert jobs
    job_id = jobs[0]["id"]

    # Not shared yet: the member sees nothing.
    assert (await member.get("/api/jobs")).json() == []
    assert (await member.get("/api/accounts")).json() == []
    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 404

    await client.patch(f"/api/accounts/{account_id}", json={"shared": True})

    assert {j["id"] for j in (await member.get("/api/jobs")).json()} == {j["id"] for j in jobs}
    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 200
    assert (await member.get(f"/api/jobs/{job_id}/metrics")).status_code == 200
    assert (await member.get("/api/runs")).json()
    assert (await member.get("/api/events")).json()
    [shared] = (await member.get("/api/accounts")).json()
    assert shared["owner"] == "admin" and shared["shared"] is True
    [own] = (await client.get("/api/accounts")).json()
    assert own["owner"] is None


async def test_members_cannot_change_anything(
    client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    await client.patch(f"/api/accounts/{account_id}", json={"shared": True})
    job_id = (await client.get("/api/jobs")).json()[0]["id"]

    writes = [
        member.patch(f"/api/jobs/{job_id}", json={"note": "mine now"}),
        member.patch(f"/api/accounts/{account_id}", json={"shared": False}),
        member.delete(f"/api/accounts/{account_id}"),
        member.post(f"/api/accounts/{account_id}/check"),
        member.post(f"/api/accounts/{account_id}/agent-token"),
        member.post("/api/teams/mine/invites"),
    ]
    for write in writes:
        assert (await write).status_code == 404
    assert (await client.get(f"/api/jobs/{job_id}")).json()["note"] is None


@pytest.mark.parametrize("how", ["unshare", "remove", "leave", "delete team"])
async def test_access_ends_at_once(
    how: str, client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    await client.patch(f"/api/accounts/{account_id}", json={"shared": True})
    job_id = (await client.get("/api/jobs")).json()[0]["id"]
    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 200

    team = (await client.get("/api/teams")).json()["owned"]
    if how == "unshare":
        await client.patch(f"/api/accounts/{account_id}", json={"shared": False})
    elif how == "remove":
        bob = team["members"][0]["user_id"]
        assert (await client.delete(f"/api/teams/mine/members/{bob}")).status_code == 204
    elif how == "leave":
        assert (await member.delete(f"/api/teams/{team['id']}/membership")).status_code == 204
    else:
        assert (await client.delete("/api/teams/mine")).status_code == 204
        [account] = (await client.get("/api/accounts")).json()
        assert account["shared"] is False  # unshared with the team

    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 404
    assert (await member.get("/api/jobs")).json() == []


async def test_sharing_is_one_way_and_strangers_see_nothing(
    app: FastAPI, client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    await client.patch(f"/api/accounts/{account_id}", json={"shared": True})
    # The member's own account stays private, even from the owner.
    await member.post("/api/accounts", json={"username": "bob", "host": "levante.example.org"})
    assert len((await client.get("/api/accounts")).json()) == 1

    services.settings.allow_signup = True
    async with new_client(app) as stranger:
        await stranger.post("/api/auth/signup", json={"username": "eve", "password": "e" * 12})
        assert (await stranger.get("/api/jobs")).json() == []
        assert (await stranger.get("/api/events")).json() == []


async def test_invites_are_single_use_and_expire(
    app: FastAPI, client: AsyncClient, member: AsyncClient, services: Services
) -> None:
    await team_with_member(client, member)
    used = (await client.get("/api/teams")).json()["owned"]
    assert used["invites"] == []  # the joined invite was used up

    token = await invite(client)
    async with new_client(app) as carol:
        body = {"username": "carol", "password": "c" * 12}
        assert (
            await carol.post(f"/api/teams/invites/{token}/signup", json=body)
        ).status_code == 201
    async with new_client(app) as dave:
        body = {"username": "dave", "password": "d" * 12}
        reused = await dave.post(f"/api/teams/invites/{token}/signup", json=body)
        assert reused.status_code == 404

    expired = await invite(client)
    async with services.sessions() as session:
        await session.execute(
            update(TeamInvite).values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
        await session.commit()
    assert (await member.get(f"/api/teams/invites/{expired}")).status_code == 404
    assert (await member.get("/api/teams/invites/not-a-token")).status_code == 404

    own = await invite(client)
    assert (await client.post(f"/api/teams/invites/{own}/accept")).status_code == 409
    again = await invite(client)
    assert (await member.post(f"/api/teams/invites/{again}/accept")).status_code == 409


async def test_signed_in_users_join_with_their_account(
    app: FastAPI, client: AsyncClient, services: Services
) -> None:
    services.settings.allow_signup = True
    await client.post("/api/teams", json={"name": "Vision lab"})
    async with new_client(app) as carol:
        await carol.post("/api/auth/signup", json={"username": "carol", "password": "c" * 12})
        token = await invite(client)
        joined = await carol.post(f"/api/teams/invites/{token}/accept")
        assert joined.status_code == 200
        [membership] = joined.json()["memberships"]
        assert membership == membership | {"name": "Vision lab", "owner": "admin", "alerts": False}


async def test_members_get_live_updates(
    client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    await client.patch(f"/api/accounts/{account_id}", json={"shared": True})
    bob = (await client.get("/api/teams")).json()["owned"]["members"][0]["user_id"]

    async with services.broadcaster.subscribe(bob) as queue:
        clock.advance(300)
        await services.poller.poll_all()
        update_message = json.loads(queue.get_nowait())
    assert account_id in update_message["accounts"]


async def test_member_alerts_are_opt_in(
    client: AsyncClient,
    member: AsyncClient,
    services: Services,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def fake_webpush(*, subscription_info: dict[str, Any], data: str, **_: Any) -> None:
        sent.append((subscription_info["endpoint"], json.loads(data)))

    monkeypatch.setattr(notifier_module, "webpush", fake_webpush)
    await team_with_member(client, member)
    await member.post("/api/push/subscriptions", json=SUB)
    account = await client.post(
        "/api/accounts", json={"cluster": "LUMI", "username": "alice", "host": "lumi.example.org"}
    )
    account_id = account.json()["id"]
    await client.patch(f"/api/accounts/{account_id}", json={"shared": True})
    await services.poller.poll_account(account_id)

    clock.advance(300)
    await services.poller.poll_account(account_id)
    assert not [s for s in sent if s[0] == SUB["endpoint"]]  # off by default

    team_id = (await member.get("/api/teams")).json()["memberships"][0]["team_id"]
    await member.patch(f"/api/teams/{team_id}/membership", json={"alerts": True})
    clock.advance(300)
    await services.poller.poll_account(account_id)
    to_bob = [payload for endpoint, payload in sent if endpoint == SUB["endpoint"]]
    assert to_bob and all(p["title"].startswith("admin · alice@") for p in to_bob)
