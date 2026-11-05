"""Who may see what. A job is visible to its owner, to every team its account is
shared with ("all jobs"), and to every team the job itself is shared with. Every
read of jobs, runs, events and accounts goes through here."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.models import Account, AccountShare, Event, Job, JobShare, TeamMember


def _my_teams(user_id: int) -> Select[int]:
    return select(TeamMember.team_id).where(TeamMember.user_id == user_id)


def _whole_accounts(user_id: int) -> Select[int]:
    """Accounts whose every job the user may see: their own and fully shared ones."""
    shared = select(AccountShare.account_id).where(AccountShare.team_id.in_(_my_teams(user_id)))
    return select(Account.id).where(or_(Account.user_id == user_id, Account.id.in_(shared)))


def _shared_jobs(user_id: int) -> Select[int]:
    return select(JobShare.job_id).where(JobShare.team_id.in_(_my_teams(user_id)))


def visible_jobs(user_id: int) -> ColumnElement[bool]:
    """Filter for jobs the user may read: ``select(Job).where(visible_jobs(id))``."""
    return or_(Job.account_id.in_(_whole_accounts(user_id)), Job.id.in_(_shared_jobs(user_id)))


def visible_events(user_id: int) -> ColumnElement[bool]:
    """Events of visible accounts, or of individually shared jobs only."""
    return or_(
        Event.account_id.in_(_whole_accounts(user_id)), Event.job_id.in_(_shared_jobs(user_id))
    )


def visible_account_ids(user_id: int) -> Select[int]:
    """Accounts the user sees at least one job of (for labels and the account list)."""
    via_jobs = select(Job.account_id).where(Job.id.in_(_shared_jobs(user_id)))
    return select(Account.id).where(
        or_(Account.id.in_(_whole_accounts(user_id)), Account.id.in_(via_jobs))
    )


async def can_view_job(session: AsyncSession, user_id: int, job_id: int) -> bool:
    found = await session.scalar(select(Job.id).where(Job.id == job_id, visible_jobs(user_id)))
    return found is not None


async def is_member(session: AsyncSession, user_id: int, team_id: int) -> bool:
    found = await session.scalar(
        select(TeamMember.id).where(TeamMember.user_id == user_id, TeamMember.team_id == team_id)
    )
    return found is not None


async def _account_viewers(session: AsyncSession, account_id: int) -> list[tuple[int, bool]]:
    rows = await session.execute(
        select(TeamMember.user_id, TeamMember.alerts)
        .join(AccountShare, AccountShare.team_id == TeamMember.team_id)
        .where(AccountShare.account_id == account_id)
    )
    return [(user_id, alerts) for user_id, alerts in rows.all()]


async def _job_viewers(session: AsyncSession, account_id: int) -> list[tuple[int, int, bool]]:
    """(job id, user id, alerts) for this account's individually shared jobs."""
    rows = await session.execute(
        select(JobShare.job_id, TeamMember.user_id, TeamMember.alerts)
        .join(TeamMember, TeamMember.team_id == JobShare.team_id)
        .join(Job, Job.id == JobShare.job_id)
        .where(Job.account_id == account_id)
    )
    return [(job_id, user_id, alerts) for job_id, user_id, alerts in rows.all()]


async def audience(session: AsyncSession, account: Account) -> set[int]:
    """Users who see any of this account's jobs, its owner included."""
    whole = {user_id for user_id, _ in await _account_viewers(session, account.id)}
    jobs = {user_id for _, user_id, _ in await _job_viewers(session, account.id)}
    return {account.user_id} | whole | jobs


async def partial_viewers(session: AsyncSession, account: Account) -> dict[int, set[int]]:
    """Teammates who see only some of this account's jobs, with those jobs' ids."""
    whole = {user_id for user_id, _ in await _account_viewers(session, account.id)}
    partial: dict[int, set[int]] = {}
    for job_id, user_id, _ in await _job_viewers(session, account.id):
        if user_id not in whole and user_id != account.user_id:
            partial.setdefault(user_id, set()).add(job_id)
    return partial


async def alert_recipients(
    session: AsyncSession, account: Account, events: Sequence[Event]
) -> dict[int, list[Event]]:
    """Events each teammate should be alerted about: all of a fully shared account's,
    or only those of the jobs shared with them. Only teammates who opted in."""
    recipients: dict[int, list[Event]] = {}
    whole = {u for u, alerts in await _account_viewers(session, account.id) if alerts}
    by_job: dict[int, set[int]] = {}
    for job_id, user_id, alerts in await _job_viewers(session, account.id):
        if alerts:
            by_job.setdefault(job_id, set()).add(user_id)
    for event in events:
        users = whole | (by_job.get(event.job_id, set()) if event.job_id else set())
        for user_id in users - {account.user_id}:
            recipients.setdefault(user_id, []).append(event)
    return recipients


async def audiences(session: AsyncSession) -> dict[int, set[int]]:
    """Teammates watching each account (whole or single jobs), for every account at
    once: the poller's per-cycle view. Owners aren't included; the caller adds them."""
    whole = await session.execute(
        select(AccountShare.account_id, TeamMember.user_id).join(
            TeamMember, TeamMember.team_id == AccountShare.team_id
        )
    )
    jobs = await session.execute(
        select(Job.account_id, TeamMember.user_id)
        .join(JobShare, JobShare.job_id == Job.id)
        .join(TeamMember, TeamMember.team_id == JobShare.team_id)
    )
    viewers: dict[int, set[int]] = {}
    for account_id, user_id in [*whole.all(), *jobs.all()]:
        viewers.setdefault(account_id, set()).add(user_id)
    return viewers
