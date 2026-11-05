"""SshSlurmClient against an in-process SSH server that fakes the Slurm CLI."""

import base64
import re
import shlex
import socket
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from pathlib import Path

import asyncssh
import pytest

from pulse.config import Settings
from pulse.constants import FIRST_USER_ID
from pulse.domain import JobState
from pulse.net import is_public_ip
from pulse.slurm.base import AccountRef, Hop, SlurmError
from pulse.slurm.ssh import CHUNK_MARKER, SshSlurmClient, select_files

WORK_DIR = Path(tempfile.mkdtemp(prefix="pulse-ssh-workdir-"))
CHUNK_READ = re.compile(r"tail -c \+(\d+) (\S+) \| head -c (\d+) \| base64")

SACCT_OUTPUT = (
    "4242|train|gpu|RUNNING|1|cpu=8,gres/gpu=4|cpu=8,gres/gpu=4|gpu001"
    "|1767268800|1767269400|Unknown|600|1800|0:0\n"
)


def fake_slurm(process: asyncssh.SSHServerProcess[str]) -> None:
    command = process.command or ""
    if command == "sacct --version":
        process.stdout.write("slurm 24.05.1\n")
    elif "sacct -X" in command:
        process.stdout.write(SACCT_OUTPUT)
    elif command.startswith("scontrol show job"):
        process.stdout.write(
            f"JobId=4242 JobName=train StdOut=/scratch/train-4242.out WorkDir={WORK_DIR}\n"
        )
    elif " find " in f" {command}":
        # GNU find -printf isn't on macOS; answer from the fake work dir instead.
        for path in sorted(WORK_DIR.rglob("*"), reverse=True):
            if path.is_file():
                process.stdout.write(f"{path.stat().st_mtime}\t{path.stat().st_size}\t{path}\n")
    elif command.startswith("stat --printf"):
        for path in shlex.split(command)[3:-1]:
            if Path(path).exists():
                process.stdout.write(f"{Path(path).stat().st_size}\t{path}\n")
    elif CHUNK_MARKER in command:
        for start, path, limit in CHUNK_READ.findall(command):
            data = Path(shlex.split(path)[0]).read_bytes()[int(start) - 1 :][: int(limit)]
            process.stdout.write(f"{CHUNK_MARKER}\n{base64.encodebytes(data).decode()}")
    elif command.startswith("stat -c %Y"):
        process.stdout.write(f"{int(time.time())}\n[step 10] epoch 2/5 loss=0.512\n")
    elif "srun" in command:
        process.stdout.write("gpu001\tcpu\t40\ngpu001\tgpu\t0\t80\t1000\t2000\n")
        process.stdout.write("gpu001\tgpu\t1\t90\t1000\t2000\n")
    else:
        process.exit(127)
        return
    process.exit(0)


OWNER = FIRST_USER_ID  # the Pulse user whose key the fake servers accept


@dataclass
class FakeCluster:
    port: int
    host_key: str
    connections: list[asyncssh.SSHServerConnection]

    def account(self, host_key: str | None = None, owner_id: int = OWNER) -> AccountRef:
        return AccountRef(
            username="alice", host="127.0.0.1", port=self.port, host_key=host_key, owner_id=owner_id
        )


def make_client(data_dir: Path) -> SshSlurmClient:
    settings = Settings(data_dir=data_dir, slurm_backend="ssh", _env_file=None)  # type: ignore[call-arg]
    return SshSlurmClient(settings)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[SshSlurmClient]:
    c = make_client(tmp_path / "pulse")
    yield c
    await c.close()


@pytest.fixture
async def cluster(client: SshSlurmClient) -> AsyncIterator[FakeCluster]:
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    connections: list[asyncssh.SSHServerConnection] = []

    class Server(asyncssh.SSHServer):
        def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
            connections.append(conn)

    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[server_key],
        authorized_client_keys=asyncssh.import_authorized_keys(client.public_key_for(OWNER)),
        process_factory=fake_slurm,
        server_factory=Server,
    )
    port = server.sockets[0].getsockname()[1]
    yield FakeCluster(port, server_key.export_public_key().decode().strip(), connections)
    await client.close()  # the server waits for open client connections on shutdown
    server.close()
    await server.wait_closed()


def test_generates_private_key_once(tmp_path: Path) -> None:
    first = make_client(tmp_path)
    key_file = tmp_path / "pulse_ed25519"  # the first account's key keeps its old name
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert first.public_key_for(OWNER).startswith("ssh-ed25519 ")
    assert make_client(tmp_path).public_key_for(OWNER) == first.public_key_for(OWNER)


def test_every_other_user_gets_their_own_key(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    keys = {client.public_key_for(user_id) for user_id in (OWNER, 2, 3)}
    assert len(keys) == 3
    assert (tmp_path / "ssh" / "user-2_ed25519").stat().st_mode & 0o777 == 0o600
    assert make_client(tmp_path).public_key_for(2) == client.public_key_for(2)  # kept


async def test_check_returns_server_host_key(client: SshSlurmClient, cluster: FakeCluster) -> None:
    assert (await client.check(cluster.account())).target == cluster.host_key


async def test_snapshot_parses_jobs_and_telemetry(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    snapshot = await client.snapshot(cluster.account(), {})

    (job,) = snapshot.jobs
    assert job.state is JobState.RUNNING
    assert job.gpus == 4
    telemetry = snapshot.telemetry["4242"]
    assert telemetry.loss == 0.512
    assert telemetry.epoch == "2/5"
    assert telemetry.gpu_util == 85.0
    assert telemetry.gpu_mem == 50.0
    assert snapshot.host_keys.target == cluster.host_key


async def test_connection_is_reused_across_polls(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    for _ in range(3):
        await client.snapshot(cluster.account(), {})
    assert len(cluster.connections) == 1


async def test_pinned_host_key_mismatch_is_rejected(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    other = asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode()
    with pytest.raises(SlurmError, match="different host key"):
        await client.check(cluster.account(host_key=other))


async def test_matching_pinned_host_key_connects(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    keys = await client.check(cluster.account(host_key=cluster.host_key))
    assert keys.target == cluster.host_key


async def test_unauthorised_key_gets_actionable_error(tmp_path: Path, cluster: FakeCluster) -> None:
    stranger = make_client(tmp_path / "other")
    try:
        with pytest.raises(SlurmError, match="Authorise the key"):
            await stranger.check(cluster.account())
    finally:
        await stranger.close()


async def test_connection_errors_are_plain_language(client: SshSlurmClient) -> None:
    with socket.socket() as probe:  # grab a free port, then close it so nothing listens
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    account = AccountRef(username="alice", host="127.0.0.1", port=port)
    with pytest.raises(SlurmError, match="refused the connection"):
        await client.check(account)


async def test_metric_files_are_read_incrementally(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    metrics = WORK_DIR / "metrics.jsonl"
    metrics.write_text('{"step": 1, "loss": 2.0}\n')
    (WORK_DIR / "hparams.yaml").write_text("lr: 0.1\n")
    (WORK_DIR / "unrelated.txt").write_text("ignored\n")

    first = (await client.snapshot(cluster.account(), {})).telemetry["4242"].files
    by_path = {c.path: c for c in first}
    assert set(by_path) == {str(metrics), str(WORK_DIR / "hparams.yaml")}
    assert by_path[str(metrics)].data == b'{"step": 1, "loss": 2.0}\n'

    with metrics.open("a") as handle:
        handle.write('{"step": 2, "loss": 1.0}\n')
    cursors = {"4242": {c.path: c.size for c in first}}
    (again,) = (await client.snapshot(cluster.account(), cursors)).telemetry["4242"].files
    assert again.offset == by_path[str(metrics)].size
    assert again.data == b'{"step": 2, "loss": 1.0}\n'


def test_select_files_keeps_newest_per_kind() -> None:
    lines = [f"{100 - i}\t10\t/w/run{i}/metrics.jsonl" for i in range(12)]
    lines += ["50\t5\t/w/hparams.yaml", "49\tx\t/w/bad.jsonl", "48\t3\t/w/readme.md"]
    picked = select_files("\n".join(lines))
    assert [p for p, _ in picked][:2] == ["/w/run0/metrics.jsonl", "/w/run1/metrics.jsonl"]
    assert len(picked) == 8 + 1  # MAX_METRIC_FILES metrics, plus the config
    assert ("/w/hparams.yaml", 5) in picked


# Jump hosts (ssh -J / ProxyJump)


@dataclass
class JumpHost:
    port: int
    host_key: str
    forwarded: list[tuple[str, int]]

    def hop(self, host_key: str | None = None, port: int | None = None) -> Hop:
        return Hop("alice", "127.0.0.1", port or self.port, host_key)


@pytest.fixture
async def jump_host(client: SshSlurmClient, cluster: FakeCluster) -> AsyncIterator[JumpHost]:
    """An SSH server that only forwards connections, like an HPC centre's gateway."""
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    forwarded: list[tuple[str, int]] = []

    class Jump(asyncssh.SSHServer):
        def connection_requested(
            self, dest_host: str, dest_port: int, orig_host: str, orig_port: int
        ) -> bool:
            forwarded.append((dest_host, dest_port))
            return True  # let asyncssh open the forwarded TCP connection

    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[server_key],
        authorized_client_keys=asyncssh.import_authorized_keys(client.public_key_for(OWNER)),
        server_factory=Jump,
    )
    port = server.sockets[0].getsockname()[1]
    yield JumpHost(port, server_key.export_public_key().decode().strip(), forwarded)
    await client.close()
    server.close()
    await server.wait_closed()


def via_jump(cluster: FakeCluster, jump: Hop) -> AccountRef:
    return AccountRef(
        username="alice", host="127.0.0.1", port=cluster.port, jump=jump, owner_id=OWNER
    )


async def test_connects_through_a_jump_host(
    client: SshSlurmClient, cluster: FakeCluster, jump_host: JumpHost
) -> None:
    account = via_jump(cluster, jump_host.hop())

    keys = await client.check(account)
    assert keys.target == cluster.host_key
    assert keys.jump == jump_host.host_key
    assert jump_host.forwarded == [("127.0.0.1", cluster.port)]

    snapshot = await client.snapshot(account, {})
    assert [j.slurm_id for j in snapshot.jobs] == ["4242"]
    assert len(cluster.connections) == 1  # both hops reused across calls
    assert len(jump_host.forwarded) == 1


async def test_jump_host_key_is_pinned(
    client: SshSlurmClient, cluster: FakeCluster, jump_host: JumpHost
) -> None:
    other = asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode()
    with pytest.raises(SlurmError, match=r"jump host 127\.0\.0\.1 presented a different host key"):
        await client.check(via_jump(cluster, jump_host.hop(host_key=other)))


async def test_unreachable_jump_host_is_named(
    client: SshSlurmClient, cluster: FakeCluster, jump_host: JumpHost
) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    with pytest.raises(SlurmError, match=r"jump host 127\.0\.0\.1:\d+ refused the connection"):
        await client.check(via_jump(cluster, jump_host.hop(port=closed_port)))


# Pulse's SSH must not depend on whoever's home directory it runs with.


async def test_unreadable_home_does_not_break_ssh(
    client: SshSlurmClient,
    cluster: FakeCluster,
    jump_host: JumpHost,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In the image, Pulse ran with HOME=/root, which its user can't read."""
    home = tmp_path / "root-home"
    (home / ".ssh").mkdir(parents=True)
    home.chmod(0o000)
    monkeypatch.setenv("HOME", str(home))
    try:
        keys = await client.check(via_jump(cluster, jump_host.hop()))
    finally:
        home.chmod(0o700)
    assert keys.target == cluster.host_key


async def test_ambient_ssh_config_and_agent_are_ignored(
    client: SshSlurmClient, cluster: FakeCluster, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    # If Pulse read this, every connection would go through a dead jump host.
    (home / ".ssh" / "config").write_text("Host *\n  ProxyJump nobody@127.0.0.1:1\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SSH_AUTH_SOCK", str(tmp_path / "no-agent.sock"))

    keys = await client.check(cluster.account())
    assert keys.target == cluster.host_key


# Multi-user isolation and network policy


async def test_another_user_cannot_use_the_owners_authorised_key(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    """User 2 adds the same cluster login: Pulse signs in with user 2's key, which the
    cluster never authorised, so it can't read the owner's jobs."""
    assert (await client.check(cluster.account())).target == cluster.host_key
    with pytest.raises(SlurmError, match="rejected Pulse's SSH key"):
        await client.check(cluster.account(owner_id=2))


async def test_users_without_admin_rights_cannot_reach_private_addresses(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    restricted = replace(cluster.account(), public_only=True)
    with pytest.raises(SlurmError, match="isn't on the public internet"):
        await client.check(restricted)
    assert cluster.connections == []  # refused before connecting

    jump = replace(via_jump(cluster, Hop("alice", "localhost", cluster.port)), public_only=True)
    with pytest.raises(SlurmError, match="isn't on the public internet"):
        await client.check(jump)  # the first hop is the one the server connects to


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("192.168.0.10", False),
        ("169.254.169.254", False),  # cloud metadata service
        ("100.100.1.2", False),  # carrier-grade NAT, e.g. Tailscale
        ("::1", False),
        ("fe80::1%eth0", False),
        ("::ffff:10.0.0.1", False),  # IPv4-mapped private address
    ],
)
def test_public_address_check(address: str, public: bool) -> None:
    assert is_public_ip(address) is public


async def test_telemetry_caches_are_kept_per_account(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    """Job ids repeat across clusters and users; cached samples mustn't cross over."""
    await client.snapshot(cluster.account(), {})
    keys = set(client._stats_cache) | set(client._discovery_cache)
    assert keys and all(k.startswith(f"{OWNER}:alice@127.0.0.1:{cluster.port}/") for k in keys)
