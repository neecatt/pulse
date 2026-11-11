"""Claude Code's own sign-in and Remote Control. No subscription-token proxy."""

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
from pulse.constants import STREAM_KEEPALIVE_SECONDS
from pulse.models import AssistantAudit, User
from pulse.schemas import AssistantThreads, ClaudeInput, ClaudeStart, ClaudeState
from pulse.services.claude import ClaudeSession, claude_errors

router = APIRouter(prefix="/assistants/{account_id}/claude", tags=["assistants"])


def native_session(
    services: ServicesDep, user_id: int, account_id: int, request: Request
) -> ClaudeSession:
    native = services.assistants.claude.get((user_id, account_id))
    if native is None:
        raise HTTPException(409, "Open Claude on this cluster first.")
    require_assistant_login(request, native.authorized_logins)
    return native


@router.get("/state")
async def state(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> ClaudeState:
    await account_for(session, user, account_id, services)
    native = services.assistants.claude.get((user.id, account_id))
    return (
        native.state
        if native and request.state.login_session_hash in native.authorized_logins
        else ClaudeState(phase="disconnected")
    )


@router.get("/threads")
async def threads(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AssistantThreads:
    await require_verified(request, session)
    account = await account_for(session, user, account_id, services)
    async with claude_errors():
        threads, keys = await services.assistants.claude_threads(
            account.ref(public_only=not user.is_admin)
        )
    account.pin_host_keys(keys)
    await session.commit()
    return threads


@router.post("/login")
async def login(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> ClaudeState:
    await require_verified(request, session)
    account = await account_for(session, user, account_id, services)
    async with claude_errors():
        native, keys = await services.assistants.start_claude(
            account.ref(public_only=not user.is_admin),
            account_id,
            login=True,
        )
    native.authorized_logins.add(request.state.login_session_hash)
    account.pin_host_keys(keys)
    session.add(
        AssistantAudit(user_id=user.id, session_id=str(account_id), action="claude_login_started")
    )
    await session.commit()
    return native.state


@router.post("/start")
async def start(
    account_id: int,
    body: ClaudeStart,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> ClaudeState:
    await require_verified(request, session)
    account = await account_for(session, user, account_id, services)
    async with claude_errors():
        native, keys = await services.assistants.start_claude(
            account.ref(public_only=not user.is_admin),
            account_id,
            login=False,
            work_dir=body.work_dir,
            session_id=body.session_id,
        )
    native.authorized_logins.add(request.state.login_session_hash)
    account.pin_host_keys(keys)
    session.add(
        AssistantAudit(
            user_id=user.id,
            session_id=body.session_id or str(account_id),
            action="claude_remote_started",
        )
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
    await require_verified(request, session)
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
    native = services.assistants.claude.get((user.id, account_id))
    if native is not None:
        require_assistant_login(request, native.authorized_logins)
    await services.assistants.stop_claude(user.id, account_id)
    session.add(
        AssistantAudit(user_id=user.id, session_id=str(account_id), action="claude_remote_stopped")
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
