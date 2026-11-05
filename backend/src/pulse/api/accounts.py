import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep, get_owned_account
from pulse.auth.tokens import hash_token, new_token
from pulse.constants import ACCOUNT_PALETTE_SIZE
from pulse.models import Account, AccountShare, User
from pulse.schemas import AccountCheck, AccountCreate, AccountOut, AccountUpdate, AgentToken
from pulse.services.teams import is_member, visible_account_ids
from pulse.slurm import SlurmError

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Host labels that say nothing about which cluster it is.
_GENERIC_LABELS = {"login", "ssh", "gateway", "access", "frontend", "hpc", "cluster", "www"}


@router.get("")
async def list_accounts(session: SessionDep, user: CurrentUser) -> list[AccountOut]:
    """Your accounts, then the ones teammates share with you (read-only)."""
    rows = await session.execute(
        select(Account, User.username)
        .join(User, Account.user_id == User.id)
        .where(Account.id.in_(visible_account_ids(user.id)))
        .order_by(Account.user_id != user.id, User.username, Account.id)
    )
    shares = await session.execute(
        select(AccountShare.account_id, AccountShare.team_id)
        .join(Account, AccountShare.account_id == Account.id)
        .where(Account.user_id == user.id)
    )
    teams_by_account: dict[int, list[int]] = {}
    for account_id, team_id in shares.all():
        teams_by_account.setdefault(account_id, []).append(team_id)
    return [
        AccountOut.model_validate(account).model_copy(
            update=(
                {"shared_with": teams_by_account.get(account.id, [])}
                if account.user_id == user.id
                else {"owner": owner}  # which teams it's shared with stays private
            )
        )
        for account, owner in rows.all()
    ]


@router.put("/{account_id}/shares/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def share_account(
    account_id: int, team_id: int, session: SessionDep, user: CurrentUser
) -> None:
    """Let a team you're in see this account's jobs, read-only."""
    account = await get_owned_account(session, user, account_id)
    if not await is_member(session, user.id, team_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You're not in that team.")
    exists = await session.scalar(
        select(AccountShare.id).where(
            AccountShare.account_id == account.id, AccountShare.team_id == team_id
        )
    )
    if exists is None:
        session.add(AccountShare(account_id=account.id, team_id=team_id))
        await session.commit()


@router.delete("/{account_id}/shares/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_account(
    account_id: int, team_id: int, session: SessionDep, user: CurrentUser
) -> None:
    account = await get_owned_account(session, user, account_id)
    await session.execute(
        delete(AccountShare).where(
            AccountShare.account_id == account.id, AccountShare.team_id == team_id
        )
    )
    await session.commit()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AccountOut:
    duplicate = await session.scalar(
        select(Account.id).where(
            Account.user_id == user.id,
            Account.username == body.username,
            Account.host == body.host,
            Account.port == body.port,
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "account already linked")
    count = await session.scalar(select(func.count()).where(Account.user_id == user.id)) or 0
    fields = body.model_dump(exclude={"cluster"})
    cluster = body.cluster or cluster_name_from_host(body.host)
    account = Account(
        user_id=user.id, color=count % ACCOUNT_PALETTE_SIZE, cluster=cluster, **fields
    )
    session.add(account)
    await session.commit()
    if account.connection == "direct":
        services.poller.trigger()
    return AccountOut.model_validate(account)


@router.post("/{account_id}/agent-token")
async def issue_agent_token(account_id: int, session: SessionDep, user: CurrentUser) -> AgentToken:
    """Create (or replace) the token the login-node agent reports with.

    Only a hash is stored, so the token is shown once; issuing a new one
    disables the previous install.
    """
    account = await get_owned_account(session, user, account_id)
    if account.connection != "agent":
        raise HTTPException(status.HTTP_409_CONFLICT, "account doesn't use an agent")
    token = new_token()
    account.agent_token_hash = hash_token(token)
    await session.commit()
    return AgentToken(token=token)


@router.patch("/{account_id}")
async def update_account(
    account_id: int, body: AccountUpdate, session: SessionDep, user: CurrentUser
) -> AccountOut:
    account = await get_owned_account(session, user, account_id)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(account, field, value)
    await session.commit()
    return AccountOut.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, session: SessionDep, user: CurrentUser) -> None:
    account = await get_owned_account(session, user, account_id)
    await session.delete(account)
    await session.commit()


@router.post("/{account_id}/check")
async def check_account(
    account_id: int, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AccountCheck:
    account = await get_owned_account(session, user, account_id)
    if account.connection == "agent":
        if account.last_polled_at is None:
            return AccountCheck(
                ok=False, error="Waiting for the agent's first report from the login node."
            )
        return AccountCheck(ok=account.last_error is None, error=account.last_error)
    try:
        host_keys = await services.slurm.check(account.ref(public_only=not user.is_admin))
    except SlurmError as exc:
        account.last_error = str(exc)[:500]
        await session.commit()
        return AccountCheck(ok=False, error=str(exc))
    account.pin_host_keys(host_keys)
    account.last_error = None
    await session.commit()
    services.poller.trigger()
    return AccountCheck(ok=True)


def cluster_name_from_host(host: str) -> str:
    """Readable cluster name from a login hostname.

    ``login.leonardo.cineca.it`` -> ``Leonardo``, ``lumi.csc.fi`` -> ``LUMI``.
    """
    for label in host.split("."):
        stem = re.sub(r"[-_]?\d+$", "", label)
        if stem and stem not in _GENERIC_LABELS and not stem.isdigit():
            return stem.upper() if len(stem) <= 4 else stem.capitalize()
    return host
