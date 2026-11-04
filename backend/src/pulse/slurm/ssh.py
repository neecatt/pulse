"""Slurm access over SSH to a cluster login node."""

import asyncio
import logging
import shlex
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import asyncssh
from asyncssh.known_hosts import KnownHostsArg

from pulse.config import Settings
from pulse.domain import JobState
from pulse.slurm.base import AccountRef, AccountSnapshot, JobTelemetry, SlurmError, SlurmJob
from pulse.slurm.parsing import (
    SACCT_FIELDS,
    SAFE_JOB_ID,
    parse_nvidia_smi,
    parse_sacct,
    parse_scontrol_field,
    parse_training_log,
)

logger = logging.getLogger(__name__)

LOG_TAIL_LINES = 40
COMMAND_TIMEOUT_S = 30
GPU_QUERY_TIMEOUT_S = 15
KEEPALIVE_INTERVAL_S = 60
NVIDIA_SMI_QUERY = (
    "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
)

_ConnKey = tuple[str, str, int]
_GpuSample = tuple[float, tuple[float | None, float | None]]


class SshSlurmClient:
    """Runs ``sacct``/``scontrol`` on the login node.

    One SSH connection per account is kept open and reused across polls, so a
    poll costs a few commands rather than a full handshake. Pulse authenticates
    with its own key (generated on first start), which the user authorises on
    the cluster once.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._key_file = settings.ssh_key_file
        self._public_key = _ensure_key_pair(self._key_file)
        self._conns: dict[_ConnKey, asyncssh.SSHClientConnection] = {}
        self._locks: dict[_ConnKey, asyncio.Lock] = {}
        # GPU queries start a job step, so sample them less often than we poll.
        self._gpu_cache: dict[str, _GpuSample] = {}

    @property
    def public_key(self) -> str | None:
        return self._public_key

    async def check(self, account: AccountRef) -> str | None:
        async with self._session(account) as conn:
            await self._run(conn, "sacct --version")
            return _host_key(conn)

    async def snapshot(self, account: AccountRef) -> AccountSnapshot:
        async with self._session(account) as conn:
            jobs = parse_sacct(await self._run(conn, self._sacct_command(account.username)))
            running = [j for j in jobs if j.state is JobState.RUNNING]
            results = await asyncio.gather(*(self._telemetry(conn, j) for j in running))
            return AccountSnapshot(
                jobs=jobs,
                telemetry={j.slurm_id: t for j, t in zip(running, results, strict=True)},
                host_key=_host_key(conn),
            )

    async def close(self) -> None:
        conns, self._conns = list(self._conns.values()), {}
        for conn in conns:
            conn.close()
        await asyncio.gather(*(conn.wait_closed() for conn in conns))

    def _sacct_command(self, username: str) -> str:
        hours = self._settings.sacct_lookback_hours
        return (
            f"SLURM_TIME_FORMAT=%s sacct -X -P -n -u {shlex.quote(username)} "
            f"-S now-{hours}hours -o {','.join(SACCT_FIELDS)}"
        )

    async def _telemetry(self, conn: asyncssh.SSHClientConnection, job: SlurmJob) -> JobTelemetry:
        if not SAFE_JOB_ID.match(job.slurm_id):
            return JobTelemetry()
        try:
            info = await self._run(conn, f"scontrol show job -o {job.slurm_id}")
            log_tail, log_mtime = await self._log_tail(conn, parse_scontrol_field(info, "StdOut"))
            gpu_util, gpu_mem = await self._gpu_usage(conn, job) if job.gpus else (None, None)
        except SlurmError as exc:
            logger.info("telemetry unavailable for job %s: %s", job.slurm_id, exc)
            return JobTelemetry()
        loss, epoch = parse_training_log(log_tail)
        return JobTelemetry(
            loss=loss,
            epoch=epoch,
            gpu_util=gpu_util,
            gpu_mem=gpu_mem,
            log_tail=log_tail,
            log_updated_at=log_mtime,
        )

    async def _log_tail(
        self, conn: asyncssh.SSHClientConnection, path: str | None
    ) -> tuple[list[str], datetime | None]:
        if not path:
            return [], None
        quoted = shlex.quote(path)
        out = await self._run(conn, f"stat -c %Y {quoted} && tail -n {LOG_TAIL_LINES} {quoted}")
        first, _, rest = out.partition("\n")
        mtime = datetime.fromtimestamp(int(first), UTC) if first.strip().isdigit() else None
        return rest.splitlines(), mtime

    async def _gpu_usage(
        self, conn: asyncssh.SSHClientConnection, job: SlurmJob
    ) -> tuple[float | None, float | None]:
        cached = self._gpu_cache.get(job.slurm_id)
        if cached and time.monotonic() - cached[0] < self._settings.gpu_sample_interval_seconds:
            return cached[1]
        # --overlap lets the step share the job's allocation (Slurm >= 20.11).
        cmd = (
            f"timeout {GPU_QUERY_TIMEOUT_S} srun --jobid={job.slurm_id} --overlap -N1 -n1 "
            f"{NVIDIA_SMI_QUERY}"
        )
        try:
            usage = parse_nvidia_smi(await self._run(conn, cmd))
        except SlurmError:
            usage = (None, None)
        self._gpu_cache[job.slurm_id] = (time.monotonic(), usage)
        return usage

    @asynccontextmanager
    async def _session(self, account: AccountRef) -> AsyncIterator[asyncssh.SSHClientConnection]:
        """Yield a live connection, dropping it if the session fails so the next
        call reconnects."""
        key = (account.username, account.host, account.port)
        conn = await self._connection(key, account)
        try:
            yield conn
        except SlurmError:
            if conn.is_closed():
                self._conns.pop(key, None)
            raise

    async def _connection(self, key: _ConnKey, account: AccountRef) -> asyncssh.SSHClientConnection:
        async with self._locks.setdefault(key, asyncio.Lock()):
            conn = self._conns.get(key)
            if conn is not None and not conn.is_closed():
                return conn
            try:
                conn = await asyncssh.connect(
                    account.host,
                    port=account.port,
                    username=account.username,
                    client_keys=[str(self._key_file)],
                    known_hosts=self._known_hosts(account),
                    connect_timeout=self._settings.ssh_connect_timeout_seconds,
                    keepalive_interval=KEEPALIVE_INTERVAL_S,
                )
            except asyncssh.HostKeyNotVerifiable as exc:
                raise SlurmError(
                    f"{account.host} presented a different host key than before. "
                    "If the cluster rotated its keys, remove and re-add the account."
                ) from exc
            except asyncssh.PermissionDenied as exc:
                raise SlurmError(
                    f"{account.host} rejected Pulse's SSH key for {account.username}. "
                    "Authorise the key shown in the app on that cluster."
                ) from exc
            except (OSError, asyncssh.Error) as exc:
                raise SlurmError(_describe_connect_error(account, exc)) from exc
            self._conns[key] = conn
            return conn

    def _known_hosts(self, account: AccountRef) -> KnownHostsArg:
        if self._settings.ssh_known_hosts:
            return self._settings.ssh_known_hosts
        if account.host_key:
            pinned = [asyncssh.import_public_key(account.host_key)]
            return (pinned, [], [], [], [], [], [])  # trusted keys only
        return None  # trust on first use; the key is pinned after this connect

    @staticmethod
    async def _run(conn: asyncssh.SSHClientConnection, command: str) -> str:
        try:
            result = await conn.run(command, check=False, timeout=COMMAND_TIMEOUT_S)
        except (asyncssh.Error, OSError, TimeoutError) as exc:
            raise SlurmError(f"`{_program(command)}` failed: {exc}") from exc
        if result.exit_status != 0:
            stderr = str(result.stderr or "").strip()[:200]
            raise SlurmError(f"`{_program(command)}` exited {result.exit_status}: {stderr}")
        return str(result.stdout or "")


def _ensure_key_pair(private_path: Path) -> str:
    """Load Pulse's SSH key, generating an ed25519 pair on first use."""
    public_path = private_path.with_name(private_path.name + ".pub")
    if not private_path.exists():
        private_path.parent.mkdir(parents=True, exist_ok=True)
        key = asyncssh.generate_private_key("ssh-ed25519", comment="pulse-hpc-monitor")
        key.write_private_key(private_path)
        private_path.chmod(0o600)
        key.write_public_key(public_path)
        logger.info("generated SSH key %s", private_path)
    if public_path.exists():
        return public_path.read_text().strip()
    return asyncssh.read_private_key(private_path).export_public_key().decode().strip()


def _describe_connect_error(account: AccountRef, exc: Exception) -> str:
    where = account.host if account.port == 22 else f"{account.host}:{account.port}"
    if isinstance(exc, socket.gaierror):
        return f"Can't find {account.host}. Check the hostname."
    if isinstance(exc, ConnectionRefusedError):
        return f"{where} refused the connection. Check the host and SSH port."
    if isinstance(exc, TimeoutError):
        return f"{where} didn't respond. It may be down, or only reachable via VPN."
    return f"SSH to {where} failed: {exc}"


def _host_key(conn: asyncssh.SSHClientConnection) -> str | None:
    key = conn.get_server_host_key()
    return key.export_public_key().decode().strip() if key else None


def _program(command: str) -> str:
    """First word of a shell command, skipping leading ``VAR=value`` assignments."""
    return next((w for w in command.split() if "=" not in w), command)
