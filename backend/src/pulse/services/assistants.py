"""Cluster assistants over a user's pinned SSH connection: Codex's app-server and
Claude Code's headless mode, plus Claude's native sign-in."""

import asyncio
import contextlib
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Iterable
from typing import Any, Literal

import asyncssh
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pulse import __version__
from pulse.config import Settings
from pulse.constants import (
    ASSISTANT_CHECK_SECONDS,
    ASSISTANT_MAX_CONNECTIONS,
    ASSISTANT_MAX_ITEMS,
    ASSISTANT_MAX_PENDING,
    ASSISTANT_MAX_RPC_BYTES,
    ASSISTANT_MAX_SESSIONS,
    ASSISTANT_MAX_TEXT,
)
from pulse.models import Account, LoginSession, User, utcnow
from pulse.schemas import (
    AssistantApproval,
    AssistantConnection,
    AssistantConversation,
    AssistantLogin,
    AssistantMessage,
    AssistantModel,
    AssistantThread,
    AssistantThreads,
)
from pulse.services.chat import (
    APPROVAL_SECONDS,
    TRAINING_INSTRUCTIONS,
    ChatConnection,
    PendingApproval,
    login_command,
)
from pulse.services.claude import ClaudeSession
from pulse.services.claude_chat import ClaudeChat, claude_auth
from pulse.slurm.base import AccountRef, HostKeys, SlurmError
from pulse.slurm.ssh import SshSlurmClient

logger = logging.getLogger(__name__)

PERMISSIONS: dict[str, Any] = {
    "approvalPolicy": "untrusted",
    "approvalsReviewer": "user",
    "sandbox": "workspace-write",
}


def thread_info(raw: dict[str, Any]) -> AssistantThread:
    return AssistantThread(
        id=str(raw["id"]),
        title=str(raw.get("name") or raw.get("preview") or "New conversation")[:200],
        work_dir=str(raw.get("cwd") or ""),
        updated_at=int(raw.get("updatedAt") or 0),
    )


def message_info(raw: dict[str, Any]) -> AssistantMessage | None:
    kind = str(raw.get("type", ""))
    role = "tool"
    text = ""
    if kind == "userMessage":
        role = "user"
        text = "\n".join(
            str(c.get("text", "")) for c in raw.get("content", []) if c.get("type") == "text"
        )
    elif kind == "agentMessage":
        role = "assistant"
        text = str(raw.get("text", ""))
    elif kind == "commandExecution":
        text = str(raw.get("command", "")) + "\n" + str(raw.get("aggregatedOutput") or "")
    elif kind == "fileChange":
        text = "\n\n".join(
            str(c.get("path", "")) + "\n" + str(c.get("diff", "")) for c in raw.get("changes", [])
        )
    elif kind == "plan":
        role = "assistant"
        text = str(raw.get("text", ""))
    else:
        return None
    return AssistantMessage(
        id=str(raw.get("id", "")),
        role=role,
        kind=kind,
        text=text[-ASSISTANT_MAX_TEXT:],
        status=raw.get("status"),
    )


class CodexConnection(ChatConnection):
    """Codex's documented app-server protocol. The cluster's unmodified CLI owns
    provider sign-in and local conversation history; Pulse never reads auth.json,
    receives OAuth tokens, or asks for an API key."""

    name = "Codex"

    def __init__(self, process: asyncssh.SSHClientProcess[str]) -> None:
        super().__init__()
        self.process = process
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.login: AssistantLogin | None = None
        self.login_id: str | None = None
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._models: list[AssistantModel] | None = None
        self._reader = asyncio.create_task(self._read())
        self._stderr = asyncio.create_task(self._discard_stderr())

    async def initialize(self) -> None:
        await self.rpc(
            "initialize",
            {"clientInfo": {"name": "pulse", "title": "Pulse", "version": __version__}},
        )
        await self.send({"method": "initialized"})
        await self.refresh_account()

    async def send(self, value: dict[str, Any]) -> None:
        if not self.connected:
            raise SlurmError("The cluster connection closed. Reconnect Codex to continue.")
        async with self._write_lock:
            self.process.stdin.write(json.dumps(value) + "\n")
            await self.process.stdin.drain()

    async def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if len(self.pending) >= ASSISTANT_MAX_PENDING:
            raise SlurmError("Codex is busy. Wait a moment and try again.")
        self.last_used = time.monotonic()
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"id": request_id, "method": method, "params": params or {}})
            return await asyncio.wait_for(future, 60)
        except TimeoutError as exc:
            raise SlurmError(
                "Codex didn't respond. Check the cluster connection and retry."
            ) from exc
        finally:
            self.pending.pop(request_id, None)

    async def refresh_account(self) -> AssistantConnection:
        result = await self.rpc("account/read", {"refreshToken": False})
        account = result.get("account") or {}
        self.account = AssistantConnection(
            connected=self.connected,
            signed_in=bool(account),
            email=account.get("email"),
        )
        self.changed()
        return self.account

    async def _discard_stderr(self) -> None:
        with contextlib.suppress(asyncssh.Error, OSError):
            while await self.process.stderr.read(8192):
                pass  # CLI diagnostics may contain private paths; never forward or log them.

    async def _read(self) -> None:
        buffer = ""
        try:
            while chunk := await self.process.stdout.read(8192):
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if len(line.encode()) > ASSISTANT_MAX_RPC_BYTES:
                        raise ValueError
                    if line.strip():
                        await self._message(json.loads(line))
                if len(buffer.encode()) > ASSISTANT_MAX_RPC_BYTES:
                    raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, asyncssh.Error, OSError):
            self.error = "Codex sent an unreadable response. Update the cluster CLI and reconnect."
        finally:
            self.connected = False
            self.account.connected = False
            self.active.clear()
            self.approvals.clear()
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(
                        SlurmError("Codex disconnected. Check its installation and reconnect.")
                    )
            self.changed()

    async def _message(self, value: dict[str, Any]) -> None:
        if "method" not in value and isinstance(value.get("id"), int):
            future = self.pending.get(value["id"])
            if future and not future.done():
                if "error" in value:
                    # Never expose raw RPC failures, credentials or remote stack traces.
                    future.set_exception(
                        SlurmError(
                            "Codex couldn't complete that request. "
                            "Check that the CLI is current and the conversation is available."
                        )
                    )
                else:
                    future.set_result(value.get("result") or {})
            return
        method, params = value.get("method", ""), value.get("params") or {}
        if "id" in value:
            await self._approval(value["id"], method, params)
            return
        thread_id = str(params.get("threadId") or "")
        if method == "account/login/completed":
            self.login = None
            self.login_id = None
            if not params.get("success"):
                self.error = "Sign-in wasn't completed. Connect Codex again to retry."
            else:
                self.account.signed_in = True
                self.error = None
        elif method == "account/updated":
            self.account.signed_in = params.get("authMode") is not None
        elif method == "turn/started":
            self.active[thread_id] = str(params.get("turn", {}).get("id", ""))
            self.error = None
        elif method == "turn/completed":
            self.active.pop(thread_id, None)
            if params.get("turn", {}).get("status") == "failed":
                self.error = (
                    "Codex couldn't finish this turn. "
                    "Check your plan access and cluster setup, then try again."
                )
            self._drop_approvals(thread_id)
        elif method in {"item/started", "item/completed"}:
            item = message_info(params.get("item", {}))
            if item:
                self._remember(thread_id, item)
        elif method in {
            "item/agentMessage/delta",
            "item/commandExecution/outputDelta",
            "item/plan/delta",
        }:
            item_id = str(params.get("itemId", ""))
            item = self._item(thread_id, item_id)
            if item is None:
                item = AssistantMessage(
                    id=item_id,
                    role="assistant" if "agentMessage" in method else "tool",
                    kind="agentMessage" if "agentMessage" in method else "commandExecution",
                    text="",
                )
            item = item.model_copy(
                update={"text": (item.text + str(params.get("delta", "")))[-ASSISTANT_MAX_TEXT:]}
            )
            self._remember(thread_id, item)
        elif method == "serverRequest/resolved":
            request_id = params.get("requestId")
            for key in [
                key for key, pending in self.approvals.items() if pending.rpc_id == request_id
            ]:
                del self.approvals[key]
        elif method == "error":
            self.error = "Codex reported a problem. Check your plan access and cluster setup."
        self.changed()

    async def _approval(self, request_id: str | int, method: str, params: dict[str, Any]) -> None:
        supported = {
            "item/commandExecution/requestApproval": "command",
            "item/fileChange/requestApproval": "files",
            "item/tool/requestUserInput": "question",
        }
        thread_id = str(params.get("threadId", ""))
        if (
            method not in supported
            or thread_id not in self.allowed_threads
            or len(self.approvals) >= ASSISTANT_MAX_PENDING
        ):
            await self.send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": "This request isn't supported by Pulse."},
                }
            )
            return
        kind = supported[method]
        item_id = str(params.get("itemId", ""))
        current = self._item(thread_id, item_id)
        detail = str(
            params.get("command")
            or (current.text if current else "")
            or params.get("reason")
            or "Review this change before continuing."
        )
        key = secrets.token_urlsafe(16)
        item = AssistantApproval(
            id=key,
            thread_id=thread_id,
            kind=kind,
            title={
                "command": "Run this command?",
                "files": "Apply these file changes?",
                "question": "Codex needs your answer",
            }[kind],
            detail=detail[-ASSISTANT_MAX_TEXT:],
            questions=params.get("questions", [])[:10],
        )
        self.approvals[key] = PendingApproval(
            request_id, method, item, time.monotonic() + APPROVAL_SECONDS
        )
        self.changed()

    async def decide(self, key: str, accept: bool, answers: dict[str, list[str]]) -> str:
        pending = self.approvals.pop(key, None)
        if pending is None:
            raise SlurmError("That request is no longer waiting for a response.")
        if pending.expires <= time.monotonic():
            accept = False
        if pending.item.kind == "question":
            result: dict[str, Any] = {
                "answers": {
                    str(q["id"]): {"answers": answers.get(str(q["id"]), []) if accept else []}
                    for q in pending.item.questions
                }
            }
        else:
            result = {"decision": "accept" if accept else "decline"}
        await self.send({"id": pending.rpc_id, "result": result})
        self.changed()
        return pending.item.thread_id

    async def history(self, thread_id: str) -> AssistantConversation:
        raw = (await self.rpc("thread/read", {"threadId": thread_id, "includeTurns": True}))[
            "thread"
        ]
        items = [item for turn in raw.get("turns", []) for item in turn.get("items", [])]
        messages = [
            message
            for item in items[-ASSISTANT_MAX_ITEMS:]
            if (message := message_info(item)) is not None
        ]
        return AssistantConversation(thread=thread_info(raw), messages=messages)

    async def threads(self, cursor: str | None) -> AssistantThreads:
        raw = await self.rpc(
            "thread/list", {"limit": 30, "cursor": cursor, "sortKey": "updated_at"}
        )
        return AssistantThreads(
            data=[thread_info(t) for t in raw.get("data", [])[:30]],
            next_cursor=raw.get("nextCursor"),
        )

    async def start_thread(self, work_dir: str) -> AssistantThread:
        result = await self.rpc(
            "thread/start",
            {"cwd": work_dir, **PERMISSIONS, "developerInstructions": TRAINING_INSTRUCTIONS},
        )
        thread = thread_info(result["thread"])
        self.allow(thread.id)
        return thread

    async def resume_thread(self, thread: AssistantThread) -> AssistantThread:
        if thread.id in self.active:
            return thread
        result = await self.rpc(
            "thread/resume",
            {
                "threadId": thread.id,
                "cwd": thread.work_dir,
                **PERMISSIONS,
                "developerInstructions": TRAINING_INSTRUCTIONS,
            },
        )
        resumed = thread_info(result["thread"])
        self.allow(resumed.id)
        return resumed

    async def models(self) -> list[AssistantModel]:
        if self._models is None:
            raw = await self.rpc("model/list", {"includeHidden": False})
            self._models = [
                AssistantModel(
                    id=str(m.get("model") or m["id"]),
                    name=str(m.get("displayName") or m.get("model") or m["id"]),
                    description=str(m.get("description") or ""),
                    efforts=[
                        str(o["reasoningEffort"])
                        for o in m.get("supportedReasoningEfforts") or []
                        if isinstance(o, dict) and o.get("reasoningEffort")
                    ],
                    default_effort=m.get("defaultReasoningEffort"),
                    is_default=bool(m.get("isDefault")),
                )
                for m in raw.get("data", [])[:50]
                if isinstance(m, dict) and not m.get("hidden")
            ]
        return self._models

    async def send_turn(
        self, thread_id: str, prompt: str, model: str | None = None, effort: str | None = None
    ) -> None:
        self.active[thread_id] = ""
        options = {"model": model, "effort": effort}
        try:
            result = await self.rpc(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    **{key: value for key, value in options.items() if value is not None},
                },
            )
        except BaseException:
            self.active.pop(thread_id, None)
            self.changed()
            raise
        # Notifications may already have completed the turn while rpc() was returning.
        if thread_id in self.active:
            if result.get("turn", {}).get("status") == "inProgress":
                self.active[thread_id] = str(result["turn"]["id"])
            else:
                self.active.pop(thread_id, None)
        self.changed()

    async def interrupt(self, thread_id: str) -> bool:
        turn_id = self.active.get(thread_id)
        if not turn_id:
            return False
        await self.rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
        return True

    async def close(self) -> None:
        self.process.close()
        self._reader.cancel()
        self._stderr.cancel()
        await asyncio.gather(self._reader, self._stderr, return_exceptions=True)
        with contextlib.suppress(TimeoutError, asyncssh.Error, OSError):
            await asyncio.wait_for(self.process.wait_closed(), 5)
        self.connected = False
        self.account.connected = False
        self.changed()


Provider = Literal["codex", "claude"]


class Assistants:
    def __init__(self, settings: Settings, ssh: SshSlurmClient | None) -> None:
        self.settings = settings
        self.ssh = ssh
        self._connections: dict[tuple[Provider, int, int], ChatConnection] = {}
        # Claude Code's own `claude auth login`, run on the cluster for the user.
        self.sign_ins: dict[tuple[int, int], ClaudeSession] = {}
        # Slow SSH work runs under a per-account lock; the shared lock only reserves
        # capacity, so one unreachable cluster never blocks other users.
        self._lock = asyncio.Lock()
        self._locks: dict[tuple[str, int, int], asyncio.Lock] = {}
        self._starting: set[tuple[str, int, int]] = set()

    @contextlib.asynccontextmanager
    async def _reserve(
        self, kind: str, key: tuple[int, int], open_keys: Iterable[tuple[int, int]], message: str
    ) -> AsyncIterator[None]:
        """Hold ``kind``'s lock for ``key``, counting it against the connection limits."""
        slot = (kind, *key)
        async with self._locks.setdefault(slot, asyncio.Lock()):
            async with self._lock:
                taken = set(open_keys) | {(u, a) for k, u, a in self._starting if k == kind}
                if key not in taken and (
                    len(taken) >= ASSISTANT_MAX_CONNECTIONS
                    or sum(owner == key[0] for owner, _ in taken) >= ASSISTANT_MAX_SESSIONS
                ):
                    raise SlurmError(message)
                self._starting.add(slot)
            try:
                yield
            finally:
                self._starting.discard(slot)

    async def _transport(
        self, account: AccountRef, program: str
    ) -> tuple[asyncssh.SSHClientConnection, HostKeys]:
        if self.ssh is None or account.simulated_since is not None:
            raise SlurmError("Assistants need a real cluster connected directly over SSH.")
        conn, keys = await self.ssh.connection(account)
        probe = await conn.run(
            login_command(f"command -v {program} >/dev/null"),
            check=False,
            timeout=self.settings.ssh_command_timeout_seconds,
        )
        if probe.exit_status != 0:
            raise SlurmError(
                {
                    "codex": "Codex isn't in this cluster's login PATH. "
                    "Install or load the Codex CLI, then reconnect.",
                    "claude": "Claude Code isn't in the cluster's login PATH. "
                    "Install or load it, then retry.",
                }[program]
            )
        return conn, keys

    async def start_sign_in(
        self, account: AccountRef, account_id: int
    ) -> tuple[ClaudeSession, HostKeys]:
        key = (account.owner_id, account_id)
        async with self._reserve(
            "claude-login",
            key,
            self.sign_ins,
            "Finish signing in to Claude on another cluster first.",
        ):
            conn, keys = await self._transport(account, "claude")
            if previous := self.sign_ins.pop(key, None):
                await previous.close()
            process = await conn.create_process(
                login_command("exec claude auth login"),
                encoding="utf-8",
                errors="replace",
                stderr=asyncssh.STDOUT,
            )
            native = ClaudeSession(process)
            self.sign_ins[key] = native
            return native, keys

    async def stop_sign_in(self, user_id: int, account_id: int) -> None:
        native = self.sign_ins.pop((user_id, account_id), None)
        if native:
            await native.close()

    def get(self, provider: Provider, user_id: int, account_id: int) -> ChatConnection | None:
        return self._connections.get((provider, user_id, account_id))

    async def connect(
        self, provider: Provider, account: AccountRef, account_id: int
    ) -> tuple[ChatConnection, HostKeys]:
        key = (account.owner_id, account_id)
        async with self._reserve(
            provider,
            key,
            (
                (user, acct)
                for (kind, user, acct), c in self._connections.items()
                if kind == provider and c.connected
            ),
            "Disconnect another cluster assistant before connecting this one.",
        ):
            existing = self.get(provider, *key)
            if existing is not None and existing.connected:
                if not existing.account.signed_in:
                    await existing.refresh_account()  # e.g. after signing in on the cluster
                return existing, HostKeys()
            if existing is not None:
                await existing.close()
                self._connections.pop((provider, *key), None)
            conn, keys = await self._transport(account, provider)
            connection: ChatConnection
            if provider == "claude":
                timeout = self.settings.ssh_command_timeout_seconds
                connection = ClaudeChat(
                    conn, timeout=timeout, auth=await claude_auth(conn, timeout)
                )
            else:
                process = await conn.create_process(
                    login_command("exec codex app-server --listen stdio://"),
                    encoding="utf-8",
                    errors="replace",
                )
                connection = CodexConnection(process)
                try:
                    await connection.initialize()
                except BaseException:
                    await connection.close()
                    raise
            self._connections[(provider, *key)] = connection
            return connection, keys

    async def disconnect(self, provider: Provider, user_id: int, account_id: int) -> None:
        connection = self._connections.pop((provider, user_id, account_id), None)
        if connection:
            await connection.close()

    def keys(self) -> list[tuple[Provider, int, int]]:
        return list(self._connections)

    async def watch(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        while True:
            await asyncio.sleep(ASSISTANT_CHECK_SECONDS)
            try:
                await self.check(sessions)
            except Exception:
                # Keep enforcing revocation and idle limits on the next pass.
                logger.exception("assistant check failed")

    async def _valid(
        self,
        sessions: async_sessionmaker[AsyncSession],
        user_id: int,
        account_id: int,
        logins: set[str],
    ) -> bool:
        """The owner, account and an authorizing Pulse login are all still valid."""
        async with sessions() as db:
            account = await db.get(Account, account_id)
            user = await db.get(User, user_id)
            login = await db.scalar(
                select(LoginSession.id)
                .where(
                    LoginSession.token_hash.in_(logins),
                    LoginSession.user_id == user_id,
                    LoginSession.expires_at > utcnow(),
                )
                .limit(1)
            )
        return (
            account is not None
            and account.user_id == user_id
            and account.connection == "direct"
            and not account.simulated
            and user is not None
            and not user.is_guest
            and login is not None
            and self.settings.assistants_enabled
        )

    async def check(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Close connections whose owner, account or login is no longer valid, or idle."""
        idle_after = self.settings.assistant_idle_seconds
        for provider, user_id, account_id in self.keys():
            connection = self.get(provider, user_id, account_id)
            if connection is None:
                continue
            valid = await self._valid(sessions, user_id, account_id, connection.authorized_logins)
            idle = not connection.active and time.monotonic() - connection.last_used > idle_after
            if not valid or idle or not connection.connected:
                await self.disconnect(provider, user_id, account_id)
            else:
                with contextlib.suppress(SlurmError, asyncssh.Error, OSError):
                    await connection.expire_approvals()
        for (user_id, account_id), native in list(self.sign_ins.items()):
            valid = await self._valid(sessions, user_id, account_id, native.authorized_logins)
            if not valid or time.monotonic() - native.last_used > idle_after:
                await self.stop_sign_in(user_id, account_id)

    async def close(self) -> None:
        for provider, user_id, account_id in self.keys():
            await self.disconnect(provider, user_id, account_id)
        for user_id, account_id in list(self.sign_ins):
            await self.stop_sign_in(user_id, account_id)
