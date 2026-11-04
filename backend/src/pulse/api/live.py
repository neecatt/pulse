import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from pulse.api.deps import CurrentUserId, ServicesDep
from pulse.schemas import SetupInfo

router = APIRouter(tags=["live"])

KEEPALIVE_S = 15


@router.get("/stream")
async def stream(
    request: Request, user_id: CurrentUserId, services: ServicesDep
) -> StreamingResponse:
    """Server-Sent Events: an ``update`` message after every poll cycle."""
    if not services.broadcaster.has_subscribers:
        services.poller.trigger()  # the app just opened: fetch fresh data now

    async def events() -> AsyncIterator[str]:
        async with services.broadcaster.subscribe(user_id) as queue:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
                except TimeoutError:
                    yield ": keepalive\n\n"
                else:
                    yield f"data: {message}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/setup")
async def setup(services: ServicesDep) -> SetupInfo:
    return SetupInfo(
        slurm_backend=services.settings.slurm_backend,
        ssh_public_key=services.slurm.public_key,
    )
