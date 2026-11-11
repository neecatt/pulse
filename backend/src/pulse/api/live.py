import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from pulse.api.deps import CurrentUser, CurrentUserId, ServicesDep, session_is_active
from pulse.constants import STREAM_KEEPALIVE_SECONDS
from pulse.schemas import SetupInfo

router = APIRouter(tags=["live"])


@router.get("/stream")
async def stream(
    request: Request, user_id: CurrentUserId, services: ServicesDep
) -> StreamingResponse:
    """Server-Sent Events: an ``update`` message after every poll cycle."""
    if not services.broadcaster.has_subscribers:
        services.poller.trigger()  # the app just opened: fetch fresh data now

    async def events() -> AsyncIterator[str]:
        async with services.broadcaster.subscribe(user_id) as queue:
            if not await session_is_active(services, user_id, request.state.login_session_hash):
                return
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), STREAM_KEEPALIVE_SECONDS)
                except TimeoutError:
                    message = None
                if not await session_is_active(services, user_id, request.state.login_session_hash):
                    return
                yield f"data: {message}\n\n" if message is not None else ": keepalive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/setup")
async def setup(services: ServicesDep, user: CurrentUser) -> SetupInfo:
    """What the signed-in user needs to add accounts, including their own SSH key."""
    if user.is_guest:  # a demo guest's accounts are simulated: no key to install
        return SetupInfo(slurm_backend="mock", ssh_public_key=None)
    return SetupInfo(
        slurm_backend=services.settings.slurm_backend,
        ssh_public_key=services.slurm.public_key_for(user.id),
    )
