import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from pywebpush import WebPushException

from pulse.config import Settings
from pulse.services import notifier as notifier_module
from pulse.services.container import Services
from tests.conftest import FakeClock

SUB = {"endpoint": "https://push.example.com/device-1", "keys": {"p256dh": "k", "auth": "a"}}


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        vapid_public_key="public",
        vapid_private_key="private",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    def fake_webpush(*, subscription_info: dict[str, Any], data: str, **_: Any) -> None:
        payloads.append(json.loads(data))

    monkeypatch.setattr(notifier_module, "webpush", fake_webpush)
    return payloads


async def _account_with_events(client: AsyncClient, services: Services, clock: FakeClock) -> None:
    account = await client.post(
        "/api/accounts", json={"cluster": "LUMI", "username": "alice", "host": "lumi.example.org"}
    )
    await services.poller.poll_account(account.json()["id"])
    clock.advance(300)
    await services.poller.poll_account(account.json()["id"])


async def test_events_are_pushed_respecting_preferences(
    client: AsyncClient, services: Services, clock: FakeClock, sent: list[dict[str, Any]]
) -> None:
    await client.post("/api/push/subscriptions", json=SUB)
    await client.put("/api/preferences", json={"alerts": {"job_started": False}})

    await _account_with_events(client, services, clock)

    kinds = {p["kind"] for p in sent}
    assert "job_failed" in kinds
    assert "job_started" not in kinds
    failed = next(p for p in sent if p["kind"] == "job_failed")
    assert failed["title"] == "alice@LUMI"
    assert failed["url"].startswith("/jobs/")


async def test_expired_subscriptions_are_removed(
    client: AsyncClient, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(**_: Any) -> None:
        raise WebPushException("gone", response=_Response(410))

    monkeypatch.setattr(notifier_module, "webpush", gone)
    await client.post("/api/push/subscriptions", json=SUB)

    assert (await client.post("/api/push/test")).json() == {"delivered": 0}
    # The subscription was deleted, so a working push now reaches nobody.
    monkeypatch.setattr(notifier_module, "webpush", lambda **_: None)
    assert (await client.post("/api/push/test")).json() == {"delivered": 0}


async def test_stalled_job_is_reported_once(
    client: AsyncClient, services: Services, clock: FakeClock, sent: list[dict[str, Any]]
) -> None:
    await client.post("/api/push/subscriptions", json=SUB)
    await _account_with_events(client, services, clock)
    account_id = (await client.get("/api/accounts")).json()[0]["id"]

    # rl-ppo's log freezes; it is reported after PULSE_STALL_MINUTES (15) without output.
    for _ in range(3):
        clock.advance(300)
        await services.poller.poll_account(account_id)

    stalls = [p for p in sent if p["kind"] == "job_stalled"]
    assert len(stalls) == 1
    assert "rl-ppo" in stalls[0]["body"]
