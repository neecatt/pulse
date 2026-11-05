"""HTTP request/response bodies. Mirrored in frontend/src/api/types.ts."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field

from pulse.config import Settings
from pulse.constants import (
    PASSKEY_NAME_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_PATTERN,
)
from pulse.domain import EventKind, JobState

Username = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
]
Hostname = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$",
        max_length=255,
    ),
]
ClusterName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Connection = Literal["direct", "agent"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Accounts


class AccountCreate(BaseModel):
    # Derived from the host when omitted ("login.lumi.csc.fi" -> "LUMI").
    cluster: ClusterName | None = None
    username: Username
    host: Hostname
    port: int = Field(default=22, ge=1, le=65535)
    notify: bool = True
    connection: Connection = "direct"
    # Jump host (ssh -J / ProxyJump) for login nodes that aren't directly reachable.
    jump_host: Hostname | None = None
    jump_port: int = Field(default=22, ge=1, le=65535)
    jump_username: Username | None = None  # defaults to username


class AccountUpdate(BaseModel):
    cluster: ClusterName | None = None
    notify: bool | None = None


class AccountOut(ORMModel):
    id: int
    cluster: str
    username: str
    host: str
    port: int
    color: int
    notify: bool
    connection: Connection
    jump_host: str | None
    jump_port: int
    jump_username: str | None
    last_polled_at: datetime | None
    last_error: str | None
    # Teams you share this account with (your own accounts only).
    shared_with: list[int] = []
    # Username of the account's owner when it's shared with you by a teammate;
    # None for your own accounts (only those can be changed).
    owner: str | None = None


class AgentToken(BaseModel):
    """Shown once: the agent's credential. Only its hash is stored."""

    token: str


class AccountCheck(BaseModel):
    ok: bool
    error: str | None = None


# Auth

AuthUsername = Annotated[str, StringConstraints(strip_whitespace=True, pattern=USERNAME_PATTERN)]
Password = Annotated[
    str, StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
]


class Credentials(BaseModel):
    username: AuthUsername
    password: Password


class Setup(Credentials):
    setup_code: str = Field(max_length=32)


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    new_password: Password


class Me(ORMModel):
    id: int
    username: str
    is_admin: bool
    password_from_env: bool


class AuthStatus(BaseModel):
    """What the sign-in screen needs before anyone is signed in."""

    setup_required: bool  # no accounts yet: the first visitor creates the admin
    signup_allowed: bool
    user: Me | None  # who this browser is signed in as, if anyone


class PasskeyOut(ORMModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class PasskeyOptions(BaseModel):
    """WebAuthn options for the browser, plus the id of the pending challenge."""

    challenge_id: str
    options: dict[str, Any]


class PasskeyRegistration(BaseModel):
    challenge_id: str = Field(max_length=64)
    credential: dict[str, Any]  # PublicKeyCredential JSON from the browser
    name: str | None = Field(default=None, max_length=PASSKEY_NAME_MAX_LENGTH)


class PasskeyLogin(BaseModel):
    challenge_id: str = Field(max_length=64)
    credential: dict[str, Any]


class LoginSessionOut(ORMModel):
    id: int
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool = False


# Agent


class AgentFile(BaseModel):
    path: str = Field(max_length=1024)
    offset: int = Field(ge=0)
    size: int = Field(ge=0)
    data: str = Field(max_length=400_000)  # base64 of at most CHUNK_BYTES


class AgentJob(BaseModel):
    log_tail: list[Annotated[str, StringConstraints(max_length=4096)]] = Field(
        default=[], max_length=200
    )
    log_mtime: int | None = None
    node_stats: str | None = Field(default=None, max_length=65536)  # NODE_STATS_SCRIPT output
    files: list[AgentFile] = Field(default=[], max_length=16)


class AgentReport(BaseModel):
    """Raw Slurm output from the login-node agent; parsed server-side."""

    agent_version: str = Field(max_length=16)
    sacct: str = Field(max_length=2_000_000)
    jobs: dict[str, AgentJob] = Field(default={}, max_length=1000)
    error: str | None = Field(default=None, max_length=500)


class AgentReportAck(BaseModel):
    next_report_in: int
    # Offsets already ingested per job and file; the agent sends only newer bytes.
    cursors: dict[str, dict[str, int]] = {}


class SetupInfo(BaseModel):
    """What the UI needs to guide account setup."""

    slurm_backend: str
    ssh_public_key: str | None


# Jobs


class JobOut(ORMModel):
    id: int
    account_id: int
    slurm_id: str
    name: str
    partition: str
    state: JobState
    reason: str | None
    nodes: int
    gpus: int
    node_list: str | None
    submit_time: datetime | None
    start_time: datetime | None
    end_time: datetime | None
    time_limit_s: int | None
    elapsed_s: int
    exit_code: int | None
    epoch: str | None
    last_loss: float | None
    gpu_util: float | None
    gpu_mem: float | None
    loss_trend: list[float] = []
    primary_metric: str | None
    tags: list[str]
    array_id: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def time_used(self) -> float | None:
        """Fraction of the time limit consumed, 0..1."""
        if not self.time_limit_s:
            return None
        return min(1.0, self.elapsed_s / self.time_limit_s)


class MetricPoint(BaseModel):
    t: datetime
    v: float


class JobDetailOut(JobOut):
    log_tail: list[str]
    log_updated_at: datetime | None
    note: str | None
    hparams: dict[str, Any]
    node_stats: dict[str, Any]  # latest per node: {cpu, mem, gpus: [{util, mem}]}
    # System metrics: gpu_util, gpu_mem and per node sys/<node>/{cpu,mem,gpu,gpu_mem}
    series: dict[str, list[MetricPoint]] = {}


class MetricStats(BaseModel):
    last: float
    min: float
    max: float


class RunOut(JobOut):
    """A job as a row of the runs table: metric summaries plus hyperparameters."""

    hparams: dict[str, Any]
    # Not "metrics": that name is the ORM relationship holding every sample.
    metric_stats: dict[str, MetricStats] = {}


Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class JobUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    tags: list[Tag] | None = Field(default=None, max_length=20)


class StepPoint(BaseModel):
    s: int | None  # step
    t: datetime
    v: float


class JobMetrics(BaseModel):
    """Training metrics of a job, each downsampled for charting."""

    metrics: dict[str, list[StepPoint]]
    primary: str | None
    hparams: dict[str, Any]
    files: list[str]


# Events


class EventOut(ORMModel):
    id: int
    account_id: int
    job_id: int | None
    kind: EventKind
    message: str
    created_at: datetime


# Teams

TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class TeamCreate(BaseModel):
    name: TeamName


class TeamMemberOut(BaseModel):
    user_id: int
    username: str
    joined_at: datetime


class TeamInviteOut(ORMModel):
    id: int
    created_at: datetime
    expires_at: datetime


class NewTeamInvite(TeamInviteOut):
    token: str  # shown once; the link is /join/<token>


class OwnedTeam(BaseModel):
    id: int
    name: str
    members: list[TeamMemberOut]  # everyone but you
    invites: list[TeamInviteOut]  # pending, not yet used or expired
    alerts: bool  # your alerts for teammates' shared jobs


class TeamMembership(BaseModel):
    """A team you belong to that someone else owns."""

    team_id: int
    name: str
    owner: str
    alerts: bool
    joined_at: datetime


class TeamOverview(BaseModel):
    owned: OwnedTeam | None
    memberships: list[TeamMembership]


class MembershipUpdate(BaseModel):
    alerts: bool


class InviteInfo(BaseModel):
    """What an invite link shows before you join."""

    team: str
    owner: str


# Preferences & push


class Monitoring(BaseModel):
    """Per-user monitoring settings. Server config supplies the defaults."""

    live_refresh_seconds: int = Field(ge=5, le=300)
    idle_refresh_seconds: int = Field(ge=30, le=1800)
    stall_minutes: int = Field(ge=5, le=240)
    time_limit_warning_percent: int = Field(ge=50, le=99)
    diverge_percent: int = Field(ge=10, le=500)
    plateau_minutes: int = Field(ge=15, le=1440)

    @classmethod
    def resolve(cls, stored: dict[str, int], settings: Settings) -> "Monitoring":
        defaults = {
            "live_refresh_seconds": settings.poll_interval_live_seconds,
            "idle_refresh_seconds": settings.poll_interval_idle_seconds,
            "stall_minutes": settings.stall_minutes,
            "time_limit_warning_percent": round(settings.time_limit_warning_ratio * 100),
            "diverge_percent": settings.diverge_percent,
            "plateau_minutes": settings.plateau_minutes,
        }
        merged = defaults | {k: v for k, v in stored.items() if k in defaults}
        try:
            return cls(**merged)
        except ValueError:  # stored values from an older, wider range
            return cls(**defaults)


class MonitoringUpdate(BaseModel):
    live_refresh_seconds: int | None = Field(default=None, ge=5, le=300)
    idle_refresh_seconds: int | None = Field(default=None, ge=30, le=1800)
    stall_minutes: int | None = Field(default=None, ge=5, le=240)
    time_limit_warning_percent: int | None = Field(default=None, ge=50, le=99)
    diverge_percent: int | None = Field(default=None, ge=10, le=500)
    plateau_minutes: int | None = Field(default=None, ge=15, le=1440)


class Preferences(BaseModel):
    alerts: dict[EventKind, bool]
    monitoring: Monitoring


class PreferencesUpdate(BaseModel):
    """Partial update: only the given alert kinds and monitoring fields change."""

    alerts: dict[EventKind, bool] = {}
    monitoring: MonitoringUpdate = MonitoringUpdate()


class PushConfig(BaseModel):
    public_key: str  # VAPID key browsers subscribe with


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionIn(BaseModel):
    """Shape of ``PushSubscription.toJSON()`` in the browser."""

    endpoint: str = Field(pattern=r"^https://", max_length=1024)
    keys: PushKeys


class PushUnsubscribe(BaseModel):
    endpoint: str


class PushTestResult(BaseModel):
    delivered: int
