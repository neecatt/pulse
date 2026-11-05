from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Connection, DateTime, Dialect, event, inspect, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime stored as UTC.

    SQLite drops tzinfo on round-trip, so normalise on the way in and re-attach
    UTC on the way out.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create missing tables, and add columns that newer versions introduced."""
    from pulse import models  # noqa: F401  (register tables on Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
        await conn.run_sync(_relabel_timeouts)


def _add_missing_columns(conn: Connection) -> None:
    """Upgrade databases from older versions in place.

    ``create_all`` never alters existing tables, so a column added in a new
    version is added here and existing rows get its default. This covers
    additive changes only; renames or new constraints need a real migration.
    The database column stays nullable (SQLite can't add a NOT NULL column
    without a constant default); the models still require a value.
    """
    inspector = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # just created with every column
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if column.primary_key or column.unique:
                raise RuntimeError(f"Can't add key column {table.name}.{column.name} in place")
            column_type = column.type.compile(conn.dialect)
            conn.exec_driver_sql(
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'
            )
            if column.default is not None:
                conn.execute(table.update().values({column.name: _default_value(column)}))
            elif not column.nullable:
                raise RuntimeError(f"New column {table.name}.{column.name} needs a default")


def _relabel_timeouts(conn: Connection) -> None:
    """Before 0.2.2, a job that ran until its time limit was recorded as failed.
    Relabel those events so past activity matches. Idempotent, and a no-op once
    there are none left."""
    from pulse.domain import EventKind, JobState
    from pulse.models import Event, Job

    conn.execute(
        update(Event)
        .where(
            Event.kind == EventKind.JOB_FAILED,
            Event.job_id.in_(select(Job.id).where(Job.state == JobState.TIMEOUT)),
        )
        .values(kind=EventKind.JOB_TIMED_OUT)
    )


def _default_value(column: Column[Any]) -> Any:
    default = column.default
    assert default is not None
    if default.is_scalar:
        return default.arg  # type: ignore[attr-defined]
    return default.arg(None)  # type: ignore[attr-defined]  # callable, e.g. dict or utcnow
