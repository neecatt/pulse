"""Parsers for Slurm CLI output. Pure functions; no I/O."""

import re
from datetime import UTC, datetime

from pulse.domain import JobState
from pulse.slurm.base import NodeStats, SlurmJob

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
                array_id=array_id(row["JobID"]),
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


def array_id(slurm_id: str) -> str | None:
    """``123_4`` and ``123_[5-9%2]`` belong to array ``123``; others to none."""
    head, sep, _ = slurm_id.partition("_")
    return head if sep and head.isdigit() else None


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


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


# Per-node usage. One `srun` step runs this on every node of the job and prints
# tab-separated lines: "<node> cpu <pct>", "<node> mem <pct>" and
# "<node> gpu <index> <util%> <mem used> <mem total>". The agent ships the same
# script (checked by a test).
NODE_STATS_SCRIPT = r"""h=$(hostname -s)
vmstat 1 2 | tail -1 | awk -v h="$h" '{print h "\tcpu\t" 100-$15}'
awk -v h="$h" '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2}
  END{if (t>0) print h "\tmem\t" (t-a)*100/t}' /proc/meminfo
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total \
  --format=csv,noheader,nounits 2>/dev/null |
  awk -F', *' -v h="$h" '{print h "\tgpu\t" $1 "\t" $2 "\t" $3 "\t" $4}'
"""


def parse_node_stats(output: str) -> dict[str, NodeStats]:
    nodes: dict[str, NodeStats] = {}
    for line in output.splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 3 or not parts[0]:
            continue
        node = nodes.setdefault(parts[0], {"cpu": None, "mem": None, "gpus": []})
        try:
            if parts[1] in ("cpu", "mem") and len(parts) == 3:
                node[parts[1]] = round(float(parts[2]), 1)  # type: ignore[literal-required]
            elif parts[1] == "gpu" and len(parts) == 6:
                util, used, total = (float(v) for v in parts[3:])
                mem = 100 * used / total if total > 0 else 0.0
                node["gpus"].append({"util": round(util, 1), "mem": round(mem, 1)})
        except ValueError:
            continue
    return nodes


def mean_gpu_usage(nodes: dict[str, NodeStats]) -> tuple[float | None, float | None]:
    """Job-wide GPU utilisation and memory (%), averaged over every GPU."""
    gpus = [gpu for node in nodes.values() for gpu in node["gpus"]]
    return _mean([g["util"] for g in gpus]), _mean([g["mem"] for g in gpus])
