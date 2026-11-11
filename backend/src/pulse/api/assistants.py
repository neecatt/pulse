"""Codex account connection, cluster-local chat history and live conversations."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import urlsplit

import asyncssh
from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.api.deps import (
    CurrentUser,
    CurrentUserId,
    ServicesDep,
    SessionDep,
    get_owned_account,
    recently_verified,
    require_assistant_login,
    require_verified,
    session_is_active,
)
from pulse.constants import ASSISTANT_MAX_SESSIONS, STREAM_KEEPALIVE_SECONDS
from pulse.models import Account, AssistantAudit, LoginSession, User
from pulse.schemas import (
    AssistantAccess,
    AssistantAuditOut,
    AssistantConnection,
    AssistantConversation,
    AssistantCreate,
    AssistantDecision,
    AssistantLive,
    AssistantLogin,
    AssistantThread,
    AssistantThreads,
    AssistantTurn,
)
from pulse.services.assistants import (
    PERMISSIONS,
    TRAINING_INSTRUCTIONS,
    CodexConnection,
    thread_info,
)
from pulse.services.container import Services
from pulse.slurm.base import SlurmError

router = APIRouter(prefix="/assistants", tags=["assistants"])
ThreadId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


async def account_for(
    session: AsyncSession, user: User, account_id: int, services: Services
) -> Account:
    if not services.settings.assistants_enabled or user.is_guest:
        raise HTTPException(
            403, "Assistants are off. The admin can enable PULSE_ASSISTANTS_ENABLED."
        )
    account = await get_owned_account(session, user, account_id)
    if account.connection != "direct" or account.simulated:
        raise HTTPException(
            409,
            "Use a real cluster connected directly over SSH. The reporting agent stays read-only.",
        )
    return account


def connected(
    services: Services, user_id: int, account_id: int, request: Request
) -> CodexConnection:
    connection = services.assistants.get(user_id, account_id)
    if connection is None or not connection.connected:
        raise HTTPException(409, "Connect Codex on this cluster first.")
    require_assistant_login(request, connection.authorized_logins)
    return connection


def opened(connection: CodexConnection, thread_id: str) -> None:
    if thread_id not in connection.allowed_threads:
        raise HTTPException(409, "Open this conversation before sending a prompt or an approval.")


@router.get("/access")
async def access(
    request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AssistantAccess:
    return AssistantAccess(
        enabled=services.settings.assistants_enabled and not user.is_guest,
        verified=recently_verified(await session.get(LoginSession, request.state.login_session_id)),
    )


@router.get("/audit")
async def audit(session: SessionDep, user: CurrentUser) -> list[AssistantAuditOut]:
    statement = select(AssistantAudit).order_by(AssistantAudit.id.desc()).limit(100)
    if not user.is_admin:
        statement = statement.where(AssistantAudit.user_id == user.id)
    return [AssistantAuditOut.model_validate(a) for a in await session.scalars(statement)]


@router.get("/{account_id}/state")
async def state(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AssistantLive:
    await account_for(session, user, account_id, services)
    connection = services.assistants.get(user.id, account_id)
    return (
        connection.snapshot()
        if connection and request.state.login_session_hash in connection.authorized_logins
        else AssistantLive(
            connection=AssistantConnection(connected=False, signed_in=False),
            messages={},
            active={},
            approvals=[],
            revision=0,
        )
    )


@router.post("/{account_id}/connect")
async def connect(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AssistantConnection:
    await require_verified(request, session)
    account = await account_for(session, user, account_id, services)
    try:
        connection, keys = await services.assistants.connect(
            account.ref(public_only=not user.is_admin), account.id
        )
    except (SlurmError, asyncssh.Error, OSError, TimeoutError) as exc:
        message = (
            str(exc)
            if isinstance(exc, SlurmError)
            else "Couldn't reach Codex. Check the cluster's SSH connection and retry."
        )
        raise HTTPException(400, message) from exc
    account.pin_host_keys(keys)
    connection.authorized_logins.add(request.state.login_session_hash)
    session.add(AssistantAudit(user_id=user.id, session_id=str(account_id), action="connected"))
    await session.commit()
    return connection.account


@router.post("/{account_id}/login")
async def login(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> AssistantLogin:
    await require_verified(request, session)
    await account_for(session, user, account_id, services)
    connection = connected(services, user.id, account_id, request)
    async with connection.action_lock:
        if connection.login is not None:
            return connection.login
        result = await connection.rpc("account/login/start", {"type": "chatgptDeviceCode"})
        url = str(result.get("verificationUrl", ""))
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "auth.openai.com":
            raise HTTPException(
                400, "Codex didn't return a supported sign-in link. Update its CLI and retry."
            )
        connection.login = AssistantLogin(url=url, code=str(result.get("userCode", ""))[:128])
        connection.login_id = str(result.get("loginId", ""))
        return connection.login


@router.post("/{account_id}/disconnect", status_code=204)
async def disconnect(
    account_id: int, request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> None:
    await account_for(session, user, account_id, services)
    connection = services.assistants.get(user.id, account_id)
    if connection is not None:
        require_assistant_login(request, connection.authorized_logins)
    await services.assistants.disconnect(user.id, account_id)
    session.add(AssistantAudit(user_id=user.id, session_id=str(account_id), action="disconnected"))
    await session.commit()


@router.get("/{account_id}/threads")
async def threads(
    account_id: int,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> AssistantThreads:
    await account_for(session, user, account_id, services)
    return await connected(services, user.id, account_id, request).threads(cursor)


@router.get("/{account_id}/threads/{thread_id}")
async def history(
    account_id: int,
    thread_id: ThreadId,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> AssistantConversation:
    await account_for(session, user, account_id, services)
    return await connected(services, user.id, account_id, request).history(thread_id)


@router.post("/{account_id}/threads", status_code=201)
async def new_thread(
    account_id: int,
    body: AssistantCreate,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> AssistantThread:
    await require_verified(request, session)
    await account_for(session, user, account_id, services)
    connection = connected(services, user.id, account_id, request)
    async with connection.action_lock:
        result = await connection.rpc(
            "thread/start",
            {"cwd": body.work_dir, **PERMISSIONS, "developerInstructions": TRAINING_INSTRUCTIONS},
        )
        thread = thread_info(result["thread"])
        connection.allow(thread.id)
    session.add(AssistantAudit(user_id=user.id, session_id=thread.id, action="chat_started"))
    await session.commit()
    return thread


@router.post("/{account_id}/threads/{thread_id}/resume")
async def resume(
    account_id: int,
    thread_id: ThreadId,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> AssistantThread:
    await require_verified(request, session)
    await account_for(session, user, account_id, services)
    connection = connected(services, user.id, account_id, request)
    async with connection.action_lock:
        conversation = await connection.history(thread_id)
        # A remote transcript's paths are untrusted too. Never resume with a relative cwd.
        try:
            validated = AssistantCreate(work_dir=conversation.thread.work_dir, confirmed=True)
        except ValueError as exc:
            raise HTTPException(
                400,
                "This conversation has no valid project directory. "
                "Start a new chat with an absolute path.",
            ) from exc
        if thread_id in connection.active:
            return conversation.thread
        result = await connection.rpc(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": validated.work_dir,
                **PERMISSIONS,
                "developerInstructions": TRAINING_INSTRUCTIONS,
            },
        )
        thread = thread_info(result["thread"])
        connection.allow(thread.id)
    session.add(AssistantAudit(user_id=user.id, session_id=thread.id, action="chat_resumed"))
    await session.commit()
    return thread


@router.post("/{account_id}/threads/{thread_id}/turn", status_code=204)
async def turn(
    account_id: int,
    thread_id: ThreadId,
    body: AssistantTurn,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> None:
    await account_for(session, user, account_id, services)
    connection = connected(services, user.id, account_id, request)
    opened(connection, thread_id)
    async with connection.action_lock:
        if thread_id in connection.active:
            raise HTTPException(
                409, "Codex is still working. Wait or stop this turn before sending another."
            )
        if not body.prompt.strip():
            raise HTTPException(422, "Write a prompt first.")
        if len(connection.active) >= ASSISTANT_MAX_SESSIONS:
            raise HTTPException(
                409, "Wait for an active Codex task to finish before starting another."
            )
        connection.active[thread_id] = ""
        try:
            result = await connection.rpc(
                "turn/start",
                {"threadId": thread_id, "input": [{"type": "text", "text": body.prompt}]},
            )
        except BaseException:
            connection.active.pop(thread_id, None)
            connection.changed()
            raise
        # Notifications may already have completed the turn while rpc() was returning.
        if thread_id in connection.active:
            if result.get("turn", {}).get("status") == "inProgress":
                connection.active[thread_id] = str(result["turn"]["id"])
            else:
                connection.active.pop(thread_id, None)
        connection.changed()
    session.add(AssistantAudit(user_id=user.id, session_id=thread_id, action="prompt_sent"))
    await session.commit()


@router.post("/{account_id}/threads/{thread_id}/interrupt", status_code=204)
async def interrupt(
    account_id: int,
    thread_id: ThreadId,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> None:
    await account_for(session, user, account_id, services)
    connection = connected(services, user.id, account_id, request)
    opened(connection, thread_id)
    if turn_id := connection.active.get(thread_id):
        await connection.rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
        session.add(
            AssistantAudit(user_id=user.id, session_id=thread_id, action="turn_interrupted")
        )
        await session.commit()


@router.post("/{account_id}/approvals/{approval_id}", status_code=204)
async def decide(
    account_id: int,
    approval_id: str,
    body: AssistantDecision,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> None:
    await account_for(session, user, account_id, services)
    connection = connected(services, user.id, account_id, request)
    async with connection.action_lock:
        pending = connection.approvals.get(approval_id)
        if pending is None:
            raise HTTPException(409, "This approval is no longer waiting for a response.")
        if pending.expires <= time.monotonic():
            await connection.decide(approval_id, False, {})
            raise HTTPException(
                409, "This approval expired and was declined. Ask Codex to try again."
            )
        opened(connection, pending.item.thread_id)
        session.add(
            AssistantAudit(
                user_id=user.id,
                session_id=pending.item.thread_id,
                action="approval_accepted" if body.decision == "accept" else "approval_declined",
            )
        )
        await session.commit()  # record the decision before letting the command proceed
        await connection.decide(approval_id, body.decision == "accept", body.answers)


@router.get("/{account_id}/stream")
async def stream(
    account_id: int, request: Request, user_id: CurrentUserId, services: ServicesDep
) -> StreamingResponse:
    async with services.sessions() as db:
        user = await db.get(User, user_id)
        assert user is not None
        await account_for(db, user, account_id, services)
    connection = connected(services, user_id, account_id, request)

    async def events() -> AsyncIterator[str]:
        async with connection.subscribe() as queue:
            if not await session_is_active(services, user_id, request.state.login_session_hash):
                return
            sent = connection.snapshot()
            yield f"data: {sent.model_dump_json()}\n\n"
            while not await request.is_disconnected():
                # Release all DB transactions before streaming. Session revocation and
                # account removal are checked by the service's watchdog too.
                try:
                    await asyncio.wait_for(queue.get(), STREAM_KEEPALIVE_SECONDS)
                except TimeoutError:
                    if not await session_is_active(
                        services, user_id, request.state.login_session_hash
                    ):
                        return
                    yield ": keepalive\n\n"
                else:
                    await asyncio.sleep(0.1)  # coalesce token deltas, never poll the cluster
                    if not await session_is_active(
                        services, user_id, request.state.login_session_hash
                    ):
                        return
                    sent = connection.snapshot(since=sent.revision)
                    yield f"data: {sent.model_dump_json()}\n\n"
                if not connection.connected:
                    return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
