from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.models import Account, User
from pulse.services.container import Services


def get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


ServicesDep = Annotated[Services, Depends(get_services)]


async def get_session(services: ServicesDep) -> AsyncIterator[AsyncSession]:
    async with services.sessions() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(session: SessionDep, services: ServicesDep) -> User:
    # Single-user stub: every request acts as the default user. Replace with real
    # authentication (OIDC / passkeys); all queries are already scoped by user.
    user = await _load_current_user(session, services)
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "default user not initialised")
    return user


async def get_current_user_id(services: ServicesDep) -> int:
    """Current user id without holding a DB session, for long-lived responses."""
    async with services.sessions() as session:
        user = await _load_current_user(session, services)
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "default user not initialised")
    return user.id


async def _load_current_user(session: AsyncSession, services: Services) -> User | None:
    email = services.settings.default_user_email
    return await session.scalar(select(User).where(User.email == email))


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]


async def get_owned_account(session: AsyncSession, user: User, account_id: int) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return account
