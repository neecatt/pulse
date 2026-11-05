"""Demo guests: temporary accounts with simulated clusters, for a public site
(``PULSE_DEMO``). Each guest gets their own sandbox and is deleted after a day."""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.constants import DEMO_GUEST_TTL_SECONDS, DEMO_MAX_GUESTS
from pulse.models import Account, User

# The clusters a guest starts with: (login, host, cluster name). Hosts use the
# reserved .example domain; nothing ever connects to them.
DEMO_ACCOUNTS = (
    ("demo", "login.lumi.example", "LUMI"),
    ("demo", "login.leonardo.example", "Leonardo"),
)


async def create_guest(session: AsyncSession, now: datetime) -> User:
    """A new guest with simulated clusters. Makes room first if there are too many."""
    alive = await session.scalar(select(func.count()).where(User.is_guest)) or 0
    if alive >= DEMO_MAX_GUESTS:
        oldest = (
            select(User.id)
            .where(User.is_guest)
            .order_by(User.created_at)
            .limit(alive - DEMO_MAX_GUESTS + 1)
        )
        await session.execute(delete(User).where(User.id.in_(oldest)))
    user = User(username=f"guest-{secrets.token_hex(4)}", is_guest=True, created_at=now)
    session.add(user)
    await session.flush()
    for color, (login, host, cluster) in enumerate(DEMO_ACCOUNTS):
        session.add(
            Account(
                user_id=user.id,
                username=login,
                host=host,
                cluster=cluster,
                color=color,
                simulated=True,
                created_at=now,
            )
        )
    await session.flush()
    return user


async def remove_expired_guests(session: AsyncSession, now: datetime) -> None:
    """Delete guests older than a day, with everything they had (foreign keys cascade)."""
    cutoff = now - timedelta(seconds=DEMO_GUEST_TTL_SECONDS)
    await session.execute(delete(User).where(User.is_guest, User.created_at < cutoff))
