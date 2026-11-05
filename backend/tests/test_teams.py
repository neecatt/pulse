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


async def team_id(owner: AsyncClient) -> int:
    overview = (await owner.get("/api/teams")).json()
    owned = overview["owned"]
    tid: int = owned["id"] if owned else overview["memberships"][0]["team_id"]
    return tid


async def share(user: AsyncClient, account_id: int, team: int | None = None) -> None:
    team = team if team is not None else await team_id(user)
    response = await user.put(f"/api/accounts/{account_id}/shares/{team}")
    assert response.status_code == 204, response.text


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

    await share(client, account_id)

    assert {j["id"] for j in (await member.get("/api/jobs")).json()} == {j["id"] for j in jobs}
    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 200
    assert (await member.get(f"/api/jobs/{job_id}/metrics")).status_code == 200
    assert (await member.get("/api/runs")).json()
    assert (await member.get("/api/events")).json()
    [shared] = (await member.get("/api/accounts")).json()
    assert shared["owner"] == "admin"
    assert shared["shared_with"] == []  # which teams it's shared with stays private
    [own] = (await client.get("/api/accounts")).json()
    assert own["owner"] is None


async def test_members_cannot_change_anything(
    client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    await share(client, account_id)
    job_id = (await client.get("/api/jobs")).json()[0]["id"]

    writes = [
        member.patch(f"/api/jobs/{job_id}", json={"note": "mine now"}),
        member.delete(f"/api/accounts/{account_id}/shares/{await team_id(client)}"),
        member.put(f"/api/accounts/{account_id}/shares/{await team_id(client)}"),
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
    await share(client, account_id)
    job_id = (await client.get("/api/jobs")).json()[0]["id"]
    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 200

    team = (await client.get("/api/teams")).json()["owned"]
    if how == "unshare":
        await client.delete(f"/api/accounts/{account_id}/shares/{await team_id(client)}")
    elif how == "remove":
        bob = team["members"][0]["user_id"]
        assert (await client.delete(f"/api/teams/mine/members/{bob}")).status_code == 204
    elif how == "leave":
        assert (await member.delete(f"/api/teams/{team['id']}/membership")).status_code == 204
    else:
        assert (await client.delete("/api/teams/mine")).status_code == 204
        [account] = (await client.get("/api/accounts")).json()
        assert account["shared_with"] == []  # the team's shares went with it

    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 404
    assert (await member.get("/api/jobs")).json() == []


async def test_sharing_is_one_way_and_strangers_see_nothing(
    app: FastAPI, client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    await share(client, account_id)
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
    await share(client, account_id)
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
    await share(client, account_id)
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


async def test_members_use_pulse_personally_and_share_by_choice(
    app: FastAPI, client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    """An invited member is a normal user: their own accounts are private until they
    choose to share them, and then the lead and the rest of the team see them."""
    await team_with_member(client, member)
    private = await polled_account(member, services, clock)
    shared = (
        await member.post("/api/accounts", json={"username": "bob", "host": "levante.example.org"})
    ).json()["id"]
    await services.poller.poll_account(shared)
    assert (await client.get("/api/accounts")).json() == []  # private by default

    await share(member, shared)
    seen = (await client.get("/api/accounts")).json()
    assert [(a["id"], a["owner"]) for a in seen] == [(shared, "bob")]
    bob_jobs = {
        j["id"] for j in (await member.get("/api/jobs")).json() if j["account_id"] == shared
    }
    assert bob_jobs <= {j["id"] for j in (await client.get("/api/jobs")).json()}
    assert private not in {j["account_id"] for j in (await client.get("/api/jobs")).json()}

    # A third member sees it too; nobody but bob can change it.
    token = await invite(client)
    async with new_client(app) as carol:
        body = {"username": "carol", "password": "c" * 12}
        await carol.post(f"/api/teams/invites/{token}/signup", json=body)
        assert [a["owner"] for a in (await carol.get("/api/accounts")).json()] == ["bob"]
        assert (await carol.delete(f"/api/accounts/{shared}")).status_code == 404
    assert (
        await client.patch(f"/api/accounts/{shared}", json={"notify": False})
    ).status_code == 404


async def test_sharing_needs_your_account_and_your_team(
    app: FastAPI, client: AsyncClient, member: AsyncClient, services: Services
) -> None:
    await team_with_member(client, member)
    mine = await member.post("/api/accounts", json={"username": "bob", "host": "a.example.org"})
    services.settings.allow_signup = True
    async with new_client(app) as eve:
        await eve.post("/api/auth/signup", json={"username": "eve", "password": "e" * 12})
        await eve.post("/api/teams", json={"name": "Eve's team"})
        eves_team = await team_id(eve)
        # Not a member of Eve's team: can't share into it.
        refused = await member.put(f"/api/accounts/{mine.json()['id']}/shares/{eves_team}")
        assert refused.status_code == 404
        # Eve can't share Bob's account into her own team either.
        stolen = await eve.put(f"/api/accounts/{mine.json()['id']}/shares/{eves_team}")
        assert stolen.status_code == 404
        assert (await eve.get("/api/accounts")).json() == []


@pytest.mark.parametrize("how", ["removed", "leaves"])
async def test_leaving_withdraws_your_shares(
    how: str, client: AsyncClient, member: AsyncClient, services: Services
) -> None:
    await team_with_member(client, member)
    mine = await member.post("/api/accounts", json={"username": "bob", "host": "a.example.org"})
    await share(member, mine.json()["id"])
    assert len((await client.get("/api/accounts")).json()) == 1

    team = await team_id(client)
    if how == "removed":
        bob = (await client.get("/api/teams")).json()["owned"]["members"][0]["user_id"]
        await client.delete(f"/api/teams/mine/members/{bob}")
    else:
        await member.delete(f"/api/teams/{team}/membership")
    assert (await client.get("/api/accounts")).json() == []
    assert (await member.get("/api/accounts")).json()[0]["shared_with"] == []


async def test_the_owner_is_a_member_but_cannot_leave(client: AsyncClient) -> None:
    await client.post("/api/teams", json={"name": "Vision lab"})
    overview = (await client.get("/api/teams")).json()
    assert overview["owned"]["members"] == [] and overview["memberships"] == []
    team = overview["owned"]["id"]
    me = (await client.get("/api/auth/me")).json()["id"]
    assert (await client.delete(f"/api/teams/{team}/membership")).status_code == 409
    assert (await client.delete(f"/api/teams/mine/members/{me}")).status_code == 409
    toggled = await client.patch(f"/api/teams/{team}/membership", json={"alerts": True})
    assert toggled.json()["owned"]["alerts"] is True


async def share_job(user: AsyncClient, job_id: int, team: int) -> None:
    response = await user.put(f"/api/jobs/{job_id}/shares/{team}")
    assert response.status_code == 204, response.text


async def test_sharing_one_job_shows_only_that_job(
    client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    account_id = await polled_account(client, services, clock)
    team = await team_id(client)
    jobs = (await client.get("/api/jobs")).json()
    assert len(jobs) > 1
    job_id, other_id = jobs[0]["id"], jobs[1]["id"]

    await share_job(client, job_id, team)
    await share_job(client, job_id, team)  # sharing twice is harmless

    assert [j["id"] for j in (await member.get("/api/jobs")).json()] == [job_id]
    assert [r["id"] for r in (await member.get("/api/runs")).json()] == [job_id]
    assert {e["job_id"] for e in (await member.get("/api/events")).json()} <= {job_id}
    assert (await member.get(f"/api/jobs/{other_id}")).status_code == 404
    [account] = (await member.get("/api/accounts")).json()
    assert account["id"] == account_id  # for the job's label
    assert (await client.get(f"/api/jobs/{job_id}")).json()["shared_with"] == [team]
    assert (await member.get(f"/api/jobs/{job_id}")).json()["shared_with"] == []

    # Only the owner shares, and only with teams they're in.
    assert (await member.put(f"/api/jobs/{other_id}/shares/{team}")).status_code == 404
    assert (await member.delete(f"/api/jobs/{job_id}/shares/{team}")).status_code == 404
    assert (await client.put(f"/api/jobs/{job_id}/shares/{team + 1}")).status_code == 404

    assert (await client.delete(f"/api/jobs/{job_id}/shares/{team}")).status_code == 204
    assert (await member.get("/api/jobs")).json() == []
    assert (await member.get(f"/api/jobs/{job_id}")).status_code == 404


async def test_one_shared_job_sends_only_its_own_updates(
    client: AsyncClient, member: AsyncClient, services: Services, clock: FakeClock
) -> None:
    await team_with_member(client, member)
    await polled_account(client, services, clock)
    team = await team_id(client)
    job_id = (await client.get("/api/jobs")).json()[0]["id"]
    await share_job(client, job_id, team)
    bob = (await client.get("/api/teams")).json()["owned"]["members"][0]["user_id"]

    me = (await client.get("/api/auth/me")).json()["id"]

    async with (
        services.broadcaster.subscribe(bob) as theirs,
        services.broadcaster.subscribe(me) as mine,
    ):
        for _ in range(6):
            clock.advance(300)
            await services.poller.poll_all()
        seen = {
            user: [
                e["job_id"] for _ in range(q.qsize()) for e in json.loads(q.get_nowait())["events"]
            ]
            for user, q in (("bob", theirs), ("me", mine))
        }
    assert set(seen["me"]) - {job_id}  # other jobs changed meanwhile
    assert set(seen["bob"]) <= {job_id}
