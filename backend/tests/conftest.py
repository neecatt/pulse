from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pulse.config import Settings
from pulse.main import create_app
from pulse.services.container import Services
from pulse.slurm.mock import MockSlurmClient

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
async def app(settings: Settings, clock: FakeClock) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings, slurm_client=MockSlurmClient(clock), clock=clock, run_poller=False
    )
    async with application.router.lifespan_context(application):
        yield application


ADMIN = {"username": "admin", "password": "correct horse battery"}


@pytest.fixture
async def anon(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client that isn't signed in."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def setup_body(app: FastAPI, credentials: dict[str, str] = ADMIN) -> dict[str, str]:
    """First-run setup request, with the one-time code the server logged."""
    return credentials | {"setup_code": app.state.services.setup_code}


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client signed in as the admin created through first-run setup."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/api/auth/setup", json=setup_body(app))
        assert response.status_code == 201, response.text
        yield c


@pytest.fixture
def services(app: FastAPI) -> Services:
    services: Services = app.state.services
    return services
