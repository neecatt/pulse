from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, TypedDict

from pulse.domain import JobState

# slurm_id -> file path -> byte offset already ingested
Cursors = Mapping[str, Mapping[str, int]]


@dataclass(frozen=True, slots=True)
class Hop:
    """One SSH server to connect to: the login node, or a jump host before it."""

    username: str
    host: str
    port: int = 22
    # OpenSSH public key pinned on first successful connect; None = not yet known.
    host_key: str | None = None


@dataclass(frozen=True, slots=True)
class AccountRef:
    """What a Slurm client needs to reach one account."""

    username: str
    host: str
    port: int = 22
    host_key: str | None = None
    # Jump host (like ssh -J / ProxyJump) when the login node isn't directly reachable.
    jump: Hop | None = None
    # The Pulse user the account belongs to: Pulse signs in with that user's own key.
    owner_id: int = 0
    # Connect only to public internet addresses (for users who don't run the server).
    public_only: bool = False
    # Set for a demo account: it's simulated, and its story starts at this moment.
    simulated_since: datetime | None = None

    @property
    def target(self) -> Hop:
        return Hop(self.username, self.host, self.port, self.host_key)


@dataclass(frozen=True, slots=True)
class HostKeys:
    """Host keys seen while connecting, for pinning: the login node's and the jump host's."""

    target: str | None = None
    jump: str | None = None


@dataclass(frozen=True, slots=True)
class SlurmJob:
    slurm_id: str
    name: str
    partition: str
    state: JobState
    reason: str | None = None
    nodes: int = 0
    gpus: int = 0
    node_list: str | None = None
    submit_time: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    time_limit_s: int | None = None
    elapsed_s: int = 0
    exit_code: int | None = None
    array_id: str | None = None  # "123" for array task "123_4" or pending "123_[5-9]"


class GpuStats(TypedDict):
    util: float  # %
    mem: float  # % of GPU memory used


class NodeStats(TypedDict):
    cpu: float | None  # %
    mem: float | None  # % of RAM used
    gpus: list[GpuStats]


@dataclass(frozen=True, slots=True)
class FileChunk:
    """New bytes from a metrics/config file, starting at ``offset``."""

    path: str
    offset: int
    size: int  # file size when read
    data: bytes


@dataclass(frozen=True, slots=True)
class JobTelemetry:
    """Best-effort live data for a running job. Any field may be unknown."""

    loss: float | None = None
    epoch: str | None = None
    gpu_util: float | None = None
    gpu_mem: float | None = None
    log_tail: list[str] = field(default_factory=list)
    log_updated_at: datetime | None = None
    files: list[FileChunk] = field(default_factory=list)
    nodes: dict[str, NodeStats] = field(default_factory=dict)  # latest per-node usage


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    jobs: list[SlurmJob]
    telemetry: dict[str, JobTelemetry] = field(default_factory=dict)  # keyed by slurm_id
    host_keys: HostKeys = field(default_factory=HostKeys)  # keys seen, for pinning


class SlurmError(Exception):
    """Raised when a cluster can't be reached or returns unusable output."""


class SlurmClient(Protocol):
    def public_key_for(self, user_id: int) -> str | None:
        """The key a user authorises on their clusters, if the client uses one."""

    async def check(self, account: AccountRef) -> HostKeys:
        """Verify the account is reachable and return the host keys seen.

        Raises SlurmError if it isn't reachable.
        """

    async def snapshot(self, account: AccountRef, cursors: Cursors) -> AccountSnapshot:
        """Active and recently finished jobs, plus telemetry for running ones.

        For files listed in ``cursors``, only bytes after the offset are needed.
        """

    async def close(self) -> None:
        """Release connections."""
