"""Who may see an account: its owner, and the members of the owner's team when the
account is shared. Every read of jobs, runs and events goes through here."""

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.models import Account, Team, TeamMember


def visible_account_ids(user_id: int) -> Select[int]:
    """Accounts the user may read: their own, plus shared accounts of the owners of
    teams they belong to. Use it in queries as ``Job.account_id.in_(...)``."""
    owners = select(Team.owner_id).join(TeamMember).where(TeamMember.user_id == user_id)
    return select(Account.id).where(
        or_(Account.user_id == user_id, and_(Account.shared, Account.user_id.in_(owners)))
    )


async def can_view(session: AsyncSession, user_id: int, account_id: int) -> bool:
    found = await session.scalar(visible_account_ids(user_id).where(Account.id == account_id))
    return found is not None


async def team_members(session: AsyncSession, owner_id: int) -> list[TeamMember]:
    rows = await session.scalars(select(TeamMember).join(Team).where(Team.owner_id == owner_id))
    return list(rows)


async def audience(session: AsyncSession, account: Account) -> set[int]:
    """Users who see this account's jobs: the owner, plus the team if it's shared."""
    viewers = {account.user_id}
    if account.shared:
        viewers |= {m.user_id for m in await team_members(session, account.user_id)}
    return viewers


async def audiences(session: AsyncSession) -> dict[int, set[int]]:
    """Team members by owner, for every team at once (the poller's per-cycle view)."""
    rows = await session.execute(select(Team.owner_id, TeamMember.user_id).join(TeamMember))
    members: dict[int, set[int]] = {}
    for owner_id, user_id in rows.all():
        members.setdefault(owner_id, set()).add(user_id)
    return members
