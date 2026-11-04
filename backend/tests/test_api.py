from httpx import AsyncClient

from pulse.services.container import Services
from tests.conftest import FakeClock

ACCOUNT = {"cluster": "Leonardo", "username": "alice", "host": "login.leonardo.example.org"}


async def add_account(client: AsyncClient, **overrides: object) -> dict:  # type: ignore[type-arg]
    response = await client.post("/api/accounts", json=ACCOUNT | overrides)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_health(client: AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    assert body["status"] == "ok"
    assert body["slurm_backend"] == "mock"
    assert body["version"]


async def test_account_crud(client: AsyncClient) -> None:
    account = await add_account(client)
    assert account["color"] == 0
    assert (await client.post("/api/accounts", json=ACCOUNT)).status_code == 409

    second = await add_account(client, username="alice2")
    assert second["color"] == 1

    patched = await client.patch(f"/api/accounts/{account['id']}", json={"notify": False})
    assert patched.json()["notify"] is False

    assert (await client.delete(f"/api/accounts/{account['id']}")).status_code == 204
    remaining = (await client.get("/api/accounts")).json()
    assert [a["id"] for a in remaining] == [second["id"]]


async def test_account_validation(client: AsyncClient) -> None:
    bad = await client.post("/api/accounts", json=ACCOUNT | {"username": "alice; rm -rf /"})
    assert bad.status_code == 422


async def test_account_check_reports_unreachable_host(client: AsyncClient) -> None:
    account = await add_account(client, host="down.invalid")
    result = (await client.post(f"/api/accounts/{account['id']}/check")).json()
    assert result["ok"] is False
    assert "unreachable" in result["error"]


async def test_poll_populates_jobs_then_emits_events(
    client: AsyncClient, services: Services, clock: FakeClock
) -> None:
    account = await add_account(client)

    await services.poller.poll_account(account["id"])
    jobs = (await client.get("/api/jobs")).json()
    assert jobs, "first poll should record jobs"
    assert jobs[0]["state"] == "RUNNING"  # active jobs sort first
    assert (await client.get("/api/events")).json() == [], "first poll must not announce"

    # Two steps: gnn-sweep-17 crosses 90% of its time limit, then completes.
    for seconds in (60, 240):
        clock.advance(seconds)
        await services.poller.poll_account(account["id"])
    events = (await client.get("/api/events")).json()
    kinds = {e["kind"] for e in events}
    assert {"job_started", "job_completed", "job_failed", "job_time_limit"} <= kinds

    failed = next(j for j in (await client.get("/api/jobs")).json() if j["name"] == "mixtral-eval")
    assert failed["state"] == "FAILED"
    assert failed["reason"] == "OUT_OF_MEMORY"

    running = next(j for j in (await client.get("/api/jobs")).json() if j["name"] == "llama-7b-sft")
    detail = (await client.get(f"/api/jobs/{running['id']}")).json()
    assert detail["log_tail"]
    assert len(detail["series"]["gpu_util"]) == 3  # one sample per poll
    assert 0 < detail["time_used"] < 1
    assert detail["primary_metric"] == "loss"
    assert len(detail["loss_trend"]) > 1

    metrics = (await client.get(f"/api/jobs/{running['id']}/metrics")).json()
    # From stdout ("[step N] ... loss=... lr=...") and the job's metrics.jsonl.
    assert {"loss", "lr", "train/loss", "train/acc", "val/loss"} <= set(metrics["metrics"])
    steps = [p["s"] for p in metrics["metrics"]["train/loss"]]
    assert steps == sorted(steps) and len(steps) == len(set(steps))  # no duplicates
    assert len(steps) > 500  # 14 h of history, read in 256 KB chunks over 3 polls
    assert metrics["hparams"]["optimizer.name"] == "adamw"
    assert "gpu_util" not in metrics["metrics"]


async def test_job_notes_and_tags(client: AsyncClient, services: Services) -> None:
    account = await add_account(client)
    await services.poller.poll_account(account["id"])
    job = (await client.get("/api/jobs")).json()[0]

    body = {"note": "  baseline run  ", "tags": ["baseline", "lr-sweep", "baseline"]}
    updated = (await client.patch(f"/api/jobs/{job['id']}", json=body)).json()
    assert updated["note"] == "baseline run"
    assert updated["tags"] == ["baseline", "lr-sweep"]

    await services.poller.poll_account(account["id"])  # annotations survive polling
    listed = next(j for j in (await client.get("/api/jobs")).json() if j["id"] == job["id"])
    assert listed["tags"] == ["baseline", "lr-sweep"]

    too_long = await client.patch(f"/api/jobs/{job['id']}", json={"tags": ["x" * 40]})
    assert too_long.status_code == 422


async def test_poll_records_error_for_unreachable_account(
    client: AsyncClient, services: Services
) -> None:
    account = await add_account(client, host="down.invalid")
    await services.poller.poll_account(account["id"])
    stored = (await client.get("/api/accounts")).json()[0]
    assert "unreachable" in stored["last_error"]


async def test_jobs_are_scoped_to_account_filter(client: AsyncClient, services: Services) -> None:
    a = await add_account(client)
    b = await add_account(client, username="bob")
    await services.poller.poll_all()
    only_b = (await client.get("/api/jobs", params={"account_id": b["id"]})).json()
    assert only_b
    assert {j["account_id"] for j in only_b} == {b["id"]}
    assert (await client.get("/api/jobs/999999")).status_code == 404
    assert a["id"] != b["id"]


async def test_preferences_round_trip(client: AsyncClient) -> None:
    prefs = (await client.get("/api/preferences")).json()["alerts"]
    assert all(prefs.values())

    updated = await client.patch("/api/preferences", json={"alerts": {"job_started": False}})
    assert updated.json()["alerts"]["job_started"] is False
    assert updated.json()["alerts"]["job_failed"] is True


async def test_monitoring_preferences(client: AsyncClient) -> None:
    monitoring = (await client.get("/api/preferences")).json()["monitoring"]
    assert monitoring == {
        "live_refresh_seconds": 10,
        "idle_refresh_seconds": 60,
        "stall_minutes": 15,
        "time_limit_warning_percent": 90,
        "diverge_percent": 50,
        "plateau_minutes": 60,
    }

    body = {"monitoring": {"stall_minutes": 30, "time_limit_warning_percent": 80}}
    updated = (await client.patch("/api/preferences", json=body)).json()
    assert updated["monitoring"]["stall_minutes"] == 30
    assert updated["monitoring"]["live_refresh_seconds"] == 10  # untouched
    assert updated["alerts"]["job_started"] is True

    too_fast = {"monitoring": {"live_refresh_seconds": 1}}
    assert (await client.patch("/api/preferences", json=too_fast)).status_code == 422


async def test_push_subscription_lifecycle(client: AsyncClient) -> None:
    config = (await client.get("/api/push/config")).json()
    assert config == {"enabled": False, "public_key": None}

    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert (await client.post("/api/push/subscriptions", json=sub)).status_code == 204
    assert (await client.post("/api/push/subscriptions", json=sub)).status_code == 204  # upsert

    # Delivery is a no-op without VAPID keys.
    assert (await client.post("/api/push/test")).json() == {"delivered": 0}

    response = await client.request(
        "DELETE", "/api/push/subscriptions", json={"endpoint": sub["endpoint"]}
    )
    assert response.status_code == 204


async def test_account_with_jump_host(client: AsyncClient) -> None:
    body = ACCOUNT | {"jump_host": "csnhr.nhr.fau.de", "username": "b268dc21"}
    created = (await client.post("/api/accounts", json=body)).json()
    assert created["jump_host"] == "csnhr.nhr.fau.de"
    assert created["jump_port"] == 22
    assert created["jump_username"] is None  # same as the login username

    bad = await client.post("/api/accounts", json=ACCOUNT | {"jump_host": "not a host!"})
    assert bad.status_code == 422
