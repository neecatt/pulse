from fastapi import APIRouter
from sqlalchemy import select

from pulse.api.deps import CurrentUser, SessionDep
from pulse.api.jobs import sort_time
from pulse.metrics.ingest import is_system_metric
from pulse.models import Account, Job
from pulse.schemas import MetricStats, RunOut

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(
    session: SessionDep, user: CurrentUser, array_id: str | None = None
) -> list[RunOut]:
    """Jobs with metric summaries and hyperparameters, for the runs table.

    ``array_id`` narrows it to one job array (a sweep)."""
    query = select(Job).join(Account).where(Account.user_id == user.id)
    if array_id is not None:
        query = query.where(Job.array_id == array_id)
    jobs = sorted(await session.scalars(query), key=lambda j: -sort_time(j))
    return [
        RunOut.model_validate(job).model_copy(update={"metric_stats": _metric_stats(job)})
        for job in jobs
    ]


def _metric_stats(job: Job) -> dict[str, MetricStats]:
    return {
        name: MetricStats(last=s["last"], min=s["min"], max=s["max"])
        for name, s in (job.metric_summary or {}).items()
        if not is_system_metric(name)
    }
