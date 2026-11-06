"""Site stats for admins: daily totals of landing views, visitors, demos and
sign-ups. Nothing identifying is stored. Distinct visitors are told apart by a
hash of their address with a salt that changes every day and lives only in
memory, so they can't be followed from one day to the next."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.constants import ACTIVE_USER_DAYS, SITE_STATS_DAYS, SITE_STATS_MAX_VISITORS_PER_DAY
from pulse.domain import Clock
from pulse.models import DailyCount, LoginSession, User
from pulse.schemas import DayStats, SiteStats


class SiteCounter:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._day = ""
        self._salt = b""
        self._visitors: set[bytes] = set()
        self._demoed: set[bytes] = set()  # addresses that started a demo today

    async def visit(self, session: AsyncSession, address: str) -> None:
        """A signed-out visitor opened the landing or sign-in page."""
        key = self._key(address)
        await _bump(session, self._day, "views")
        if key not in self._visitors and len(self._visitors) < SITE_STATS_MAX_VISITORS_PER_DAY:
            self._visitors.add(key)
            await _bump(session, self._day, "visitors")

    async def demo(self, session: AsyncSession, address: str) -> None:
        key = self._key(address)
        if len(self._demoed) < SITE_STATS_MAX_VISITORS_PER_DAY:
            self._demoed.add(key)
        await _bump(session, self._day, "demos")

    async def signup(self, session: AsyncSession, address: str) -> None:
        key = self._key(address)
        await _bump(session, self._day, "signups")
        if key in self._demoed:
            await _bump(session, self._day, "signups_after_demo")

    def _key(self, address: str) -> bytes:
        day = self._clock().date().isoformat()
        if day != self._day:  # a new day: forget yesterday's visitors entirely
            self._day, self._salt = day, secrets.token_bytes(16)
            self._visitors.clear()
            self._demoed.clear()
        return hashlib.sha256(self._salt + address.encode()).digest()


async def _bump(session: AsyncSession, day: str, name: str) -> None:
    await session.execute(
        insert(DailyCount)
        .values(day=day, name=name, count=1)
        .on_conflict_do_update(index_elements=["day", "name"], set_={"count": DailyCount.count + 1})
    )


async def site_stats(session: AsyncSession, now: datetime) -> SiteStats:
    days = [(now - timedelta(days=n)).date().isoformat() for n in reversed(range(SITE_STATS_DAYS))]
    rows = await session.execute(
        select(DailyCount.day, DailyCount.name, DailyCount.count).where(DailyCount.day >= days[0])
    )
    by_day: dict[str, dict[str, int]] = {day: {} for day in days}
    for day, name, count in rows.all():
        if day in by_day:
            by_day[day][name] = count
    real = select(User.id).where(User.is_guest.is_(False))
    seen_since = now - timedelta(days=ACTIVE_USER_DAYS)
    active = select(func.count(func.distinct(LoginSession.user_id))).where(
        LoginSession.last_seen_at >= seen_since, LoginSession.user_id.in_(real)
    )
    return SiteStats(
        days=[DayStats(day=day, **counts) for day, counts in by_day.items()],
        users=await session.scalar(select(func.count()).select_from(real.subquery())) or 0,
        active_users=await session.scalar(active) or 0,
        guests=await session.scalar(select(func.count()).where(User.is_guest)) or 0,
    )
