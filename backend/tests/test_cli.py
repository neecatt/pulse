import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from pulse import cli
from pulse.auth.passwords import verify_password
from pulse.config import get_settings
from pulse.db import create_engine, create_session_factory
from pulse.models import User


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("PULSE_DATABASE_URL", url)
    monkeypatch.setenv("PULSE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def typed(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    replies = iter(answers)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(replies))


async def stored_user(url: str, username: str) -> User | None:
    engine = create_engine(url)
    async with create_session_factory(engine)() as session:
        user = await session.scalar(select(User).where(User.username == username))
    await engine.dispose()
    return user


def test_create_user_and_reset_password(cli_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # A too-short password and a mismatch are asked again.
    typed(monkeypatch, "short", "long enough pw", "typo", "long enough pw", "long enough pw")
    assert asyncio.run(cli._create_user("ops", admin=True)) == 0
    user = asyncio.run(stored_user(cli_db, "ops"))
    assert user is not None and user.is_admin
    assert verify_password("long enough pw", user.password_hash)

    typed(monkeypatch, "another password", "another password")
    assert asyncio.run(cli._create_user("ops", admin=False)) == 1  # already exists

    typed(monkeypatch, "rotated password", "rotated password")
    assert asyncio.run(cli._reset_password("ops")) == 0
    user = asyncio.run(stored_user(cli_db, "ops"))
    assert user is not None and verify_password("rotated password", user.password_hash)

    assert asyncio.run(cli._reset_password("nobody")) == 1
    assert asyncio.run(cli._create_user("bad name!", admin=False)) == 1
