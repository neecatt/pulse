from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pulse.auth.rate_limit import LoginRateLimiter
from pulse.auth.webauthn import ChallengeStore
from pulse.config import Settings
from pulse.domain import Clock
from pulse.services.assistants import Assistants
from pulse.services.broadcaster import Broadcaster
from pulse.services.notifier import Notifier
from pulse.services.poller import Poller
from pulse.services.stats import SiteCounter
from pulse.slurm import SlurmClient


@dataclass(frozen=True, slots=True)
class Services:
    """Long-lived objects created at startup and shared by request handlers."""

    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    slurm: SlurmClient
    notifier: Notifier
    broadcaster: Broadcaster
    poller: Poller
    login_limiter: LoginRateLimiter
    signup_limiter: LoginRateLimiter
    setup_code: str | None  # required to create the first account; None once set up
    passkey_challenges: ChallengeStore
    demo_limiter: LoginRateLimiter  # "Try the demo" guests per address
    # New guests and new sign-ups across all addresses (keys "guests", "signups").
    total_limiter: LoginRateLimiter
    clock: Clock  # the poller's notion of now (injected in tests)
    site: SiteCounter  # daily totals for the admin's site stats
    assistants: Assistants
