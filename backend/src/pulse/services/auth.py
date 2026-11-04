"""Accounts, sign-in sessions and the environment-managed admin."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pulse.auth.passwords import hash_password, verify_password
from pulse.auth.tokens import hash_token, new_token
from pulse.config import Settings
from pulse.constants import SESSION_RENEW_SECONDS
from pulse.models import LoginSession, User, utcnow

logger = logging.getLogger(__name__)

# Checked against when a username doesn't exist, so a failed login takes the
# same time whether or not the account is real.
_DUMMY_HASH = hash_password("pulse-timing-equaliser")


async def sync_admin_from_env(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Make PULSE_ADMIN_USERNAME/PASSWORD the admin's credentials.

    Runs at startup. The environment is the source of truth: a changed password
    replaces the stored one and signs the admin out everywhere. Without the
    variables, any account previously managed this way can change its own
    password in the app again.
    """
    async with sessions() as session:
        if not (settings.admin_username and settings.admin_password):
            await session.execute(update(User).values(password_from_env=False))
            await session.commit()
            if await user_count(session) == 0:
                logger.warning("No users yet: open Pulse in a browser to create the admin account.")
            return

        password = settings.admin_password.get_secret_value()
        user = await session.scalar(select(User).where(User.username == settings.admin_username))
        if user is None:
            user = User(username=settings.admin_username)
            session.add(user)
            logger.info("Created admin account %r from the environment.", settings.admin_username)
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            if user.id is not None:
                await revoke_sessions(session, user.id)
        user.is_admin = True
        user.password_from_env = True
        await session.commit()


async def user_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None:
        verify_password(password, _DUMMY_HASH)  # same work either way: no username probing
        return None
    return user if verify_password(password, user.password_hash) else None


async def start_session(
    session: AsyncSession, user: User, settings: Settings, user_agent: str | None
) -> str:
    """Create a sign-in session and return its token (for the cookie)."""
    token = new_token()
    now = utcnow()
    session.add(
        LoginSession(
            user_id=user.id,
            token_hash=hash_token(token),
            user_agent=user_agent[:255] if user_agent else None,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.session_days),
        )
    )
    await session.commit()
    return token


async def resolve_session(
    session: AsyncSession, token: str, settings: Settings, now: datetime | None = None
) -> tuple[User, LoginSession] | None:
    """The user behind a session token, renewing the session as it's used."""
    now = now or utcnow()
    row = await session.scalar(
        select(LoginSession).where(LoginSession.token_hash == hash_token(token))
    )
    if row is None or row.expires_at <= now:
        return None
    if (now - row.last_seen_at).total_seconds() >= SESSION_RENEW_SECONDS:
        row.last_seen_at = now
        row.expires_at = now + timedelta(days=settings.session_days)
        await session.commit()
    user = await session.get(User, row.user_id)
    return (user, row) if user is not None else None


async def revoke_sessions(session: AsyncSession, user_id: int, *, keep: int | None = None) -> None:
    query = delete(LoginSession).where(LoginSession.user_id == user_id)
    if keep is not None:
        query = query.where(LoginSession.id != keep)
    await session.execute(query)
