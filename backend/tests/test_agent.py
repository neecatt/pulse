"""The login-node agent script and the server endpoints it talks to."""

import base64
import importlib.util
import os
import socket
import stat
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import uvicorn
from httpx import AsyncClient

from pulse.agent import SCRIPT_PATH
from pulse.config import Settings
from pulse.main import create_app
from pulse.metrics import discovery
from pulse.services.container import Services
from pulse.slurm.parsing import SACCT_FIELDS
from tests.conftest import FakeClock

ACCOUNT = {"username": "alice", "host": "login.secure-hpc.example.org", "connection": "agent"}


def load_agent() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pulse_agent", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_exe(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The agent with fake Slurm binaries on PATH and its config in tmp_path."""
    module = load_agent()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "train-77.out"
    log.write_text("epoch 3/10 loss=0.731\n" * 3)
    work_dir = tmp_path / "run"
    (work_dir / "logs").mkdir(parents=True)
    (work_dir / "logs" / "metrics.jsonl").write_text(
        '{"step": 1, "train/loss": 2.0}\n{"step": 2, "train/loss": 1.5}\n'
    )
    (work_dir / "hparams.yaml").write_text("lr: 0.001\nbatch_size: 32\n")
    (work_dir / ".git").mkdir()
    (work_dir / ".git" / "metrics.jsonl").write_text("ignored\n")
    running = "77|train|gpu|RUNNING|1|cpu=8,gres/gpu=2|cpu=8,gres/gpu=2|gpu07"
    write_exe(
        bin_dir,
        "sacct",
        f'echo "{running}|1767268800|1767269400|Unknown|600|1200|0:0"\n'
        'echo "76|prep|cpu|PENDING|1||cpu=4|None assigned|1767268800|Unknown|Unknown|60|0|0:0"',
    )
    write_exe(
        bin_dir, "scontrol", f'echo "JobId=77 StdOut={log} StdErr=/dev/null WorkDir={work_dir}"'
    )
    write_exe(bin_dir, "srun", 'echo "60, 4000, 8000"; echo "80, 4000, 8000"')
    crontab_file = tmp_path / "crontab.txt"
    write_exe(
        bin_dir,
        "crontab",
        f'if [ "$1" = "-l" ]; then cat {crontab_file} 2>/dev/null || exit 1; '
        f"else cat > {crontab_file}; fi",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("USER", "alice")
    config_dir = tmp_path / "config"
    monkeypatch.setattr(module, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(module, "CONFIG_PATH", str(config_dir / "config.json"))
    monkeypatch.setattr(module, "LOCK_PATH", str(config_dir / "lock"))
    monkeypatch.setattr(module, "STATE_PATH", str(config_dir / "state.json"))
    module.crontab_file = crontab_file  # type: ignore[attr-defined]
    module.work_dir = work_dir  # type: ignore[attr-defined]
    return module


def test_agent_requests_the_columns_the_server_parses() -> None:
    assert load_agent().SACCT_FIELDS == SACCT_FIELDS


def test_agent_finds_the_same_files_as_the_server() -> None:
    agent = load_agent()
    for name in (
        "CHUNK_BYTES",
        "CONFIG_MAX_BYTES",
        "MAX_METRIC_FILES",
        "MAX_CONFIG_FILES",
        "SEARCH_DEPTH",
        "PRUNE_DIRS",
        "CONFIG_NAMES",
    ):
        assert getattr(agent, name) == getattr(discovery, name), name
    for path in (
        "/a/events.out.tfevents.1.host",
        "/a/metrics.jsonl",
        "/a/x_metrics.csv",
        "/a/progress.csv",
        "/a/hparams.yaml",
        "/a/config.json",
        "/a/data.csv",
        "/a/n.txt",
    ):
        assert agent.classify(path) == discovery.classify(path), path


def test_collect_sends_new_file_bytes_only(agent: ModuleType) -> None:
    jsonl = str(agent.work_dir / "logs" / "metrics.jsonl")
    config = str(agent.work_dir / "hparams.yaml")

    files = {f["path"]: f for f in agent.collect(False, {}, {})["jobs"]["77"]["files"]}
    assert set(files) == {jsonl, config}  # .git is pruned
    assert files[jsonl]["offset"] == 0
    assert base64.b64decode(files[jsonl]["data"]).count(b"\n") == 2

    size = files[jsonl]["size"]
    cursors = {"77": {jsonl: size, config: files[config]["size"]}}
    assert agent.collect(False, cursors, {})["jobs"]["77"]["files"] == []

    with open(jsonl, "a") as handle:
        handle.write('{"step": 3, "train/loss": 1.1}\n')
    (again,) = agent.collect(False, cursors, {})["jobs"]["77"]["files"]
    assert again["offset"] == size
    assert base64.b64decode(again["data"]) == b'{"step": 3, "train/loss": 1.1}\n'


def test_collect_sends_raw_output_for_running_jobs(agent: ModuleType) -> None:
    payload = agent.collect(True, {}, {})

    assert payload["error"] is None
    assert payload["sacct"].count("\n") == 2
    assert set(payload["jobs"]) == {"77"}  # only running jobs get telemetry
    job = payload["jobs"]["77"]
    assert job["log_tail"][-1] == "epoch 3/10 loss=0.731"
    assert isinstance(job["log_mtime"], int)
    assert "60, 4000" in job["nvidia_smi"]
    assert "nvidia_smi" not in agent.collect(False, {}, {})["jobs"]["77"]


def test_collect_reports_slurm_failures(agent: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    assert "sacct failed" in agent.collect(False, {}, {})["error"]


async def create_agent_account(client: AsyncClient) -> tuple[int, str]:
    account = (await client.post("/api/accounts", json=ACCOUNT)).json()
    assert account["connection"] == "agent"
    token = (await client.post(f"/api/accounts/{account['id']}/agent-token")).json()["token"]
    return account["id"], token


async def test_report_requires_a_valid_token(client: AsyncClient, agent: ModuleType) -> None:
    await create_agent_account(client)
    payload = agent.collect(False, {}, {})
    for header in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic x"}):
        response = await client.post("/api/agent/report", json=payload, headers=header)
        assert response.status_code == 401


async def test_reports_feed_jobs_events_and_status(
    client: AsyncClient, agent: ModuleType, clock: FakeClock
) -> None:
    account_id, token = await create_agent_account(client)
    auth = {"Authorization": f"Bearer {token}"}
    check = (await client.post(f"/api/accounts/{account_id}/check")).json()
    assert check == {
        "ok": False,
        "error": "Waiting for the agent's first report from the login node.",
    }

    ack = (
        await client.post("/api/agent/report", json=agent.collect(True, {}, {}), headers=auth)
    ).json()
    assert ack["next_report_in"] == 60  # nobody watching: idle pace
    jsonl = agent.work_dir / "logs" / "metrics.jsonl"
    assert ack["cursors"]["77"][str(jsonl)] == len(jsonl.read_bytes())
    jobs = {j["slurm_id"]: j for j in (await client.get("/api/jobs")).json()}
    assert jobs["77"]["state"] == "RUNNING"
    assert jobs["77"]["epoch"] == "3/10"
    assert jobs["77"]["gpu_util"] == 70.0
    assert (await client.post(f"/api/accounts/{account_id}/check")).json()["ok"] is True
    metrics = (await client.get(f"/api/jobs/{jobs['77']['id']}/metrics")).json()
    assert [p["v"] for p in metrics["metrics"]["train/loss"]] == [2.0, 1.5]
    assert metrics["hparams"] == {"lr": 0.001, "batch_size": 32}

    # Second report without GPU data keeps the last GPU reading.
    clock.advance(30)
    await client.post("/api/agent/report", json=agent.collect(False, {}, {}), headers=auth)
    assert (await client.get("/api/jobs/1")).json()["gpu_util"] == 70.0

    # An agent-side error surfaces on the account.
    await client.post(
        "/api/agent/report",
        json={"agent_version": "1", "sacct": "", "error": "sacct failed: boom"},
        headers=auth,
    )
    assert "boom" in (await client.get("/api/accounts")).json()[0]["last_error"]


async def test_new_token_revokes_the_old_one(client: AsyncClient, agent: ModuleType) -> None:
    account_id, old = await create_agent_account(client)
    await client.post(f"/api/accounts/{account_id}/agent-token")
    response = await client.post(
        "/api/agent/report",
        json=agent.collect(False, {}, {}),
        headers={"Authorization": f"Bearer {old}"},
    )
    assert response.status_code == 401


async def test_direct_accounts_cannot_get_tokens(client: AsyncClient) -> None:
    account = (await client.post("/api/accounts", json=ACCOUNT | {"connection": "direct"})).json()
    assert (await client.post(f"/api/accounts/{account['id']}/agent-token")).status_code == 409


async def test_poller_skips_agents_and_flags_silent_ones(
    client: AsyncClient, services: Services, agent: ModuleType, clock: FakeClock
) -> None:
    _, token = await create_agent_account(client)
    await client.post(
        "/api/agent/report",
        json=agent.collect(False, {}, {}),
        headers={"Authorization": f"Bearer {token}"},
    )
    await services.poller.poll_all()
    assert (await client.get("/api/accounts")).json()[0]["last_error"] is None

    clock.advance(services.settings.agent_stale_seconds + 1)
    await services.poller.poll_all()
    assert "stopped reporting" in (await client.get("/api/accounts")).json()[0]["last_error"]


async def test_agent_script_is_downloadable(client: AsyncClient) -> None:
    response = await client.get("/api/agent/script")
    assert response.status_code == 200
    assert response.text.startswith("#!/usr/bin/env python3")


# End to end: the real script over real HTTP.


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[str]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'live.db'}",
        _env_file=None,  # type: ignore[call-arg]
    )
    config = uvicorn.Config(
        create_app(settings, run_poller=False), host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_install_verifies_connection_and_adds_cron_entry(
    agent: ModuleType, live_server: str
) -> None:
    import httpx

    account = httpx.post(f"{live_server}/api/accounts", json=ACCOUNT).json()
    token = httpx.post(f"{live_server}/api/accounts/{account['id']}/agent-token").json()["token"]

    assert agent.install(live_server, "wrong-token") == 1
    assert agent.install(live_server, token) == 0

    cron = agent.crontab_file.read_text()
    assert cron.count("# pulse-agent") == 1
    assert " run " in cron
    assert agent.status() == 0
    jobs = httpx.get(f"{live_server}/api/jobs").json()
    assert [j["slurm_id"] for j in jobs] == ["77", "76"]

    assert agent.install(live_server, token) == 0  # idempotent
    assert agent.crontab_file.read_text().count("# pulse-agent") == 1

    assert agent.uninstall() == 0
    assert "# pulse-agent" not in agent.crontab_file.read_text()
    assert agent.status() == 1  # no longer configured
