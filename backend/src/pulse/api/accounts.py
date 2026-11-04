import hashlib
import re
import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep, get_owned_account
from pulse.constants import ACCOUNT_PALETTE_SIZE
from pulse.models import Account
from pulse.schemas import AccountCheck, AccountCreate, AccountOut, AccountUpdate, AgentToken
from pulse.slurm import AccountRef, SlurmError

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Host labels that say nothing about which cluster it is.
_GENERIC_LABELS = {"login", "ssh", "gateway", "access", "frontend", "hpc", "cluster", "www"}


@router.get("")
async def list_accounts(session: SessionDep, user: CurrentUser) -> list[AccountOut]:
    accounts = await session.scalars(
        select(Account).where(Account.user_id == user.id).order_by(Account.id)
    )
    return [AccountOut.model_validate(a) for a in accounts]


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
    token = secrets.token_urlsafe(32)
    account.agent_token_hash = hash_token(token)
    await session.commit()
    return AgentToken(token=token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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
    ref = AccountRef(
        username=account.username,
        host=account.host,
        port=account.port,
        host_key=account.host_key,
    )
    try:
        host_key = await services.slurm.check(ref)
    except SlurmError as exc:
        account.last_error = str(exc)[:500]
        await session.commit()
        return AccountCheck(ok=False, error=str(exc))
    account.host_key = account.host_key or host_key
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
