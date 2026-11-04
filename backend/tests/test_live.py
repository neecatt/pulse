import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from pulse.api.accounts import cluster_name_from_host
from pulse.config import Settings
from pulse.main import create_app
from pulse.services.container import Services
from tests.conftest import FakeClock

ACCOUNT = {"username": "alice", "host": "login.leonardo.example.org"}


@pytest.mark.parametrize(
    ("host", "name"),
    [
        ("lumi.csc.fi", "LUMI"),
        ("login.leonardo.cineca.it", "Leonardo"),
        ("login01.juwels.fz-juelich.de", "Juwels"),
        ("ssh-2.perlmutter.nersc.gov", "Perlmutter"),
        ("10.0.0.5", "10.0.0.5"),
    ],
)
def test_cluster_name_from_host(host: str, name: str) -> None:
    assert cluster_name_from_host(host) == name


async def test_cluster_name_is_derived_when_omitted(client: AsyncClient) -> None:
    created = (await client.post("/api/accounts", json=ACCOUNT)).json()
    assert created["cluster"] == "Leonardo"
    named = await client.post("/api/accounts", json=ACCOUNT | {"username": "b", "cluster": "Mine"})
    assert named.json()["cluster"] == "Mine"


async def test_setup_info_in_mock_mode(client: AsyncClient) -> None:
    assert (await client.get("/api/setup")).json() == {
        "slurm_backend": "mock",
        "ssh_public_key": None,
    }


async def test_check_records_errors_on_account(client: AsyncClient) -> None:
    account = (await client.post("/api/accounts", json=ACCOUNT | {"host": "x.invalid"})).json()
    await client.post(f"/api/accounts/{account['id']}/check")
    stored = (await client.get("/api/accounts")).json()[0]
    assert "unreachable" in stored["last_error"]


async def test_poll_cycle_publishes_one_update_per_user(
    client: AsyncClient, services: Services, clock: FakeClock
) -> None:
    a = (await client.post("/api/accounts", json=ACCOUNT)).json()
    b = (await client.post("/api/accounts", json=ACCOUNT | {"username": "bob"})).json()
    await services.poller.poll_all()  # seed silently

    user_id = 1
    async with services.broadcaster.subscribe(user_id) as queue:
        assert services.broadcaster.has_subscribers
        clock.advance(300)
        await services.poller.poll_all()
        message = json.loads(queue.get_nowait())
        assert queue.empty()

    assert not services.broadcaster.has_subscribers
    assert message["type"] == "update"
    assert sorted(message["accounts"]) == sorted([a["id"], b["id"]])
    assert {e["kind"] for e in message["events"]} >= {"job_started", "job_failed"}


async def test_poll_interval_follows_viewers(services: Services) -> None:
    poller = services.poller
    assert poller._interval() == services.settings.poll_interval_idle_seconds
    async with services.broadcaster.subscribe(1):
        assert poller._interval() == services.settings.poll_interval_live_seconds


async def test_serves_built_frontend_with_spa_fallback(tmp_path: Path) -> None:
    web = tmp_path / "dist"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>Pulse</title>")
    (web / "sw.js").write_text("// sw")
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'web.db'}",
        static_dir=web,
        _env_file=None,  # type: ignore[call-arg]
    )
    app = create_app(settings, run_poller=False)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        assert (await http.get("/api/health")).status_code == 200
        assert "Pulse" in (await http.get("/")).text
        assert "Pulse" in (await http.get("/jobs/12")).text  # client-side route
        assert (await http.get("/sw.js")).text == "// sw"
        assert (await http.get("/api/nope")).status_code == 404
