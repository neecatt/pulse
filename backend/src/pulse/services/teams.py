"""Who may see what. A job is visible to its owner, to every team its account is
shared with, to every team its owner shares all their jobs with, and to every
team the job itself is shared with. Every read of jobs, runs, events and
accounts goes through here."""

import re
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pulse.models import Account, AccountShare, Event, Job, JobShare, TeamMember
from pulse.services.broadcaster import Broadcaster


def _my_teams(user_id: int) -> Select[int]:
    return select(TeamMember.team_id).where(TeamMember.user_id == user_id)


def _whole_accounts(user_id: int) -> Select[int]:
    """Accounts whose every job the user may see: their own, those shared with
    their teams, and all accounts of teammates who share everything."""
    shared = select(AccountShare.account_id).where(AccountShare.team_id.in_(_my_teams(user_id)))
    sharing_all = select(TeamMember.user_id).where(
        TeamMember.team_id.in_(_my_teams(user_id)), TeamMember.share_all
    )
    return select(Account.id).where(
        or_(
            Account.user_id == user_id,
            Account.id.in_(shared),
            Account.user_id.in_(sharing_all),
        )
    )


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


async def team_member_ids(session: AsyncSession, team_id: int) -> set[int]:
    rows = await session.scalars(select(TeamMember.user_id).where(TeamMember.team_id == team_id))
    return set(rows)


def announce_access_change(broadcaster: Broadcaster, user_ids: Iterable[int]) -> None:
    """Tell these users' open apps that what they may see changed, so they refetch
    now rather than at the next poll."""
    for user_id in user_ids:
        broadcaster.publish(user_id, {"type": "access"})


async def _account_viewers(
    session: AsyncSession, account_id: int | None = None
) -> list[tuple[int, int, bool]]:
    """(account id, user id, alerts) for everyone who sees whole accounts through a
    team: shared accounts, and accounts of members who share everything. Owners
    are included, as members of their own teams. All accounts when ``account_id``
    is None (the poller's per-cycle view)."""
    shared = select(AccountShare.account_id, TeamMember.user_id, TeamMember.alerts).join(
        TeamMember, TeamMember.team_id == AccountShare.team_id
    )
    sharer, viewer = aliased(TeamMember), aliased(TeamMember)
    sharing_all = (
        select(Account.id, viewer.user_id, viewer.alerts)
        .join(sharer, (sharer.user_id == Account.user_id) & sharer.share_all)
        .join(viewer, viewer.team_id == sharer.team_id)
    )
    if account_id is not None:
        shared = shared.where(AccountShare.account_id == account_id)
        sharing_all = sharing_all.where(Account.id == account_id)
    rows = [*(await session.execute(shared)).all(), *(await session.execute(sharing_all)).all()]
    return [(a, u, alerts) for a, u, alerts in rows]


async def _job_viewers(
    session: AsyncSession, account_id: int | None = None
) -> list[tuple[int, int, int, bool]]:
    """(account id, job id, user id, alerts) for individually shared jobs."""
    query = (
        select(Job.account_id, JobShare.job_id, TeamMember.user_id, TeamMember.alerts)
        .join(TeamMember, TeamMember.team_id == JobShare.team_id)
        .join(Job, Job.id == JobShare.job_id)
    )
    if account_id is not None:
        query = query.where(Job.account_id == account_id)
    rows = (await session.execute(query)).all()
    return [(a, j, u, alerts) for a, j, u, alerts in rows]


async def audience(session: AsyncSession, account: Account) -> set[int]:
    """Users who see any of this account's jobs, its owner included."""
    whole = {user_id for _, user_id, _ in await _account_viewers(session, account.id)}
    jobs = {user_id for _, _, user_id, _ in await _job_viewers(session, account.id)}
    return {account.user_id} | whole | jobs


async def partial_viewers(session: AsyncSession, account: Account) -> dict[int, set[int]]:
    """Teammates who see only some of this account's jobs, with those jobs' ids."""
    whole = {user_id for _, user_id, _ in await _account_viewers(session, account.id)}
    partial: dict[int, set[int]] = {}
    for _, job_id, user_id, _ in await _job_viewers(session, account.id):
        if user_id not in whole and user_id != account.user_id:
            partial.setdefault(user_id, set()).add(job_id)
    return partial


async def alert_recipients(
    session: AsyncSession, account: Account, events: Sequence[Event]
) -> dict[int, list[Event]]:
    """Events each teammate should be alerted about: all of a fully shared account's,
    or only those of the jobs shared with them. Only teammates who opted in."""
    recipients: dict[int, list[Event]] = {}
    whole = {u for _, u, alerts in await _account_viewers(session, account.id) if alerts}
    by_job: dict[int, set[int]] = {}
    for _, job_id, user_id, alerts in await _job_viewers(session, account.id):
        if alerts:
            by_job.setdefault(job_id, set()).add(user_id)
    for event in events:
        users = whole | (by_job.get(event.job_id, set()) if event.job_id else set())
        for user_id in users - {account.user_id}:
            recipients.setdefault(user_id, []).append(event)
    return recipients


async def audiences(session: AsyncSession) -> dict[int, set[int]]:
    """Teammates watching each account (whole or single jobs), for every account at
    once: the poller's per-cycle view. The caller adds owners."""
    viewers: dict[int, set[int]] = {}
    for account_id, user_id, _ in await _account_viewers(session):
        viewers.setdefault(account_id, set()).add(user_id)
    for account_id, _, user_id, _ in await _job_viewers(session):
        viewers.setdefault(account_id, set()).add(user_id)
    return viewers


def hide_username(value: Any, username: str) -> Any:
    """Replace the owner's cluster username in path segments (``/home/jdoe/run``
    becomes ``/home/…/run``) in a string, or in the strings of a list or dict."""
    if isinstance(value, str):
        return re.sub(rf"(?<=/){re.escape(username)}(?![\w.-])", "…", value)
    if isinstance(value, list):
        return [hide_username(v, username) for v in value]
    if isinstance(value, dict):
        return {k: hide_username(v, username) for k, v in value.items()}
    return value
