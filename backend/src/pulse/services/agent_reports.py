"""Turn raw output sent by the login-node agent into an AccountSnapshot."""

import binascii
from datetime import UTC, datetime

from pulse.metrics.ingest import decode_chunk_data
from pulse.schemas import AgentFile, AgentReport
from pulse.slurm.base import AccountSnapshot, FileChunk, JobTelemetry, SlurmError
from pulse.slurm.parsing import (
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
        )
    return AccountSnapshot(jobs=jobs, telemetry=telemetry)


def _chunk(file: AgentFile) -> FileChunk | None:
    try:
        data = decode_chunk_data(file.data)
    except (binascii.Error, ValueError):
        return None
    return FileChunk(path=file.path, offset=file.offset, size=file.size, data=data)
