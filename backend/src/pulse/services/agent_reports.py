"""Turn raw output sent by the login-node agent into an AccountSnapshot."""

import binascii
from datetime import UTC, datetime

from pulse.domain import JobState
from pulse.metrics.ingest import decode_chunk_data
from pulse.schemas import AgentFile, AgentReport
from pulse.slurm.base import AccountSnapshot, FileChunk, JobTelemetry, SlurmError
from pulse.slurm.parsing import (
    failure_summary,
    mean_gpu_usage,
    parse_node_stats,
    parse_sacct,
    parse_training_log,
)


def snapshot_from_report(report: AgentReport) -> AccountSnapshot | SlurmError:
    if report.error:
        return SlurmError(f"Agent: {report.error}")
    jobs = parse_sacct(report.sacct)
    telemetry: dict[str, JobTelemetry] = {}
    failed = {j.slurm_id for j in jobs if j.state is JobState.FAILED}
    for slurm_id, raw in report.jobs.items():
        loss, epoch = parse_training_log(raw.log_tail)
        nodes = parse_node_stats(raw.node_stats) if raw.node_stats else {}
        gpu_util, gpu_mem = mean_gpu_usage(nodes)
        telemetry[slurm_id] = JobTelemetry(
            loss=loss,
            epoch=epoch,
            gpu_util=gpu_util,
            gpu_mem=gpu_mem,
            nodes=nodes,
            log_tail=raw.log_tail,
            log_updated_at=datetime.fromtimestamp(raw.log_mtime, UTC) if raw.log_mtime else None,
            files=[c for c in map(_chunk, raw.files) if c is not None],
            err_tail=raw.err_tail,
            error=failure_summary([*raw.log_tail, *raw.err_tail]) if slurm_id in failed else None,
        )
    return AccountSnapshot(jobs=jobs, telemetry=telemetry)


def _chunk(file: AgentFile) -> FileChunk | None:
    try:
        data = decode_chunk_data(file.data)
    except (binascii.Error, ValueError):
        return None
    return FileChunk(path=file.path, offset=file.offset, size=file.size, data=data)
