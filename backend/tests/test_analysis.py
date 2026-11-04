"""Phase 2 end to end on the simulated cluster: sweeps, metric alerts, runs, nodes."""

from httpx import AsyncClient

from pulse.services.container import Services
from tests.conftest import FakeClock

ACCOUNT = {"username": "alice", "host": "lumi.example.org"}


async def setup(client: AsyncClient, services: Services) -> int:
    account = (await client.post("/api/accounts", json=ACCOUNT)).json()
    await services.poller.poll_account(account["id"])
    return int(account["id"])


async def test_job_array_is_one_sweep(client: AsyncClient, services: Services) -> None:
    await setup(client, services)
    sweep = [j for j in (await client.get("/api/jobs")).json() if j["name"] == "lr-sweep"]
    assert len(sweep) == 6
    assert len({j["array_id"] for j in sweep}) == 1
    assert sorted(j["slurm_id"].split("_")[1] for j in sweep) == list("012345")
    assert sum(j["state"] == "PENDING" for j in sweep) == 2


async def test_runs_table_has_summaries_and_hparams(
    client: AsyncClient, services: Services
) -> None:
    await setup(client, services)
    array_id = next(j for j in (await client.get("/api/jobs")).json() if j["array_id"])["array_id"]

    runs = (await client.get("/api/runs", params={"array_id": array_id})).json()
    running = [r for r in runs if r["state"] == "RUNNING"]
    assert len(runs) == 6 and len(running) == 4
    assert {r["hparams"]["optimizer.lr"] for r in running} == {1e-4, 3e-4, 1e-3, 3e-3}
    worst = max(running, key=lambda r: r["metric_stats"]["train/loss"]["min"])
    assert worst["hparams"]["optimizer.lr"] == 1e-4  # the scripted too-slow learning rate
    assert all(r["primary_metric"] == "train/loss" for r in running)
    assert not any(name.startswith("sys/") for r in runs for name in r["metric_stats"])


async def test_diverging_task_raises_alerts_once(
    client: AsyncClient, services: Services, clock: FakeClock
) -> None:
    account_id = await setup(client, services)
    for _ in range(5):  # 25 minutes: the unstable task diverges, then goes NaN
        clock.advance(300)
        await services.poller.poll_account(account_id)

    events = (await client.get("/api/events")).json()
    sweep_alerts = [e["kind"] for e in events if "lr-sweep" in e["message"]]
    assert sweep_alerts.count("job_diverging") == 1
    assert sweep_alerts.count("job_nan") == 1
    nan = next(e for e in events if e["kind"] == "job_nan")
    assert "train/loss" in nan["message"]


async def test_job_page_has_per_node_usage(client: AsyncClient, services: Services) -> None:
    account_id = await setup(client, services)
    await services.poller.poll_account(account_id)
    llama = next(j for j in (await client.get("/api/jobs")).json() if j["name"] == "llama-7b-sft")

    detail = (await client.get(f"/api/jobs/{llama['id']}")).json()
    assert len(detail["node_stats"]) == 8  # nodes
    first = next(iter(detail["node_stats"].values()))
    assert len(first["gpus"]) == 4 and first["cpu"] is not None
    node_series = {k for k in detail["series"] if k.startswith("sys/")}
    assert len(node_series) == 8 * 4  # cpu, mem, gpu, gpu_mem per node
    metrics = (await client.get(f"/api/jobs/{llama['id']}/metrics")).json()["metrics"]
    assert not any(name.startswith("sys/") for name in metrics)
