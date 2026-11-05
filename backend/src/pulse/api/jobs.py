from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.api.deps import CurrentUser, SessionDep
from pulse.constants import CHART_POINTS, SERIES_POINTS, TREND_POINTS
from pulse.domain import JobState
from pulse.metrics.downsample import downsample
from pulse.metrics.ingest import system_metric_filter
from pulse.models import Account, Job, JobMetric, JobShare, MetricFile, User
from pulse.schemas import (
    JobDetailOut,
    JobMetrics,
    JobOut,
    JobUpdate,
    MetricPoint,
    StepPoint,
)
from pulse.services.teams import can_view_job, is_member, visible_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

_STATE_ORDER = {JobState.RUNNING: 0, JobState.PENDING: 1}


@router.get("")
async def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    account_id: int | None = None,
    state: JobState | None = None,
) -> list[JobOut]:
    query = select(Job).where(visible_jobs(user.id))
    if account_id is not None:
        query = query.where(Job.account_id == account_id)
    if state is not None:
        query = query.where(Job.state == state)
    jobs = list(await session.scalars(query))
    # Active jobs first, then most recently finished.
    jobs.sort(key=lambda j: (_STATE_ORDER.get(j.state, 2), -sort_time(j)))

    trends = await _loss_trends(session, [j for j in jobs if j.state is JobState.RUNNING])
    return [
        JobOut.model_validate(j).model_copy(update={"loss_trend": trends.get(j.id, [])})
        for j in jobs
    ]


@router.get("/{job_id}")
async def get_job(job_id: int, session: SessionDep, user: CurrentUser) -> JobDetailOut:
    job = await _get_visible_job(session, user, job_id)
    rows = await session.execute(
        select(JobMetric.name, JobMetric.ts, JobMetric.value)
        .where(JobMetric.job_id == job.id, system_metric_filter())
        .order_by(JobMetric.ts)
    )
    series: dict[str, list[MetricPoint]] = defaultdict(list)
    for name, ts, value in rows.all():
        series[name].append(MetricPoint(t=ts, v=value))
    trends = await _loss_trends(session, [job])
    detail = JobDetailOut.model_validate(job)
    account = await session.get(Account, job.account_id)
    shared_with = (
        list(await session.scalars(select(JobShare.team_id).where(JobShare.job_id == job.id)))
        if account is not None and account.user_id == user.id
        else []  # which teams a job is shared with is the owner's business
    )
    return detail.model_copy(
        update={
            "series": {k: downsample(v, SERIES_POINTS) for k, v in series.items()},
            "loss_trend": trends.get(job.id, []),
            "shared_with": shared_with,
        }
    )


@router.put("/{job_id}/shares/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def share_job(job_id: int, team_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Share one job with a team you're in, when its account doesn't share every job."""
    job = await _get_owned_job(session, user, job_id)
    if not await is_member(session, user.id, team_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You're not in that team.")
    exists = await session.scalar(
        select(JobShare.id).where(JobShare.job_id == job.id, JobShare.team_id == team_id)
    )
    if exists is None:
        session.add(JobShare(job_id=job.id, team_id=team_id))
        await session.commit()


@router.delete("/{job_id}/shares/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_job(job_id: int, team_id: int, session: SessionDep, user: CurrentUser) -> None:
    job = await _get_owned_job(session, user, job_id)
    await session.execute(
        delete(JobShare).where(JobShare.job_id == job.id, JobShare.team_id == team_id)
    )
    await session.commit()


@router.patch("/{job_id}")
async def update_job(
    job_id: int, body: JobUpdate, session: SessionDep, user: CurrentUser
) -> JobDetailOut:
    """Set a job's note and/or tags. Only the account's owner can; team members read."""
    job = await _get_owned_job(session, user, job_id)
    if body.note is not None:
        job.note = body.note.strip() or None
    if body.tags is not None:
        job.tags = list(dict.fromkeys(body.tags))  # dedupe, keep order
    await session.commit()
    return await get_job(job_id, session, user)


@router.get("/{job_id}/metrics")
async def get_job_metrics(
    job_id: int,
    session: SessionDep,
    user: CurrentUser,
    max_points: int = Query(default=CHART_POINTS, ge=10, le=5000),
) -> JobMetrics:
    """All training metrics of a job (system metrics excluded), downsampled per metric."""
    job = await _get_visible_job(session, user, job_id)
    rows = await session.execute(
        select(JobMetric.name, JobMetric.step, JobMetric.ts, JobMetric.value)
        .where(JobMetric.job_id == job.id, ~system_metric_filter())
        .order_by(JobMetric.name, JobMetric.step, JobMetric.ts)
    )
    metrics: dict[str, list[StepPoint]] = defaultdict(list)
    for name, step, ts, value in rows.all():
        metrics[name].append(StepPoint(s=step, t=ts, v=value))
    files = await session.scalars(select(MetricFile.path).where(MetricFile.job_id == job.id))
    return JobMetrics(
        metrics={name: downsample(points, max_points) for name, points in metrics.items()},
        primary=job.primary_metric,
        hparams=job.hparams,
        files=list(files),
    )


async def _get_visible_job(session: AsyncSession, user: User, job_id: int) -> Job:
    """A job the user may read: their own, or one on an account shared with their team."""
    job = await session.get(Job, job_id)
    if job is None or not await can_view_job(session, user.id, job.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


async def _get_owned_job(session: AsyncSession, user: User, job_id: int) -> Job:
    job = await session.get(Job, job_id)
    account = await session.get(Account, job.account_id) if job else None
    if job is None or account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


async def _loss_trends(session: AsyncSession, jobs: list[Job]) -> dict[int, list[float]]:
    """Recent values of each job's primary metric, for sparklines."""
    by_metric: dict[str, list[int]] = defaultdict(list)
    for job in jobs:
        by_metric[job.primary_metric or "loss"].append(job.id)
    if not by_metric:
        return {}
    conditions = [
        (JobMetric.name == name) & JobMetric.job_id.in_(ids) for name, ids in by_metric.items()
    ]
    rows = await session.execute(
        select(JobMetric.job_id, JobMetric.value)
        .where(or_(*conditions))
        .order_by(JobMetric.step, JobMetric.ts)
    )
    trends: dict[int, list[float]] = defaultdict(list)
    for job_id, value in rows.all():
        trends[job_id].append(value)
    return {k: v[-TREND_POINTS:] for k, v in trends.items()}


def sort_time(job: Job) -> float:
    moment = job.end_time or job.start_time or job.submit_time
    return moment.timestamp() if moment else 0.0
