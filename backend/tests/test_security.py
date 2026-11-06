"""Regression tests for the security review (request limits, SSRF, isolation)."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pulse import constants
from pulse.auth.rate_limit import LoginRateLimiter
from pulse.auth.webauthn import ChallengeStore
from pulse.config import Settings
from pulse.metrics.hparams import parse_config
from pulse.services.container import Services


async def test_oversized_body_is_refused_before_it_is_read(client: AsyncClient) -> None:
    huge = b"x" * (constants.MAX_REQUEST_BYTES + 1)
    response = await client.post(
        "/api/auth/login", content=huge, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_oversized_chunked_body_is_cut_off(client: AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:  # no Content-Length: counted as it arrives
        for _ in range(constants.MAX_REQUEST_BYTES // 65536 + 2):
            yield b"x" * 65536

    response = await client.post(
        "/api/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_agent_reports_get_a_larger_limit(client: AsyncClient) -> None:
    body = b"x" * (constants.MAX_REQUEST_BYTES * 2)
    response = await client.post(
        constants.AGENT_REPORT_PATH, content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code != 413  # read in full; rejected for other reasons

    too_big = b"x" * (constants.MAX_AGENT_REPORT_BYTES + 1)
    response = await client.post(
        constants.AGENT_REPORT_PATH, content=too_big, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_setup_info_needs_sign_in(anon: AsyncClient) -> None:
    # It carries the signed-in user's own SSH public key.
    assert (await anon.get("/api/setup")).status_code == 401


@pytest.mark.parametrize(
    ("endpoint", "accepted"),
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/abc", True),
        ("https://web.push.apple.com/QOc_abc", True),
        ("https://wns2-db5p.notify.windows.com/w/?token=abc", True),
        ("https://169.254.169.254/latest/meta-data", False),  # cloud metadata
        ("https://127.0.0.1:8000/api/auth/logout", False),
        ("https://internal.example.org/admin", False),
        ("https://fcm.googleapis.com.evil.example/x", False),  # lookalike host
        ("https://evilfcm.googleapis.com.example/x", False),
        ("https://fcm.googleapis.com:8443/x", False),  # unusual port
        ("https://user@fcm.googleapis.com/x", False),
    ],
)
async def test_push_subscriptions_only_reach_browser_push_services(
    client: AsyncClient, endpoint: str, accepted: bool
) -> None:
    body = {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}
    response = await client.post("/api/push/subscriptions", json=body)
    assert response.status_code == (204 if accepted else 422)


def test_push_delivery_follows_no_redirects(services: Services) -> None:
    assert services.notifier._http.max_redirects == 0


def test_rate_limiter_memory_is_bounded() -> None:
    limiter = LoginRateLimiter(max_failures=3, window_seconds=60, max_keys=100)
    for i in range(1000):
        assert not limiter.blocked(f"user:probe-{i}")  # looking up stores nothing
    assert len(limiter._failures) == 0
    for i in range(1000):
        limiter.record_failure(f"user:spray-{i}")
    assert len(limiter._failures) <= 100

    for _ in range(3):
        limiter.record_failure("ip:1.2.3.4")
    assert limiter.blocked("ip:1.2.3.4")  # still limits what it tracks


def test_passkey_challenges_are_capped() -> None:
    store = ChallengeStore(max_pending=50)
    ids = [store.issue(b"c", "login") for _ in range(500)]
    assert len(store._pending) == 50
    assert store.take(ids[-1], "login") is not None  # the newest still works


async def test_signups_are_limited_per_address(app: FastAPI, settings: Settings) -> None:
    settings.allow_signup = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        statuses = [
            (
                await anon.post(
                    "/api/auth/signup", json={"username": f"spam{i}", "password": "p" * 12}
                )
            ).status_code
            for i in range(constants.SIGNUPS_PER_ADDRESS + 2)
        ]
    assert statuses[: constants.SIGNUPS_PER_ADDRESS] == [201] * constants.SIGNUPS_PER_ADDRESS
    assert statuses[-1] == 429


async def test_setup_code_guesses_are_limited(anon: AsyncClient, settings: Settings) -> None:
    body = {"username": "admin", "password": "p" * 12, "setup_code": "0000-0000-0000"}
    statuses = [
        (await anon.post("/api/auth/setup", json=body)).status_code
        for _ in range(settings.login_max_failures + 1)
    ]
    assert statuses[0] == 403 and statuses[-1] == 429


def test_self_referencing_config_does_not_recurse_forever() -> None:
    hparams = parse_config("config.yaml", b"model: &m {lr: 0.1, again: *m}\nseed: 3\n")
    assert hparams["seed"] == 3
    assert hparams["model.lr"] == 0.1  # read as far as the depth limit


def test_dev_origin_is_not_trusted_by_default() -> None:
    assert Settings(_env_file=None).cors_origins == []  # type: ignore[call-arg]


async def test_no_public_map_of_the_api(anon: AsyncClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = await anon.get(path)
        assert response.status_code == 404, path
        assert "openapi" not in response.text.lower()
