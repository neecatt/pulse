from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pulse.db import Base, UTCDateTime
from pulse.domain import EventKind, JobState
from pulse.slurm.base import AccountRef, Hop, HostKeys


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Password comes from PULSE_ADMIN_PASSWORD; it can't be changed in the app.
    password_from_env: Mapped[bool] = mapped_column(default=False)
    # A demo visitor: simulated clusters only, deleted a day after it was created.
    is_guest: Mapped[bool] = mapped_column(default=False)
    # EventKind value -> enabled. Missing keys fall back to DEFAULT_ALERTS.
    alert_prefs: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)
    # Monitoring overrides (see schemas.Monitoring); missing keys use server defaults.
    monitoring_prefs: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    login_sessions: Mapped[list["LoginSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    passkeys: Mapped[list["Passkey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_password(self) -> bool:
        """False for accounts created with a passkey that never set a password."""
        return self.password_hash is not None


class Passkey(Base):
    """A WebAuthn credential (passkey) a user signs in with."""

    __tablename__ = "passkeys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(1023), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(default=0)
    transports: Mapped[list[str]] = mapped_column(JSON, default=list)
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="passkeys")


class Team(Base):
    """A group of users who share chosen accounts with each other, read-only.

    The owner manages it (invites, removals) and is a member like everyone else."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,  # one team per owner
    )
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    owner: Mapped[User] = relationship()
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    invites: Mapped[list["TeamInvite"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    """Membership in a team, the owner's included."""

    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Push alerts for the team's shared jobs; off until the member opts in.
    alerts: Mapped[bool] = mapped_column(default=False)
    # Share every job of every account this member has, now and later.
    share_all: Mapped[bool] = mapped_column(default=False)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class AccountShare(Base):
    """An account its owner shares with one of their teams; the team sees it read-only."""

    __tablename__ = "account_shares"
    __table_args__ = (UniqueConstraint("account_id", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)


class JobShare(Base):
    """One job shared with a team, for accounts that don't share all their jobs."""

    __tablename__ = "job_shares"
    __table_args__ = (UniqueConstraint("job_id", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)


class TeamInvite(Base):
    """A single-use invite link. Only the token's hash is stored."""

    __tablename__ = "team_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)

    team: Mapped[Team] = relationship(back_populates="invites")


class LoginSession(Base):
    """A signed-in browser. The cookie holds a random token; only its hash is kept."""

    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="login_sessions")


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
    # Optional jump host (ssh -J / ProxyJump) in front of the login node.
    jump_host: Mapped[str | None] = mapped_column(String(255))
    jump_port: Mapped[int] = mapped_column(default=22)
    jump_username: Mapped[str | None] = mapped_column(String(64))  # None: same as username
    jump_host_key: Mapped[str | None] = mapped_column(String(2048))
    # "direct": Pulse polls the cluster. "agent": an agent on the login node reports in.
    connection: Mapped[str] = mapped_column(String(16), default="direct")
    agent_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Polled from the simulated cluster, never over SSH (demo guests' accounts).
    simulated: Mapped[bool] = mapped_column(default=False)

    user: Mapped[User] = relationship(back_populates="accounts")

    def ref(self, *, public_only: bool) -> AccountRef:
        """How the Slurm client reaches this account. ``public_only`` for owners who
        aren't admins: they may not point the server at private networks."""
        jump = None
        if self.jump_host:
            jump = Hop(
                self.jump_username or self.username,
                self.jump_host,
                self.jump_port,
                self.jump_host_key,
            )
        return AccountRef(
            self.username,
            self.host,
            self.port,
            self.host_key,
            jump,
            owner_id=self.user_id,
            public_only=public_only,
            simulated_since=self.created_at if self.simulated else None,
        )

    def pin_host_keys(self, keys: HostKeys) -> None:
        """Remember host keys the first time they're seen (trust on first use)."""
        self.host_key = self.host_key or keys.target
        if self.jump_host:
            self.jump_host_key = self.jump_host_key or keys.jump

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
    # Metric used for last_loss and the list sparkline ("loss", "train/loss", ...).
    primary_metric: Mapped[str | None] = mapped_column(String(128))
    hparams: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Per metric: last/min/max/ema/... (see metrics/summary.py).
    metric_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Latest per-node usage: {node: {cpu, mem, gpus: [{util, mem}]}}.
    node_stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Job array the task belongs to ("123" for "123_4"); groups sweeps.
    array_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # User annotations; kept across polls because jobs are upserted, not replaced.
    note: Mapped[str | None] = mapped_column(String(2000))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    # One-shot alert latches, so each warning fires once per job
    warned_time_limit: Mapped[bool] = mapped_column(default=False)
    warned_stall: Mapped[bool] = mapped_column(default=False)
    warned_nan: Mapped[bool] = mapped_column(default=False)
    warned_divergence: Mapped[bool] = mapped_column(default=False)
    warned_plateau: Mapped[bool] = mapped_column(default=False)

    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    account: Mapped[Account] = relationship(back_populates="jobs")
    metrics: Mapped[list["JobMetric"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    metric_files: Mapped[list["MetricFile"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobMetric(Base):
    """One sample of a job's metric: training metrics (by step) or system
    metrics such as gpu_util (by time, no step)."""

    __tablename__ = "job_metrics"
    __table_args__ = (
        Index("ix_job_metrics_job_name_ts", "job_id", "name", "ts"),
        # Re-reading a file must not duplicate points. NULL steps never collide.
        UniqueConstraint("job_id", "name", "step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    step: Mapped[int | None]
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    value: Mapped[float]

    job: Mapped[Job] = relationship(back_populates="metrics")


class MetricFile(Base):
    """A metrics/config file found in a job's working directory, and how far
    into it we've read."""

    __tablename__ = "metric_files"
    __table_args__ = (UniqueConstraint("job_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(1024))
    kind: Mapped[str] = mapped_column(String(16))
    offset: Mapped[int] = mapped_column(default=0)
    csv_header: Mapped[list[str] | None] = mapped_column(JSON)

    job: Mapped[Job] = relationship(back_populates="metric_files")


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


class DailyCount(Base):
    """One counter per day for the admin's site stats (views, demos, sign-ups).
    Only totals: no addresses, users or cookies are stored."""

    __tablename__ = "daily_counts"
    __table_args__ = (UniqueConstraint("day", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, UTC
    name: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(default=0)
