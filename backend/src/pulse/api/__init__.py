from fastapi import APIRouter

from pulse.api import accounts, events, jobs, preferences, push
from pulse.api.deps import ServicesDep

api_router = APIRouter()
for module in (accounts, jobs, events, preferences, push):
    api_router.include_router(module.router)


@api_router.get("/health", tags=["meta"])
async def health(services: ServicesDep) -> dict[str, str]:
    return {"status": "ok", "slurm_backend": services.settings.slurm_backend}
