"""Store parsed metric points and keep per-file read offsets."""

import base64
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.domain import JobState
from pulse.metrics.discovery import classify
from pulse.metrics.hparams import parse_config
from pulse.metrics.model import ParsedChunk, Point
from pulse.metrics.tabular import parse_csv, parse_jsonl
from pulse.metrics.tfevents import parse_tfevents
from pulse.models import Job, JobMetric, MetricFile
from pulse.slurm.base import FileChunk

SYSTEM_METRICS = ("gpu_util", "gpu_mem")
_PRIMARY_PREFERENCE = ("loss", "train/loss", "train_loss", "loss/train", "training_loss")


def parse_file_chunk(row: MetricFile, chunk: FileChunk) -> ParsedChunk:
    """Parse new bytes from a file, advancing ``row``'s offset and CSV header."""
    if row.kind == "config":
        parsed = ParsedChunk(hparams=parse_config(row.path, chunk.data))
        row.offset = chunk.size  # re-read only when the file changes size
        return parsed
    if chunk.offset == 0 and row.offset > chunk.size:
        row.offset, row.csv_header = 0, None  # file was rewritten
    if chunk.offset != row.offset:
        return ParsedChunk()  # stale read; the next poll uses the right cursor
    if row.kind == "tfevents":
        parsed = parse_tfevents(chunk.data)
    elif row.kind == "jsonl":
        parsed = parse_jsonl(chunk.data)
    else:
        parsed, row.csv_header = parse_csv(chunk.data, row.csv_header)
    row.offset += parsed.consumed
    return parsed


def ingest_files(job: Job, chunks: Iterable[FileChunk]) -> list[Point]:
    """Apply file chunks to ``job``: returns new points, updates hparams."""
    rows = {f.path: f for f in job.metric_files}
    points: list[Point] = []
    for chunk in chunks:
        row = rows.get(chunk.path)
        if row is None:
            kind = classify(chunk.path)
            if kind is None:
                continue
            row = MetricFile(path=chunk.path, kind=kind, offset=0)
            job.metric_files.append(row)
            rows[chunk.path] = row
        parsed = parse_file_chunk(row, chunk)
        points.extend(parsed.points)
        if parsed.hparams:
            job.hparams = {**job.hparams, **parsed.hparams}
    return points


async def store_points(session: AsyncSession, job: Job, points: list[Point], now: datetime) -> None:
    """Insert points, ignoring steps already stored, and refresh the job's
    primary metric. Requires ``job.id`` (flush first for new jobs)."""
    if not points:
        return
    rows = [
        {
            "job_id": job.id,
            "name": p.name[:128],
            "step": p.step,
            "ts": p.wall_time or now,
            "value": p.value,
        }
        for p in points
    ]
    statement = sqlite_insert(JobMetric).on_conflict_do_nothing()
    for start in range(0, len(rows), 500):  # stay under SQLite's variable limit
        await session.execute(statement, rows[start : start + 500])

    names = {p.name for p in points if p.name not in SYSTEM_METRICS}
    job.primary_metric = job.primary_metric or choose_primary(names)
    primary = [p for p in points if p.name == job.primary_metric]
    if primary:
        job.last_loss = max(primary, key=lambda p: (p.step or 0, p.wall_time or now)).value


def choose_primary(names: Iterable[str]) -> str | None:
    """The metric that best represents training progress: a loss, if any."""
    candidates = set(names)
    for preferred in _PRIMARY_PREFERENCE:
        if preferred in candidates:
            return preferred
    losses = sorted((n for n in candidates if "loss" in n.lower()), key=lambda n: (len(n), n))
    return losses[0] if losses else None


async def load_cursors(session: AsyncSession, account_id: int) -> dict[str, dict[str, int]]:
    """Read offsets for files of running jobs, keyed by Slurm job id."""
    rows = await session.execute(
        select(Job.slurm_id, MetricFile.path, MetricFile.offset)
        .join(MetricFile, MetricFile.job_id == Job.id)
        .where(Job.account_id == account_id, Job.state == JobState.RUNNING)
    )
    cursors: dict[str, dict[str, int]] = {}
    for slurm_id, path, offset in rows.all():
        cursors.setdefault(slurm_id, {})[path] = offset
    return cursors


def decode_chunk_data(data: str) -> bytes:
    return base64.b64decode(data, validate=False)
