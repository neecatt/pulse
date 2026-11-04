from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep, get_owned_account
from pulse.models import Account
from pulse.schemas import AccountCheck, AccountCreate, AccountOut, AccountUpdate
from pulse.slurm import AccountRef, SlurmError

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Number of distinct account colours defined in the frontend palette.
PALETTE_SIZE = 6


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
    account = Account(user_id=user.id, color=count % PALETTE_SIZE, **body.model_dump())
    session.add(account)
    await session.commit()
    services.poller.trigger()
    return AccountOut.model_validate(account)


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
    ref = AccountRef(username=account.username, host=account.host, port=account.port)
    try:
        await services.slurm.check(ref)
    except SlurmError as exc:
        return AccountCheck(ok=False, error=str(exc))
    return AccountCheck(ok=True)
