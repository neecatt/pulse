"""Slurm access over SSH to a cluster login node."""

import asyncio
import base64
import logging
import shlex
import socket
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import asyncssh
from asyncssh.known_hosts import KnownHostsArg

from pulse.config import Settings
from pulse.constants import (
    CHUNK_BYTES,
    CONFIG_MAX_BYTES,
    CONFIG_NAMES,
    LOG_TAIL_LINES,
    MAX_CONFIG_FILES,
    MAX_METRIC_FILES,
    PRUNE_DIRS,
    SEARCH_DEPTH,
)
from pulse.domain import JobState
from pulse.metrics.discovery import classify
from pulse.slurm.base import (
    AccountRef,
    AccountSnapshot,
    Cursors,
    FileChunk,
    Hop,
    HostKeys,
    JobTelemetry,
    NodeStats,
    SlurmError,
    SlurmJob,
)
from pulse.slurm.parsing import (
    NODE_STATS_SCRIPT,
    SACCT_FIELDS,
    SAFE_JOB_ID,
    mean_gpu_usage,
    parse_node_stats,
    parse_sacct,
    parse_scontrol_field,
    parse_training_log,
)

logger = logging.getLogger(__name__)

# Separates file chunks in the output of one combined read command.
CHUNK_MARKER = "@@pulse-chunk"

_ConnKey = tuple[str, str, int, str]  # user, host, port, role
_StatsSample = tuple[float, dict[str, NodeStats]]
_Found = list[tuple[str, int]]  # (path, size)
_Discovery = tuple[float, _Found]


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
        self._stats_cache: dict[str, _StatsSample] = {}
        self._discovery_cache: dict[str, _Discovery] = {}

    @property
    def public_key(self) -> str | None:
        return self._public_key

    async def check(self, account: AccountRef) -> HostKeys:
        conn, keys = await self._connect(account)
        await self._run(conn, "sacct --version")
        return keys

    async def snapshot(self, account: AccountRef, cursors: Cursors) -> AccountSnapshot:
        conn, keys = await self._connect(account)
        jobs = parse_sacct(await self._run(conn, self._sacct_command(account.username)))
        running = [j for j in jobs if j.state is JobState.RUNNING]
        results = await asyncio.gather(
            *(self._telemetry(conn, j, cursors.get(j.slurm_id, {})) for j in running)
        )
        return AccountSnapshot(
            jobs=jobs,
            telemetry={j.slurm_id: t for j, t in zip(running, results, strict=True)},
            host_keys=keys,
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

    async def _telemetry(
        self, conn: asyncssh.SSHClientConnection, job: SlurmJob, cursors: Mapping[str, int]
    ) -> JobTelemetry:
        if not SAFE_JOB_ID.match(job.slurm_id):
            return JobTelemetry()
        try:
            info = await self._run(conn, f"scontrol show job -o {job.slurm_id}")
            log_tail, log_mtime = await self._log_tail(conn, parse_scontrol_field(info, "StdOut"))
            nodes = await self._node_usage(conn, job)
            files = await self._metric_files(
                conn, job.slurm_id, parse_scontrol_field(info, "WorkDir"), cursors
            )
        except SlurmError as exc:
            logger.info("telemetry unavailable for job %s: %s", job.slurm_id, exc)
            return JobTelemetry()
        loss, epoch = parse_training_log(log_tail)
        gpu_util, gpu_mem = mean_gpu_usage(nodes)
        return JobTelemetry(
            loss=loss,
            epoch=epoch,
            gpu_util=gpu_util,
            gpu_mem=gpu_mem,
            nodes=nodes,
            log_tail=log_tail,
            log_updated_at=log_mtime,
            files=files,
        )

    async def _metric_files(
        self,
        conn: asyncssh.SSHClientConnection,
        slurm_id: str,
        work_dir: str | None,
        cursors: Mapping[str, int],
    ) -> list[FileChunk]:
        """New bytes of metric/config files under the job's working directory."""
        if not work_dir:
            return []
        found = await self._discover(conn, slurm_id, work_dir)
        reads = []  # (path, offset, size, max bytes)
        for path, size in found:
            offset = cursors.get(path, 0)
            if classify(path) == "config":
                if offset != size:
                    reads.append((path, 0, size, CONFIG_MAX_BYTES))
            elif offset != size:
                start = 0 if offset > size else offset  # truncated or rewritten
                reads.append((path, start, size, CHUNK_BYTES))
        if not reads:
            return []
        script = "; ".join(
            f"echo {CHUNK_MARKER}; "
            f"tail -c +{start + 1} {shlex.quote(path)} | head -c {limit} | base64"
            for path, start, _, limit in reads
        )
        output = await self._run(conn, script)
        bodies = output.split(f"{CHUNK_MARKER}\n")[1:]
        return [
            FileChunk(path, start, size, base64.b64decode(body))
            for (path, start, size, _), body in zip(reads, bodies, strict=False)
        ]

    async def _discover(
        self, conn: asyncssh.SSHClientConnection, slurm_id: str, work_dir: str
    ) -> _Found:
        cached = self._discovery_cache.get(slurm_id)
        if (
            cached
            and time.monotonic() - cached[0] < self._settings.metric_discovery_interval_seconds
        ):
            # Sizes change every poll, so refresh them for the known files only.
            return await self._sizes(conn, [path for path, _ in cached[1]])
        prune = " -o ".join(f"-name {shlex.quote(d)}" for d in PRUNE_DIRS)
        names = ["events.out.tfevents.*", "*metric*.jsonl", "*metric*.csv", "progress.csv"]
        names += CONFIG_NAMES
        match = " -o ".join(f"-name {shlex.quote(n)}" for n in names)
        command = (
            f"timeout 20 find {shlex.quote(work_dir)} -maxdepth {SEARCH_DEPTH} "
            f"\\( {prune} \\) -prune -o -type f \\( {match} \\) "
            "-printf '%T@\\t%s\\t%p\\n' 2>/dev/null | sort -rn | head -200; true"
        )
        found = select_files(await self._run(conn, command))
        self._discovery_cache[slurm_id] = (time.monotonic(), found)
        return found

    async def _sizes(self, conn: asyncssh.SSHClientConnection, paths: list[str]) -> _Found:
        if not paths:
            return []
        quoted = " ".join(shlex.quote(p) for p in paths)
        output = await self._run(conn, f"stat --printf '%s\\t%n\\n' {quoted} 2>/dev/null; true")
        sizes = []
        for line in output.splitlines():
            size, _, path = line.partition("\t")
            if size.isdigit():
                sizes.append((path, int(size)))
        return sizes

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

    async def _node_usage(
        self, conn: asyncssh.SSHClientConnection, job: SlurmJob
    ) -> dict[str, NodeStats]:
        """CPU, memory and per-GPU usage on every node of the job. Sampling starts a
        job step, so it runs at most once per ``node_stats_interval_seconds``."""
        cached = self._stats_cache.get(job.slurm_id)
        if cached and time.monotonic() - cached[0] < self._settings.node_stats_interval_seconds:
            return cached[1]
        # --overlap lets the step share the job's allocation (Slurm >= 20.11).
        cmd = (
            f"timeout {self._settings.node_stats_timeout_seconds} "
            f"srun --jobid={job.slurm_id} --overlap -N{max(job.nodes, 1)} --ntasks-per-node=1 "
            f"bash -c {shlex.quote(NODE_STATS_SCRIPT)}"
        )
        try:
            nodes = parse_node_stats(await self._run(conn, cmd))
        except SlurmError:
            nodes = {}
        self._stats_cache[job.slurm_id] = (time.monotonic(), nodes)
        return nodes

    async def _connect(self, account: AccountRef) -> tuple[asyncssh.SSHClientConnection, HostKeys]:
        """A live connection to the login node (through the jump host, if any),
        reused across polls, and the host keys seen on the way."""
        tunnel = await self._hop(account.jump, None, jump=True) if account.jump else None
        conn = await self._hop(account.target, tunnel)
        return conn, HostKeys(target=_host_key(conn), jump=_host_key(tunnel) if tunnel else None)

    async def _hop(
        self, hop: Hop, tunnel: asyncssh.SSHClientConnection | None, *, jump: bool = False
    ) -> asyncssh.SSHClientConnection:
        """Connect to one hop, reusing an open connection. A connection through a
        jump host closes when the jump host's does, so it's replaced the same way."""
        key = (hop.username, hop.host, hop.port, "jump" if jump else "target")
        async with self._locks.setdefault(key, asyncio.Lock()):
            conn = self._conns.get(key)
            if conn is not None and not conn.is_closed():
                return conn
            role = "jump host " if jump else ""
            try:
                conn = await asyncssh.connect(
                    hop.host,
                    port=hop.port,
                    username=hop.username,
                    client_keys=[str(self._key_file)],
                    known_hosts=self._known_hosts(hop),
                    connect_timeout=self._settings.ssh_connect_timeout_seconds,
                    keepalive_interval=self._settings.ssh_keepalive_seconds,
                    **({"tunnel": tunnel} if tunnel is not None else {}),
                )
            except asyncssh.HostKeyNotVerifiable as exc:
                raise SlurmError(
                    f"The {role}{hop.host} presented a different host key than before. "
                    "If the cluster rotated its keys, remove and re-add the account."
                ) from exc
            except asyncssh.PermissionDenied as exc:
                raise SlurmError(
                    f"The {role}{hop.host} rejected Pulse's SSH key for {hop.username}. "
                    "Authorise the key shown in the app on that cluster."
                ) from exc
            except (OSError, asyncssh.Error) as exc:
                raise SlurmError(_describe_connect_error(hop, exc, role)) from exc
            self._conns[key] = conn
            return conn

    def _known_hosts(self, hop: Hop) -> KnownHostsArg:
        if self._settings.ssh_known_hosts:
            return self._settings.ssh_known_hosts
        if hop.host_key:
            pinned = [asyncssh.import_public_key(hop.host_key)]
            return (pinned, [], [], [], [], [], [])  # trusted keys only
        return None  # trust on first use; the key is pinned after this connect

    async def _run(self, conn: asyncssh.SSHClientConnection, command: str) -> str:
        timeout = self._settings.ssh_command_timeout_seconds
        try:
            result = await conn.run(command, check=False, timeout=timeout)
        except (asyncssh.Error, OSError, TimeoutError) as exc:
            raise SlurmError(f"`{_program(command)}` failed: {exc}") from exc
        if result.exit_status != 0:
            stderr = str(result.stderr or "").strip()[:200]
            raise SlurmError(f"`{_program(command)}` exited {result.exit_status}: {stderr}")
        return str(result.stdout or "")


def select_files(find_output: str) -> _Found:
    """Pick the newest metric and config files from ``find -printf '%T@\\t%s\\t%p\\n'``
    output (already sorted newest first)."""
    metrics: _Found = []
    configs: _Found = []
    for line in find_output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        kind = classify(parts[2])
        bucket, limit = (
            (configs, MAX_CONFIG_FILES) if kind == "config" else (metrics, MAX_METRIC_FILES)
        )
        if kind is not None and len(bucket) < limit:
            bucket.append((parts[2], int(parts[1])))
    return metrics + configs


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


def _describe_connect_error(hop: Hop, exc: Exception, role: str = "") -> str:
    where = hop.host if hop.port == 22 else f"{hop.host}:{hop.port}"
    if isinstance(exc, socket.gaierror):
        return f"Can't find the {role}{hop.host}. Check the hostname."
    if isinstance(exc, ConnectionRefusedError):
        return f"The {role}{where} refused the connection. Check the host and SSH port."
    if isinstance(exc, TimeoutError):
        return (
            f"The {role}{where} didn't respond. It may be down, only reachable via VPN, "
            "or need a jump host."
        )
    return f"SSH to the {role}{where} failed: {exc}"


def _host_key(conn: asyncssh.SSHClientConnection) -> str | None:
    key = conn.get_server_host_key()
    return key.export_public_key().decode().strip() if key else None


def _program(command: str) -> str:
    """First word of a shell command, skipping leading ``VAR=value`` assignments."""
    return next((w for w in command.split() if "=" not in w), command)
