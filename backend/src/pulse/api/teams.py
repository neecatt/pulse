"""Teams: the owner invites people by link and manages membership; every member,
the owner included, chooses which of their own accounts to share with the team.

Members see shared accounts' jobs, metrics and activity read-only; what they may
read is decided in ``services/teams.py``.
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pulse.api.auth import client_address, issue_session_cookie
from pulse.api.deps import CurrentUser, ServicesDep, SessionDep
from pulse.auth.passwords import hash_password
from pulse.auth.tokens import hash_token, new_token
from pulse.constants import TEAM_INVITE_TTL_SECONDS, TEAM_MAX_MEMBERS, TEAM_MAX_PENDING_INVITES
from pulse.models import (
    Account,
    AccountShare,
    Job,
    JobShare,
    Team,
    TeamInvite,
    TeamMember,
    User,
    utcnow,
)
from pulse.schemas import (
    Credentials,
    InviteInfo,
    Me,
    MembershipUpdate,
    NewTeamInvite,
    OwnedTeam,
    TeamCreate,
    TeamInviteOut,
    TeamMemberOut,
    TeamMembership,
    TeamOverview,
)
from pulse.services.teams import announce_access_change, team_member_ids

router = APIRouter(prefix="/teams", tags=["teams"])

_INVALID_INVITE = "This invite link is invalid or has expired. Ask for a new one."


@router.get("")
async def overview(session: SessionDep, user: CurrentUser) -> TeamOverview:
    """The team you own (if any) and the teams you're a member of."""
    return await _overview(session, user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(body: TeamCreate, session: SessionDep, user: CurrentUser) -> TeamOverview:
    _refuse_guests(user)
    if await _owned_team(session, user.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a team.")
    team = Team(owner_id=user.id, name=body.name)
    session.add(team)
    await session.flush()
    session.add(TeamMember(team_id=team.id, user_id=user.id))  # the owner is a member too
    await session.commit()
    return await _overview(session, user.id)


@router.patch("/mine")
async def rename_team(body: TeamCreate, session: SessionDep, user: CurrentUser) -> TeamOverview:
    team = await _require_owned_team(session, user.id)
    team.name = body.name
    await session.commit()
    return await _overview(session, user.id)


@router.delete("/mine", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(session: SessionDep, user: CurrentUser, services: ServicesDep) -> None:
    """Delete your team: everything shared with it stops being shared, at once."""
    team = await _require_owned_team(session, user.id)
    members = await team_member_ids(session, team.id)
    await session.delete(team)  # memberships, shares and invites go with it
    await session.commit()
    announce_access_change(services.broadcaster, members)


@router.delete("/mine/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: int, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> None:
    team = await _require_owned_team(session, user.id)
    if user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You own this team; delete it instead.")
    members = await team_member_ids(session, team.id)
    await _remove_from_team(session, team.id, user_id)
    await session.commit()
    announce_access_change(services.broadcaster, members)


@router.post("/mine/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(session: SessionDep, user: CurrentUser) -> NewTeamInvite:
    """A single-use link that lets one person join. Only its hash is kept."""
    _refuse_guests(user)  # an invite creates a real account, even with sign-ups off
    team = await _require_owned_team(session, user.id)
    now = utcnow()
    await session.execute(delete(TeamInvite).where(TeamInvite.expires_at <= now))
    pending = await session.scalar(
        select(func.count()).select_from(TeamInvite).where(TeamInvite.team_id == team.id)
    )
    if (pending or 0) >= TEAM_MAX_PENDING_INVITES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many unused invites. Revoke some first.")
    token = new_token()
    invite = TeamInvite(
        team_id=team.id,
        token_hash=hash_token(token),
        expires_at=now + timedelta(seconds=TEAM_INVITE_TTL_SECONDS),
    )
    session.add(invite)
    await session.commit()
    return NewTeamInvite(
        id=invite.id, created_at=invite.created_at, expires_at=invite.expires_at, token=token
    )


@router.delete("/mine/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: int, session: SessionDep, user: CurrentUser) -> None:
    team = await _require_owned_team(session, user.id)
    await session.execute(
        delete(TeamInvite).where(TeamInvite.id == invite_id, TeamInvite.team_id == team.id)
    )
    await session.commit()


@router.patch("/{team_id}/membership")
async def update_membership(
    team_id: int,
    body: MembershipUpdate,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> TeamOverview:
    """Your choices in a team: alerts for teammates' shared jobs, and sharing all
    of your own jobs with it."""
    member = await _membership(session, team_id, user.id)
    if body.alerts is not None:
        member.alerts = body.alerts
    sharing_changed = body.share_all is not None and body.share_all != member.share_all
    if body.share_all is not None:
        member.share_all = body.share_all
    await session.commit()
    if sharing_changed:
        announce_access_change(services.broadcaster, await team_member_ids(session, team_id))
    return await _overview(session, user.id)


@router.delete("/{team_id}/membership", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    team_id: int, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> None:
    """Leave a team: you stop seeing its shares, and yours are withdrawn from it."""
    member = await _membership(session, team_id, user.id)
    if await session.scalar(select(Team.id).where(Team.id == team_id, Team.owner_id == user.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You own this team; delete it instead.")
    members = await team_member_ids(session, team_id)
    await _remove_from_team(session, member.team_id, user.id)
    await session.commit()
    announce_access_change(services.broadcaster, members)


async def _remove_from_team(session: AsyncSession, team_id: int, user_id: int) -> None:
    """End a membership and withdraw that person's shares from the team."""
    await session.execute(
        delete(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    their_accounts = select(Account.id).where(Account.user_id == user_id)
    their_jobs = select(Job.id).where(Job.account_id.in_(their_accounts))
    await session.execute(
        delete(AccountShare).where(
            AccountShare.team_id == team_id, AccountShare.account_id.in_(their_accounts)
        )
    )
    await session.execute(
        delete(JobShare).where(JobShare.team_id == team_id, JobShare.job_id.in_(their_jobs))
    )


# Invite links. Looking one up needs no sign-in: the token itself is the secret.


@router.get("/invites/{token}")
async def invite_info(token: str, session: SessionDep) -> InviteInfo:
    team = (await _valid_invite(session, token)).team
    return InviteInfo(team=team.name, owner=team.owner.username)


@router.post("/invites/{token}/accept")
async def accept_invite(token: str, session: SessionDep, user: CurrentUser) -> TeamOverview:
    """Join with the account you're signed in with."""
    invite = await _valid_invite(session, token)
    await _join(session, invite, user.id)
    await session.commit()
    return await _overview(session, user.id)


@router.post("/invites/{token}/signup", status_code=status.HTTP_201_CREATED)
async def signup_with_invite(
    token: str,
    body: Credentials,
    request: Request,
    response: Response,
    session: SessionDep,
    services: ServicesDep,
) -> Me:
    """Create an account and join in one step. Works even when sign-ups are off:
    the invite is the permission."""
    address = f"ip:{client_address(request)}"
    if services.signup_limiter.blocked(address):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many new accounts from your network. Try again later.",
        )
    invite = await _valid_invite(session, token)
    services.signup_limiter.record_failure(address)  # every attempt counts
    if await session.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That username is taken. Sign in instead, then open the link."
        )
    user = User(username=body.username, password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    await _join(session, invite, user.id)
    await services.site.signup(session, client_address(request))
    await issue_session_cookie(user, request, response, session, services.settings)
    return Me.model_validate(user)


async def _join(session: AsyncSession, invite: TeamInvite, user_id: int) -> None:
    """Add the user to the invite's team and use up the invite."""
    team = invite.team
    if team.owner_id == user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This is your own team.")
    already = await session.scalar(
        select(TeamMember.id).where(TeamMember.team_id == team.id, TeamMember.user_id == user_id)
    )
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You're already in {team.name}.")
    members = await session.scalar(
        select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id)
    )
    if (members or 0) >= TEAM_MAX_MEMBERS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{team.name} is full.")
    # Use the invite up first: of two joins racing on one link, only one wins.
    used = await session.execute(delete(TeamInvite).where(TeamInvite.id == invite.id))
    if used.rowcount != 1:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_404_NOT_FOUND, _INVALID_INVITE)
    session.add(TeamMember(team_id=team.id, user_id=user_id))


async def _valid_invite(session: AsyncSession, token: str) -> TeamInvite:
    invite = await session.scalar(
        select(TeamInvite)
        .where(TeamInvite.token_hash == hash_token(token))
        .options(selectinload(TeamInvite.team).selectinload(Team.owner))
    )
    if invite is None or invite.expires_at <= utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, _INVALID_INVITE)
    return invite


def _refuse_guests(user: User) -> None:
    if user.is_guest:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Teams need a real account. Create one to invite people."
        )


async def _owned_team(session: AsyncSession, user_id: int) -> Team | None:
    return await session.scalar(select(Team).where(Team.owner_id == user_id))


async def _require_owned_team(session: AsyncSession, user_id: int) -> Team:
    team = await _owned_team(session, user_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You don't have a team yet.")
    return team


async def _membership(session: AsyncSession, team_id: int, user_id: int) -> TeamMember:
    member = await session.scalar(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You're not in that team.")
    return member


async def _overview(session: AsyncSession, user_id: int) -> TeamOverview:
    owned = None
    team = await _owned_team(session, user_id)
    if team is not None:
        members = await session.execute(
            select(TeamMember, User.username)
            .join(User, TeamMember.user_id == User.id)
            .where(TeamMember.team_id == team.id)
            .order_by(TeamMember.joined_at)
        )
        member_rows = members.all()
        own = next((m for m, _ in member_rows if m.user_id == user_id), None)
        invites = await session.scalars(
            select(TeamInvite)
            .where(TeamInvite.team_id == team.id, TeamInvite.expires_at > utcnow())
            .order_by(TeamInvite.created_at)
        )
        owned = OwnedTeam(
            id=team.id,
            name=team.name,
            members=[
                TeamMemberOut(user_id=m.user_id, username=name, joined_at=m.joined_at)
                for m, name in member_rows
                if m.user_id != user_id
            ],
            invites=[TeamInviteOut.model_validate(i) for i in invites],
            alerts=own.alerts if own else False,
            share_all=own.share_all if own else False,
        )
    rows = await session.execute(
        select(TeamMember, Team.name, User.username)
        .join(Team, TeamMember.team_id == Team.id)
        .join(User, Team.owner_id == User.id)
        .where(TeamMember.user_id == user_id, Team.owner_id != user_id)
        .order_by(Team.name)
    )
    memberships = [
        TeamMembership(
            team_id=m.team_id,
            name=name,
            owner=owner,
            alerts=m.alerts,
            share_all=m.share_all,
            joined_at=m.joined_at,
        )
        for m, name, owner in rows.all()
    ]
    return TeamOverview(owned=owned, memberships=memberships)
