"""Slurm access over SSH to a cluster login node."""

import asyncio
import logging
import shlex
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import asyncssh

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
NVIDIA_SMI_QUERY = (
    "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
)


class SshSlurmClient:
    """Runs ``sacct``/``scontrol`` on the login node.

    Authenticates with the configured key file or the running ssh-agent; keys are
    never stored by Pulse.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self, account: AccountRef) -> None:
        async with self._connect(account) as conn:
            await self._run(conn, "sacct --version")

    async def snapshot(self, account: AccountRef) -> AccountSnapshot:
        async with self._connect(account) as conn:
            jobs = parse_sacct(await self._run(conn, self._sacct_command(account.username)))
            running = [j for j in jobs if j.state is JobState.RUNNING]
            results = await asyncio.gather(*(self._telemetry(conn, j) for j in running))
            return AccountSnapshot(
                jobs=jobs,
                telemetry={j.slurm_id: t for j, t in zip(running, results, strict=True)},
            )

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
            gpu_util, gpu_mem = (None, None)
            if job.gpus:
                gpu_util, gpu_mem = await self._gpu_usage(conn, job.slurm_id)
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
        self, conn: asyncssh.SSHClientConnection, slurm_id: str
    ) -> tuple[float | None, float | None]:
        # --overlap lets the step share the job's allocation (Slurm >= 20.11).
        cmd = (
            f"timeout {GPU_QUERY_TIMEOUT_S} srun --jobid={slurm_id} --overlap -N1 -n1 "
            f"{NVIDIA_SMI_QUERY}"
        )
        try:
            return parse_nvidia_smi(await self._run(conn, cmd))
        except SlurmError:
            return None, None

    @asynccontextmanager
    async def _connect(self, account: AccountRef) -> AsyncIterator[asyncssh.SSHClientConnection]:
        s = self._settings
        try:
            async with asyncssh.connect(
                account.host,
                port=account.port,
                username=account.username,
                client_keys=[s.ssh_key_path] if s.ssh_key_path else (),
                known_hosts=s.ssh_known_hosts or (),
                connect_timeout=s.ssh_connect_timeout_seconds,
            ) as conn:
                yield conn
        except (OSError, asyncssh.Error) as exc:
            raise SlurmError(f"SSH to {account.host} failed: {exc}") from exc

    @staticmethod
    async def _run(conn: asyncssh.SSHClientConnection, command: str) -> str:
        try:
            result = await conn.run(command, check=False, timeout=COMMAND_TIMEOUT_S)
        except (asyncssh.Error, TimeoutError) as exc:
            raise SlurmError(f"`{_program(command)}` failed: {exc}") from exc
        if result.exit_status != 0:
            stderr = str(result.stderr or "").strip()[:200]
            raise SlurmError(f"`{_program(command)}` exited {result.exit_status}: {stderr}")
        return str(result.stdout or "")


def _program(command: str) -> str:
    """First word of a shell command, skipping leading ``VAR=value`` assignments."""
    return next((w for w in command.split() if "=" not in w), command)
