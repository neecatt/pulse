from datetime import UTC, datetime

import pytest

from pulse.domain import JobState
from pulse.slurm.base import SlurmJob
from pulse.slurm.parsing import (
    failure_summary,
    failures_to_read,
    mean_gpu_usage,
    parse_gpus,
    parse_node_stats,
    parse_sacct,
    parse_scontrol_field,
    parse_state,
    parse_training_log,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RUNNING", (JobState.RUNNING, None)),
        ("COMPLETING", (JobState.RUNNING, "COMPLETING")),
        ("CANCELLED by 1234", (JobState.CANCELLED, None)),
        ("OUT_OF_MEMORY", (JobState.FAILED, "OUT_OF_MEMORY")),
        ("REQUEUED", (JobState.PENDING, "REQUEUED")),
        ("REQUEUE_HOLD", (JobState.PENDING, "REQUEUE_HOLD")),
        ("STAGE_OUT", (JobState.RUNNING, "STAGE_OUT")),
        ("REVOKED", (JobState.CANCELLED, "REVOKED")),
        ("SOMETHING_NEW", (JobState.FAILED, "SOMETHING_NEW")),
    ],
)
def test_parse_state(raw: str, expected: tuple[JobState, str | None]) -> None:
    assert parse_state(raw) == expected


@pytest.mark.parametrize(
    ("tres", "gpus"),
    [
        ("billing=8,cpu=8,gres/gpu=4,gres/gpu:a100=4,mem=64G,node=1", 4),
        ("cpu=8,gres/gpu:a100=2,gres/gpu:h100=2", 4),
        ("cpu=16,mem=32G,node=1", 0),
        ("", 0),
    ],
)
def test_parse_gpus(tres: str, gpus: int) -> None:
    assert parse_gpus(tres) == gpus


def test_parse_sacct() -> None:
    output = (
        "4242|train|gpu|RUNNING|2|cpu=16,gres/gpu=8|cpu=16,gres/gpu=8|gpu[001-002]"
        "|1767268800|1767269400|Unknown|1440|3600|0:0\n"
        "4243|eval|gpu|PENDING|1||cpu=4,gres/gpu=1|None assigned|1767268800|Unknown|Unknown"
        "|60|0|0:0\n"
        "4240|prep|cpu|FAILED|1|cpu=4|cpu=4|cpu007|1767260000|1767260100|1767260200"
        "|UNLIMITED|100|2:0\n"
        "garbage line\n"
    )
    running, pending, failed = parse_sacct(output)

    assert running.slurm_id == "4242"
    assert running.state is JobState.RUNNING
    assert running.gpus == 8
    assert running.nodes == 2
    assert running.start_time == datetime.fromtimestamp(1767269400, UTC)
    assert running.end_time is None
    assert running.time_limit_s == 1440 * 60
    assert running.elapsed_s == 3600
    assert running.exit_code is None

    assert pending.state is JobState.PENDING
    assert pending.gpus == 1  # falls back to ReqTRES
    assert pending.node_list is None

    assert failed.state is JobState.FAILED
    assert failed.time_limit_s is None
    assert failed.exit_code == 2


def test_parse_scontrol_field() -> None:
    out = "JobId=42 JobName=train StdOut=/scratch/u/logs/train-42.out StdErr=/dev/null"
    assert parse_scontrol_field(out, "StdOut") == "/scratch/u/logs/train-42.out"
    assert parse_scontrol_field(out, "Missing") is None


def test_parse_training_log_takes_latest_values() -> None:
    lines = [
        "Epoch 1/10 step 100 loss=2.31",
        "noise",
        "epoch: 2 / 10 | train_loss: 1.5e-1",
        "[INFO] Loss: 0.142",
    ]
    assert parse_training_log(lines) == (0.142, "2/10")
    assert parse_training_log(["nothing here"]) == (None, None)


def test_parse_node_stats() -> None:
    output = (
        "gpu001\tcpu\t63.0\n"
        "gpu001\tmem\t41.25\n"
        "gpu001\tgpu\t0\t90\t40000\t80000\n"
        "gpu001\tgpu\t1\t70\t20000\t80000\n"
        "gpu002\tcpu\t12\n"
        "gpu002\tmem\tnot-a-number\n"
        "srun: warning: something\n"
    )
    nodes = parse_node_stats(output)
    assert nodes["gpu001"] == {
        "cpu": 63.0,
        "mem": 41.2,
        "gpus": [{"util": 90.0, "mem": 50.0}, {"util": 70.0, "mem": 25.0}],
    }
    assert nodes["gpu002"] == {"cpu": 12.0, "mem": None, "gpus": []}
    assert mean_gpu_usage(nodes) == (80.0, 37.5)
    assert mean_gpu_usage({}) == (None, None)


@pytest.mark.parametrize(
    ("lines", "summary"),
    [
        (
            [
                "Traceback (most recent call last):",
                '  File "train.py", line 3, in <module>',
                "[rank0]: torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2 GiB",
                "torch.distributed.elastic.multiprocessing.errors.ChildFailedError: ",
                "srun: error: gpu012: task 0: Exited with exit code 1",
            ],
            "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2 GiB",
        ),
        (["epoch 1/3\r\x1b[2Kepoch 2/3", "AssertionError"], "AssertionError"),
        (
            ["slurmstepd: error: Detected 1 oom_kill event in StepId=7.batch."],
            "Ran out of memory and was killed",
        ),
        (["loading data", "Killed"], "Killed by the system, often for using too much memory"),
        (["ok", "bash: python: command not found"], "bash: python: command not found"),
        (["step 10 loss=0.5", "srun: error: gpu01: task 0: Exited with exit code 2"], None),
        ([], None),
    ],
)
def test_failure_summary(lines: list[str], summary: str | None) -> None:
    assert failure_summary(lines) == summary


def test_failure_summary_is_one_short_line() -> None:
    summary = failure_summary(["ValueError: " + "x" * 1000])
    assert summary is not None
    assert len(summary) == 300
    assert summary.endswith("…")


def test_failures_to_read_skips_known_and_takes_newest() -> None:
    def failed(n: int) -> SlurmJob:
        end = datetime(2026, 1, 1, n % 24, tzinfo=UTC)
        return SlurmJob(str(n), "j", "gpu", JobState.FAILED, end_time=end)

    jobs = [failed(n) for n in range(12)]
    jobs.append(SlurmJob("99", "ok", "gpu", JobState.COMPLETED))
    picked = [j.slurm_id for j in failures_to_read(jobs, {"11"})]
    assert picked == ["10", "9", "8", "7", "6", "5", "4", "3"]
