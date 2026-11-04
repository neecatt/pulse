from pulse.domain import JobState
from pulse.slurm.base import AccountRef
from pulse.slurm.mock import MockSlurmClient
from tests.conftest import FakeClock

ACCOUNT = AccountRef(username="alice", host="cluster.example.org")


def states(snapshot_jobs: list) -> dict[str, JobState]:  # type: ignore[type-arg]
    return {j.name: j.state for j in snapshot_jobs}


async def test_jobs_progress_over_time(clock: FakeClock) -> None:
    client = MockSlurmClient(clock)
    first = states((await client.snapshot(ACCOUNT)).jobs)
    assert first["diffusion-ft"] is JobState.PENDING
    assert first["mixtral-eval"] is JobState.RUNNING

    clock.advance(300)
    later = states((await client.snapshot(ACCOUNT)).jobs)
    assert later["diffusion-ft"] is JobState.RUNNING
    assert later["mixtral-eval"] is JobState.FAILED
    assert later["gnn-sweep-17"] is JobState.COMPLETED


async def test_running_jobs_have_telemetry(clock: FakeClock) -> None:
    snapshot = await MockSlurmClient(clock).snapshot(ACCOUNT)
    running = [j for j in snapshot.jobs if j.state is JobState.RUNNING]
    assert running
    assert set(snapshot.telemetry) == {j.slurm_id for j in running}
    assert all(t.loss is not None for t in snapshot.telemetry.values())


async def test_job_ids_are_stable_per_account(clock: FakeClock) -> None:
    client = MockSlurmClient(clock)
    a = [j.slurm_id for j in (await client.snapshot(ACCOUNT)).jobs]
    b = [j.slurm_id for j in (await client.snapshot(ACCOUNT)).jobs]
    other = AccountRef(username="bob", host="cluster.example.org")
    c = [j.slurm_id for j in (await client.snapshot(other)).jobs]
    assert a == b
    assert a != c
