from fastapi import APIRouter

from pulse import __version__
from pulse.api import (
    accounts,
    agent,
    auth,
    events,
    jobs,
    live,
    passkeys,
    preferences,
    push,
    runs,
)
from pulse.api.deps import ServicesDep

api_router = APIRouter()
for module in (auth, passkeys, accounts, jobs, runs, events, preferences, push, live, agent):
    api_router.include_router(module.router)


@api_router.get("/health", tags=["meta"])
async def health(services: ServicesDep) -> dict[str, str]:
    return {
        "status": "ok",
        "version": __version__,
        "slurm_backend": services.settings.slurm_backend,
    }
