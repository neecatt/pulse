"""Databases created by older versions are upgraded in place on startup."""

from pathlib import Path

import pytest
from sqlalchemy import select, text

from pulse.db import create_engine, create_session_factory, init_db
from pulse.models import Account, User

# The accounts table as v0.1.0 created it, before jump hosts.
OLD_ACCOUNTS = """
CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN NOT NULL, created_at DATETIME NOT NULL);
CREATE TABLE accounts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    cluster VARCHAR(64) NOT NULL, username VARCHAR(64) NOT NULL, host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL, color INTEGER NOT NULL, notify BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL, last_polled_at DATETIME, last_error VARCHAR(500),
    host_key VARCHAR(2048), connection VARCHAR(16) NOT NULL, agent_token_hash VARCHAR(64));
INSERT INTO users VALUES (1, 'admin', 'x', 1, '2026-11-01 00:00:00');
INSERT INTO accounts VALUES (1, 1, 'lumi', 'jdoe', 'lumi.csc.fi', 22, 0, 1,
    '2026-11-01 00:00:00', NULL, NULL, NULL, 'direct', NULL);
"""


@pytest.fixture
def old_database(tmp_path: Path) -> str:
    import sqlite3

    path = tmp_path / "pulse.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(OLD_ACCOUNTS)
    return f"sqlite+aiosqlite:///{path}"


async def test_old_database_gains_new_columns(old_database: str) -> None:
    engine = create_engine(old_database)
    await init_db(engine)
    await init_db(engine)  # idempotent: a second start changes nothing

    async with create_session_factory(engine)() as session:
        account = (await session.execute(select(Account))).scalar_one()
        assert account.host == "lumi.csc.fi"  # existing data kept
        assert account.jump_host is None
        assert account.jump_port == 22  # filled with the column's default
        assert account.ref().jump is None
        user = await session.get(User, 1)
        assert user is not None
        assert user.alert_prefs == {}  # callable default (JSON) filled in too
        assert user.password_from_env is False

        tables = (await session.execute(text("SELECT name FROM sqlite_master"))).scalars()
        assert "passkeys" in set(tables)  # missing tables are still created
    await engine.dispose()
