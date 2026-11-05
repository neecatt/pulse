"""Who may see an account: its owner, and the members of every team the owner
shared it with. Every read of jobs, runs and events goes through here."""

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.models import Account, AccountShare, TeamMember


def _my_teams(user_id: int) -> Select[int]:
    return select(TeamMember.team_id).where(TeamMember.user_id == user_id)


def visible_account_ids(user_id: int) -> Select[int]:
    """Accounts the user may read: their own, plus accounts shared with a team they're
    in. Use it in queries as ``Job.account_id.in_(...)``."""
    shared = select(AccountShare.account_id).where(AccountShare.team_id.in_(_my_teams(user_id)))
    return select(Account.id).where(or_(Account.user_id == user_id, Account.id.in_(shared)))


async def can_view(session: AsyncSession, user_id: int, account_id: int) -> bool:
    found = await session.scalar(visible_account_ids(user_id).where(Account.id == account_id))
    return found is not None


async def is_member(session: AsyncSession, user_id: int, team_id: int) -> bool:
    found = await session.scalar(
        select(TeamMember.id).where(TeamMember.user_id == user_id, TeamMember.team_id == team_id)
    )
    return found is not None


def _team_viewers(account_id: int) -> Select[int, bool]:
    return (
        select(TeamMember.user_id, TeamMember.alerts)
        .join(AccountShare, AccountShare.team_id == TeamMember.team_id)
        .where(AccountShare.account_id == account_id)
    )


async def audience(session: AsyncSession, account: Account) -> set[int]:
    """Users who see this account's jobs: the owner and every team it's shared with."""
    rows = await session.execute(_team_viewers(account.id))
    return {account.user_id} | {user_id for user_id, _ in rows.all()}


async def alert_recipients(session: AsyncSession, account: Account) -> set[int]:
    """Teammates who opted in to alerts in a team this account is shared with."""
    rows = await session.execute(_team_viewers(account.id))
    return {user_id for user_id, alerts in rows.all() if alerts} - {account.user_id}


async def audiences(session: AsyncSession) -> dict[int, set[int]]:
    """Teammates watching each shared account, for every account at once (the
    poller's per-cycle view). Owners aren't included; the caller adds them."""
    rows = await session.execute(
        select(AccountShare.account_id, TeamMember.user_id).join(
            TeamMember, TeamMember.team_id == AccountShare.team_id
        )
    )
    viewers: dict[int, set[int]] = {}
    for account_id, user_id in rows.all():
        viewers.setdefault(account_id, set()).add(user_id)
    return viewers
