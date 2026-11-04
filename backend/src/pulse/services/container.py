from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pulse.config import Settings
from pulse.services.broadcaster import Broadcaster
from pulse.services.notifier import Notifier
from pulse.services.poller import Poller
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
