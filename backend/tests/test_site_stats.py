"""Site stats for admins: visits, demos and sign-ups counted per day, nothing
identifying stored."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from pulse.models import DailyCount
from pulse.services.container import Services
from tests.conftest import FakeClock


def new_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def today(stats: dict) -> dict:  # type: ignore[type-arg]
    return stats["days"][-1]  # type: ignore[no-any-return]


async def test_counts_visits_demos_and_signups(
    app: FastAPI, client: AsyncClient, services: Services
) -> None:
    services.settings.demo = services.settings.allow_signup = True
    async with new_client(app) as visitor:
        await visitor.get("/api/auth/status")
        await visitor.get("/api/auth/status")  # the same visitor again
        await visitor.post("/api/auth/demo")
        await visitor.post("/api/auth/logout")
        await visitor.post(
            "/api/auth/signup", json={"username": "ada", "password": "a long password"}
        )

    stats = (await client.get("/api/stats")).json()
    day = today(stats)
    assert (day["views"], day["visitors"]) == (2, 1)
    assert (day["demos"], day["signups"], day["signups_after_demo"]) == (1, 1, 1)
    assert len(stats["days"]) == 30
    assert stats["users"] == 2  # the admin and ada; the guest isn't a user
    assert stats["guests"] == 1
    assert stats["active_users"] == 2


async def test_visitors_are_new_again_the_next_day(
    app: FastAPI, client: AsyncClient, clock: FakeClock
) -> None:
    async with new_client(app) as visitor:
        await visitor.get("/api/auth/status")
        clock.advance(24 * 3600)
        await visitor.get("/api/auth/status")
    days = (await client.get("/api/stats")).json()["days"]
    assert [(d["views"], d["visitors"]) for d in days[-2:]] == [(1, 1), (1, 1)]


async def test_only_totals_are_stored(app: FastAPI, services: Services) -> None:
    async with new_client(app) as visitor:
        await visitor.get("/api/auth/status")
    async with services.sessions() as session:
        rows = (await session.execute(select(DailyCount.name, DailyCount.count))).all()
    assert sorted(rows) == [("views", 1), ("visitors", 1)]


async def test_signed_in_use_is_not_a_visit(client: AsyncClient) -> None:
    await client.get("/api/auth/status")
    assert today((await client.get("/api/stats")).json())["views"] == 0


async def test_stats_are_for_admins_only(
    app: FastAPI, client: AsyncClient, anon: AsyncClient, services: Services
) -> None:
    assert (await anon.get("/api/stats")).status_code == 401
    services.settings.allow_signup = True
    async with new_client(app) as member:
        await member.post(
            "/api/auth/signup", json={"username": "bob", "password": "a long password"}
        )
        assert (await member.get("/api/stats")).status_code == 404
