from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.api.deps import CurrentUser, SessionDep
from pulse.domain import JobState
from pulse.models import Account, Job, JobMetric
from pulse.schemas import JobDetailOut, JobOut, MetricPoint

router = APIRouter(prefix="/jobs", tags=["jobs"])

TREND_POINTS = 40
SERIES_POINTS = 500
_STATE_ORDER = {JobState.RUNNING: 0, JobState.PENDING: 1}


@router.get("")
async def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    account_id: int | None = None,
    state: JobState | None = None,
) -> list[JobOut]:
    query = select(Job).join(Account).where(Account.user_id == user.id)
    if account_id is not None:
        query = query.where(Job.account_id == account_id)
    if state is not None:
        query = query.where(Job.state == state)
    jobs = list(await session.scalars(query))
    # Active jobs first, then most recently finished.
    jobs.sort(key=lambda j: (_STATE_ORDER.get(j.state, 2), -_sort_time(j)))

    trends = await _loss_trends(session, [j.id for j in jobs if j.state is JobState.RUNNING])
    return [
        JobOut.model_validate(j).model_copy(update={"loss_trend": trends.get(j.id, [])})
        for j in jobs
    ]


@router.get("/{job_id}")
async def get_job(job_id: int, session: SessionDep, user: CurrentUser) -> JobDetailOut:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    account = await session.get(Account, job.account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")

    rows = await session.execute(
        select(JobMetric.name, JobMetric.ts, JobMetric.value)
        .where(JobMetric.job_id == job.id)
        .order_by(JobMetric.ts.desc())
        .limit(SERIES_POINTS * 3)
    )
    series: dict[str, list[MetricPoint]] = defaultdict(list)
    for name, ts, value in reversed(rows.all()):
        series[name].append(MetricPoint(t=ts, v=value))
    detail = JobDetailOut.model_validate(job)
    return detail.model_copy(
        update={
            "series": {k: v[-SERIES_POINTS:] for k, v in series.items()},
            "loss_trend": [p.v for p in series.get("loss", [])][-TREND_POINTS:],
        }
    )


async def _loss_trends(session: AsyncSession, job_ids: list[int]) -> dict[int, list[float]]:
    if not job_ids:
        return {}
    rows = await session.execute(
        select(JobMetric.job_id, JobMetric.value)
        .where(JobMetric.job_id.in_(job_ids), JobMetric.name == "loss")
        .order_by(JobMetric.ts)
    )
    trends: dict[int, list[float]] = defaultdict(list)
    for job_id, value in rows.all():
        trends[job_id].append(value)
    return {k: v[-TREND_POINTS:] for k, v in trends.items()}


def _sort_time(job: Job) -> float:
    moment = job.end_time or job.start_time or job.submit_time
    return moment.timestamp() if moment else 0.0
