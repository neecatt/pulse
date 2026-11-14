"""Claude Code's own sign-in on the cluster. No subscription-token proxy."""

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from pulse.api.assistants import account_for
from pulse.api.deps import (
    CurrentUser,
    CurrentUserId,
    ServicesDep,
    SessionDep,
    require_assistant_login,
    require_verified,
    session_is_active,
)
from pulse.constants import ASSISTANT_VERIFIED_SECONDS, STREAM_KEEPALIVE_SECONDS
from pulse.models import AssistantAudit, User
from pulse.schemas import ClaudeInput, ClaudeState
from pulse.services.claude import ClaudeSession, claude_errors

router = APIRouter(prefix="/assistants/{account_id}/claude", tags=["assistants"])


def native_session(
    services: ServicesDep, user_id: int, account_id: int, request: Request
) -> ClaudeSession:
    native = services.assistants.sign_ins.get((user_id, account_id))
    if native is None:
        raise HTTPException(409, "Start Claude sign-in on this cluster first.")
    require_assistant_login(request, native.authorized_logins)
    return native


@router.get("/state")
async def state(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> ClaudeState:
    await account_for(session, user, account_id, services)
    native = services.assistants.sign_ins.get((user.id, account_id))
    return (
        native.state
        if native and request.state.login_session_hash in native.authorized_logins
        else ClaudeState(phase="disconnected")
    )


@router.post("/login")
async def login(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> ClaudeState:
    await require_verified(request, session, ASSISTANT_VERIFIED_SECONDS)
    account = await account_for(session, user, account_id, services)
    async with claude_errors():
        native, keys = await services.assistants.start_sign_in(
            account.ref(public_only=not user.is_admin), account_id
        )
    native.authorized_logins.add(request.state.login_session_hash)
    account.pin_host_keys(keys)
    session.add(
        AssistantAudit(user_id=user.id, session_id=str(account_id), action="claude_login_started")
    )
    await session.commit()
    return native.state


@router.post("/setup", status_code=204)
async def setup(
    account_id: int,
    body: ClaudeInput,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> None:
    await account_for(session, user, account_id, services)
    native = native_session(services, user.id, account_id, request)
    try:
        async with claude_errors():
            await native.input(body.action, body.code)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/stop", status_code=204)
async def stop(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> None:
    await account_for(session, user, account_id, services)
    native = services.assistants.sign_ins.get((user.id, account_id))
    if native is not None:
        require_assistant_login(request, native.authorized_logins)
    await services.assistants.stop_sign_in(user.id, account_id)
    session.add(
        AssistantAudit(user_id=user.id, session_id=str(account_id), action="claude_login_stopped")
    )
    await session.commit()


@router.get("/stream")
async def stream(
    account_id: int, request: Request, user_id: CurrentUserId, services: ServicesDep
) -> StreamingResponse:
    async with services.sessions() as db:
        user = await db.get(User, user_id)
        assert user is not None
        await account_for(db, user, account_id, services)
    native = native_session(services, user_id, account_id, request)

    async def events() -> AsyncIterator[str]:
        async with native.subscribe() as queue:
            if not await session_is_active(services, user_id, request.state.login_session_hash):
                return
            yield f"data: {native.state.model_dump_json()}\n\n"
            while not await request.is_disconnected():
                try:
                    await asyncio.wait_for(queue.get(), STREAM_KEEPALIVE_SECONDS)
                except TimeoutError:
                    if not await session_is_active(
                        services, user_id, request.state.login_session_hash
                    ):
                        return
                    yield ": keepalive\n\n"
                else:
                    if not await session_is_active(
                        services, user_id, request.state.login_session_hash
                    ):
                        return
                    yield f"data: {native.state.model_dump_json()}\n\n"
                if not native.connected:
                    return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
