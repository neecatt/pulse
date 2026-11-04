from pulse.config import Settings
from pulse.slurm.base import (
    AccountRef,
    AccountSnapshot,
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
    "create_slurm_client",
]


def create_slurm_client(settings: Settings) -> SlurmClient:
    if settings.slurm_backend == "ssh":
        return SshSlurmClient(settings)
    return MockSlurmClient()
