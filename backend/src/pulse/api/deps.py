from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.constants import SESSION_COOKIE
from pulse.models import Account, User
from pulse.services.auth import resolve_session
from pulse.services.container import Services


def get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


ServicesDep = Annotated[Services, Depends(get_services)]


async def get_session(services: ServicesDep) -> AsyncIterator[AsyncSession]:
    async with services.sessions() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _authenticated(request: Request, session: AsyncSession, services: Services) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    resolved = await resolve_session(session, token, services.settings) if token else None
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    user, login = resolved
    request.state.login_session_id = login.id
    return user


async def get_current_user(request: Request, session: SessionDep, services: ServicesDep) -> User:
    """The signed-in user, from the session cookie; 401 otherwise."""
    return await _authenticated(request, session, services)


async def get_current_user_id(request: Request, services: ServicesDep) -> int:
    """Signed-in user id without holding a DB session, for long-lived responses."""
    async with services.sessions() as session:
        return (await _authenticated(request, session, services)).id


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]


async def get_owned_account(session: AsyncSession, user: User, account_id: int) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return account
