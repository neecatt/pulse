from fastapi import APIRouter
from sqlalchemy import select

from pulse.api.deps import CurrentUser, SessionDep
from pulse.api.jobs import sort_time
from pulse.metrics.ingest import is_system_metric
from pulse.models import Account, Job
from pulse.schemas import MetricStats, RunOut
from pulse.services.teams import hide_username, visible_jobs

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(
    session: SessionDep, user: CurrentUser, array_id: str | None = None
) -> list[RunOut]:
    """Jobs with metric summaries and hyperparameters, for the runs table.

    ``array_id`` narrows it to one job array (a sweep)."""
    query = select(Job).where(visible_jobs(user.id))
    if array_id is not None:
        query = query.where(Job.array_id == array_id)
    jobs = sorted(await session.scalars(query), key=lambda j: -sort_time(j))
    # Teammates' runs: the owner's cluster login stays out of hyperparameter paths.
    theirs = select(Account.id, Account.username).where(
        Account.id.in_({j.account_id for j in jobs}), Account.user_id != user.id
    )
    logins = dict((await session.execute(theirs)).all())
    return [
        RunOut.model_validate(job).model_copy(
            update={
                "metric_stats": _metric_stats(job),
                **(
                    {"hparams": hide_username(job.hparams, logins[job.account_id])}
                    if job.account_id in logins
                    else {}
                ),
            }
        )
        for job in jobs
    ]


def _metric_stats(job: Job) -> dict[str, MetricStats]:
    return {
        name: MetricStats(last=s["last"], min=s["min"], max=s["max"])
        for name, s in (job.metric_summary or {}).items()
        if not is_system_metric(name)
    }
