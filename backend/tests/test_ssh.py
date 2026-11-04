"""SshSlurmClient against an in-process SSH server that fakes the Slurm CLI."""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import asyncssh
import pytest

from pulse.config import Settings
from pulse.domain import JobState
from pulse.slurm.base import AccountRef, SlurmError
from pulse.slurm.ssh import SshSlurmClient

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
        process.stdout.write("JobId=4242 JobName=train StdOut=/scratch/train-4242.out\n")
    elif command.startswith("stat -c %Y"):
        process.stdout.write(f"{int(time.time())}\n[step 10] epoch 2/5 loss=0.512\n")
    elif "srun" in command:
        process.stdout.write("80, 1000, 2000\n90, 1000, 2000\n")
    else:
        process.exit(127)
        return
    process.exit(0)


@dataclass
class FakeCluster:
    port: int
    host_key: str
    connections: list[asyncssh.SSHServerConnection]

    def account(self, host_key: str | None = None) -> AccountRef:
        return AccountRef(username="alice", host="127.0.0.1", port=self.port, host_key=host_key)


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

    assert client.public_key is not None
    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[server_key],
        authorized_client_keys=asyncssh.import_authorized_keys(client.public_key),
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
    key_file = tmp_path / "pulse_ed25519"
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert first.public_key and first.public_key.startswith("ssh-ed25519 ")
    assert make_client(tmp_path).public_key == first.public_key


async def test_check_returns_server_host_key(client: SshSlurmClient, cluster: FakeCluster) -> None:
    assert await client.check(cluster.account()) == cluster.host_key


async def test_snapshot_parses_jobs_and_telemetry(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    snapshot = await client.snapshot(cluster.account())

    (job,) = snapshot.jobs
    assert job.state is JobState.RUNNING
    assert job.gpus == 4
    telemetry = snapshot.telemetry["4242"]
    assert telemetry.loss == 0.512
    assert telemetry.epoch == "2/5"
    assert telemetry.gpu_util == 85.0
    assert telemetry.gpu_mem == 50.0
    assert snapshot.host_key == cluster.host_key


async def test_connection_is_reused_across_polls(
    client: SshSlurmClient, cluster: FakeCluster
) -> None:
    for _ in range(3):
        await client.snapshot(cluster.account())
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
    assert await client.check(cluster.account(host_key=cluster.host_key)) == cluster.host_key


async def test_unauthorised_key_gets_actionable_error(tmp_path: Path, cluster: FakeCluster) -> None:
    stranger = make_client(tmp_path / "other")
    try:
        with pytest.raises(SlurmError, match="Authorise the key"):
            await stranger.check(cluster.account())
    finally:
        await stranger.close()
