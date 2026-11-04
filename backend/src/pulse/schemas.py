"""HTTP request/response bodies. Mirrored in frontend/src/api/types.ts."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field

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
    last_polled_at: datetime | None
    last_error: str | None


class AccountCheck(BaseModel):
    ok: bool
    error: str | None = None


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
    series: dict[str, list[MetricPoint]] = {}


# Events


class EventOut(ORMModel):
    id: int
    account_id: int
    job_id: int | None
    kind: EventKind
    message: str
    created_at: datetime


# Preferences & push


class Preferences(BaseModel):
    alerts: dict[EventKind, bool]


class PushConfig(BaseModel):
    enabled: bool
    public_key: str | None


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
