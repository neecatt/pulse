from pulse.config import Settings
from pulse.slurm.base import (
    AccountRef,
    AccountSnapshot,
    Cursors,
    Hop,
    HostKeys,
    JobTelemetry,
    SlurmClient,
    SlurmError,
    SlurmJob,
)
from pulse.slurm.mock import MockSlurmClient
from pulse.slurm.ssh import SshSlurmClient

__all__ = [
    "AccountRef",
    "AccountSnapshot",
    "Hop",
    "HostKeys",
    "JobTelemetry",
    "SlurmClient",
    "SlurmError",
    "SlurmJob",
    "WithSimulated",
    "create_slurm_client",
]


def create_slurm_client(settings: Settings) -> SlurmClient:
    if settings.slurm_backend == "mock":
        return MockSlurmClient()
    # Always, not only with PULSE_DEMO on: demo accounts made while it was on
    # must never be polled over SSH after it's switched off.
    return WithSimulated(SshSlurmClient(settings), MockSlurmClient())


class WithSimulated:
    """Real Slurm for real accounts, the simulated cluster for demo accounts.

    Which one an account gets is decided by the server (``simulated`` is set only
    on guests' accounts), so a demo visitor can't make Pulse connect anywhere."""

    def __init__(self, real: SlurmClient, simulated: SlurmClient) -> None:
        self._real = real
        self._simulated = simulated

    def _for(self, account: AccountRef) -> SlurmClient:
        return self._simulated if account.simulated_since else self._real

    def public_key_for(self, user_id: int) -> str | None:
        return self._real.public_key_for(user_id)

    async def check(self, account: AccountRef) -> HostKeys:
        return await self._for(account).check(account)

    async def snapshot(self, account: AccountRef, cursors: Cursors) -> AccountSnapshot:
        return await self._for(account).snapshot(account, cursors)

    async def close(self) -> None:
        await self._real.close()
        await self._simulated.close()
