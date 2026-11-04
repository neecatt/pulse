"""Parsers for Slurm CLI output. Pure functions; no I/O."""

import re
from datetime import UTC, datetime

from pulse.domain import JobState
from pulse.slurm.base import SlurmJob

# Order matters: this is the column order requested from sacct.
SACCT_FIELDS = (
    "JobID",
    "JobName",
    "Partition",
    "State",
    "NNodes",
    "AllocTRES",
    "ReqTRES",
    "NodeList",
    "Submit",
    "Start",
    "End",
    "TimelimitRaw",
    "ElapsedRaw",
    "ExitCode",
)

_STATE_MAP: dict[str, JobState] = {
    "PENDING": JobState.PENDING,
    "REQUEUED": JobState.PENDING,
    "SUSPENDED": JobState.PENDING,
    "PREEMPTED": JobState.PENDING,
    "RESIZING": JobState.RUNNING,
    "RUNNING": JobState.RUNNING,
    "COMPLETING": JobState.RUNNING,
    "COMPLETED": JobState.COMPLETED,
    "CANCELLED": JobState.CANCELLED,
    "TIMEOUT": JobState.TIMEOUT,
    "DEADLINE": JobState.TIMEOUT,
    "FAILED": JobState.FAILED,
    "OUT_OF_MEMORY": JobState.FAILED,
    "NODE_FAIL": JobState.FAILED,
    "BOOT_FAIL": JobState.FAILED,
}

_GPU_TRES = re.compile(r"gres/gpu(?::[\w.-]+)?=(\d+)")
_LOSS = re.compile(r"\bloss\s*[=:]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", re.IGNORECASE)
_EPOCH = re.compile(r"\bepoch\s*[=:]?\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
SAFE_JOB_ID = re.compile(r"^[0-9][0-9_+\[\]-]*$")


def parse_state(raw: str) -> tuple[JobState, str | None]:
    """Map a raw sacct state ("CANCELLED by 123", "OUT_OF_MEMORY") to (state, reason).

    The reason keeps the raw state when it was folded into a broader one.
    """
    head = raw.split()[0] if raw.strip() else "PENDING"
    state = _STATE_MAP.get(head, JobState.FAILED)
    reason = None if head == state.value else head
    return state, reason


def parse_gpus(tres: str) -> int:
    """Count GPUs in a TRES string such as ``cpu=8,gres/gpu=4,gres/gpu:a100=4``.

    Slurm lists both the generic and the typed entry for the same GPUs, so the
    generic count wins when present.
    """
    generic = re.search(r"gres/gpu=(\d+)", tres)
    if generic:
        return int(generic.group(1))
    return sum(int(n) for n in _GPU_TRES.findall(tres))


def _epoch_time(raw: str) -> datetime | None:
    # Times are requested as Unix epochs via SLURM_TIME_FORMAT=%s.
    return datetime.fromtimestamp(int(raw), UTC) if raw.isdigit() and raw != "0" else None


def _int_or_none(raw: str) -> int | None:
    return int(raw) if raw.isdigit() else None


def parse_sacct(output: str) -> list[SlurmJob]:
    """Parse ``sacct -X -P -n -o <SACCT_FIELDS>`` output (pipe-separated)."""
    jobs: list[SlurmJob] = []
    for line in output.splitlines():
        cols = line.split("|")
        if len(cols) != len(SACCT_FIELDS):
            continue
        row = dict(zip(SACCT_FIELDS, cols, strict=True))
        state, reason = parse_state(row["State"])
        limit_min = _int_or_none(row["TimelimitRaw"])
        exit_raw = row["ExitCode"].split(":")[0]
        node_list = row["NodeList"]
        jobs.append(
            SlurmJob(
                slurm_id=row["JobID"],
                name=row["JobName"],
                partition=row["Partition"],
                state=state,
                reason=reason,
                nodes=_int_or_none(row["NNodes"]) or 0,
                gpus=parse_gpus(row["AllocTRES"] or row["ReqTRES"]),
                node_list=None if node_list in ("", "None assigned") else node_list,
                submit_time=_epoch_time(row["Submit"]),
                start_time=_epoch_time(row["Start"]),
                end_time=_epoch_time(row["End"]),
                time_limit_s=limit_min * 60 if limit_min is not None else None,
                elapsed_s=_int_or_none(row["ElapsedRaw"]) or 0,
                exit_code=_int_or_none(exit_raw) if state.is_terminal else None,
            )
        )
    return jobs


def parse_scontrol_field(output: str, field: str) -> str | None:
    """Extract ``Field=value`` from one-line ``scontrol show job -o`` output."""
    match = re.search(rf"(?:^|\s){re.escape(field)}=(\S+)", output)
    return match.group(1) if match else None


def parse_training_log(lines: list[str]) -> tuple[float | None, str | None]:
    """Latest loss value and ``epoch a/b`` found in a log tail."""
    loss: float | None = None
    epoch: str | None = None
    for line in lines:
        if m := _LOSS.search(line):
            loss = float(m.group(1))
        if m := _EPOCH.search(line):
            epoch = f"{m.group(1)}/{m.group(2)}"
    return loss, epoch


def parse_nvidia_smi(output: str) -> tuple[float | None, float | None]:
    """Mean GPU utilisation and memory use (%) across GPUs.

    Expects ``nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total
    --format=csv,noheader,nounits`` output.
    """
    utils: list[float] = []
    mems: list[float] = []
    for line in output.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            util, used, total = (float(p) for p in parts)
        except ValueError:
            continue
        utils.append(util)
        if total > 0:
            mems.append(100 * used / total)
    return _mean(utils), _mean(mems)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None
