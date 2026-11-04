from datetime import UTC, datetime

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pulse.db import Base, UTCDateTime
from pulse.domain import EventKind, JobState


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # EventKind value -> enabled. Missing keys fall back to DEFAULT_ALERTS.
    alert_prefs: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Account(Base):
    """An HPC login (username on a cluster) linked by a user."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "username", "host", "port"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cluster: Mapped[str] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(64))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(default=22)
    color: Mapped[int] = mapped_column(default=0)
    notify: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_polled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))
    # Server host key pinned on first successful connect (trust on first use).
    host_key: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="accounts")
    jobs: Mapped[list["Job"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Job(Base):
    """Latest known snapshot of a Slurm job, refreshed by the poller."""

    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("account_id", "slurm_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    slurm_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    partition: Mapped[str] = mapped_column(String(64))
    state: Mapped[JobState] = mapped_column(Enum(JobState, native_enum=False))
    reason: Mapped[str | None] = mapped_column(String(64))
    nodes: Mapped[int] = mapped_column(default=0)
    gpus: Mapped[int] = mapped_column(default=0)
    node_list: Mapped[str | None] = mapped_column(String(255))
    submit_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    start_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    time_limit_s: Mapped[int | None]
    elapsed_s: Mapped[int] = mapped_column(default=0)
    exit_code: Mapped[int | None]

    # Training telemetry, latest values
    epoch: Mapped[str | None] = mapped_column(String(32))
    last_loss: Mapped[float | None]
    gpu_util: Mapped[float | None]
    gpu_mem: Mapped[float | None]
    log_tail: Mapped[list[str]] = mapped_column(JSON, default=list)
    log_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # One-shot alert latches, so each warning fires once per job
    warned_time_limit: Mapped[bool] = mapped_column(default=False)
    warned_stall: Mapped[bool] = mapped_column(default=False)

    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    account: Mapped[Account] = relationship(back_populates="jobs")
    metrics: Mapped[list["JobMetric"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobMetric(Base):
    """Time series sample (loss, gpu_util, gpu_mem) for a job."""

    __tablename__ = "job_metrics"
    __table_args__ = (Index("ix_job_metrics_job_name_ts", "job_id", "name", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    value: Mapped[float]

    job: Mapped[Job] = relationship(back_populates="metrics")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_account_created", "account_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    kind: Mapped[EventKind] = mapped_column(Enum(EventKind, native_enum=False))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    account: Mapped[Account] = relationship(back_populates="events")
    job: Mapped[Job | None] = relationship()


class PushSubscription(Base):
    """A browser/device Web Push endpoint belonging to a user."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="push_subscriptions")
