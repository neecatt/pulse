"""Codex's documented app-server protocol over a user's pinned SSH connection.

The cluster's unmodified CLI owns provider sign-in and local conversation history.
Pulse never reads auth.json, receives OAuth tokens, or asks for an API key.
"""

import asyncio
import contextlib
import json
import secrets
import shlex
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

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
    ASSISTANT_MAX_STATE_CHARS,
    ASSISTANT_MAX_TEXT,
)
from pulse.models import Account, LoginSession, User, utcnow
from pulse.schemas import (
    AssistantApproval,
    AssistantConnection,
    AssistantConversation,
    AssistantLive,
    AssistantLogin,
    AssistantMessage,
    AssistantThread,
    AssistantThreads,
)
from pulse.services.claude import HISTORY_SCRIPT, ClaudeSession, remote_command
from pulse.slurm.base import AccountRef, HostKeys, SlurmError
from pulse.slurm.ssh import SshSlurmClient

TRAINING_INSTRUCTIONS = (
    "You are running on an HPC login node through Pulse. Use Slurm for training "
    "and heavy computation, never run training directly on the login node. "
    "Read the project's instructions and inspect available partitions first. "
    "Show the batch script and resource request and ask the user before submitting, "
    "cancelling or modifying a job. Report the Slurm job ID after submission."
)
PERMISSIONS: dict[str, Any] = {
    "approvalPolicy": "untrusted",
    "approvalsReviewer": "user",
    "sandbox": "workspace-write",
}


def login_command(command: str) -> str:
    return "bash -lc " + shlex.quote(command)


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


@dataclass
class PendingApproval:
    rpc_id: str | int
    method: str
    item: AssistantApproval
    expires: float


class CodexConnection:
    def __init__(self, process: asyncssh.SSHClientProcess[str]) -> None:
        self.process = process
        self.connected = True
        self.account = AssistantConnection(connected=True, signed_in=False)
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.approvals: dict[str, PendingApproval] = {}
        self.messages: OrderedDict[str, OrderedDict[str, AssistantMessage]] = OrderedDict()
        self.active: dict[str, str] = {}
        self.allowed_threads: set[str] = set()  # only explicitly opened conversations can act
        self.authorized_logins: set[int] = set()
        self.login: AssistantLogin | None = None
        self.login_id: str | None = None
        self.error: str | None = None
        self.revision = 0
        self.last_used = time.monotonic()
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self.action_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[None]] = set()
        self._reader = asyncio.create_task(self._read())
        self._stderr = asyncio.create_task(self._discard_stderr())

    async def initialize(self) -> None:
        await self.rpc(
            "initialize",
            {"clientInfo": {"name": "pulse", "title": "Pulse", "version": __version__}},
        )
        await self.send({"method": "initialized"})
        await self.refresh_account()

    def changed(self) -> None:
        self.revision += 1
        for queue in self._subscribers:
            if queue.empty():
                queue.put_nowait(None)

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
            for key in [
                key
                for key, pending in self.approvals.items()
                if pending.item.thread_id == thread_id
            ]:
                del self.approvals[key]
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
            items = self.messages.setdefault(thread_id, OrderedDict())
            item = items.get(item_id)
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

    def _remember(self, thread_id: str, item: AssistantMessage) -> None:
        if not thread_id:
            return
        items = self.messages.setdefault(thread_id, OrderedDict())
        items[item.id] = item
        while len(items) > ASSISTANT_MAX_ITEMS:
            items.popitem(last=False)
        self.messages.move_to_end(thread_id)
        while len(self.messages) > ASSISTANT_MAX_SESSIONS:
            self.messages.popitem(last=False)
        while (
            sum(len(item.text) for items in self.messages.values() for item in items.values())
            > ASSISTANT_MAX_STATE_CHARS
        ):
            oldest_thread = next(iter(self.messages))
            oldest_items = self.messages[oldest_thread]
            oldest_items.popitem(last=False)
            if not oldest_items:
                del self.messages[oldest_thread]

    def allow(self, thread_id: str) -> None:
        if len(self.allowed_threads) >= ASSISTANT_MAX_ITEMS:
            inactive = self.allowed_threads - self.active.keys()
            if inactive:
                self.allowed_threads.remove(next(iter(inactive)))
        self.allowed_threads.add(thread_id)

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
        items = self.messages.get(thread_id)
        current = items.get(item_id) if items else None
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
        self.approvals[key] = PendingApproval(request_id, method, item, time.monotonic() + 600)
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

    async def expire_approvals(self) -> None:
        for key in [
            key for key, pending in self.approvals.items() if pending.expires <= time.monotonic()
        ]:
            await self.decide(key, False, {})

    def snapshot(self) -> AssistantLive:
        return AssistantLive(
            connection=self.account,
            messages={key: list(items.values()) for key, items in self.messages.items()},
            active=self.active,
            opened=list(self.allowed_threads),
            approvals=[pending.item for pending in self.approvals.values()],
            error=self.error,
            revision=self.revision,
        )

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[None]]:
        if len(self._subscribers) >= 4:
            raise SlurmError("This cluster already has four assistant screens open.")
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

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


class Assistants:
    def __init__(self, settings: Settings, ssh: SshSlurmClient | None) -> None:
        self.settings = settings
        self.ssh = ssh
        self._connections: dict[tuple[int, int], CodexConnection] = {}
        self.claude: dict[tuple[int, int], ClaudeSession] = {}
        self._lock = asyncio.Lock()

    async def claude_transport(
        self, account: AccountRef
    ) -> tuple[asyncssh.SSHClientConnection, HostKeys]:
        if self.ssh is None or account.simulated_since is not None:
            raise SlurmError("Claude needs a real cluster connected directly over SSH.")
        conn, keys = await self.ssh.connection(account)
        probe = await conn.run(
            login_command("command -v claude >/dev/null"),
            check=False,
            timeout=self.settings.ssh_command_timeout_seconds,
        )
        if probe.exit_status != 0:
            raise SlurmError(
                "Claude Code isn't in the cluster's login PATH. Install or load it, then retry."
            )
        return conn, keys

    async def start_claude(
        self,
        account: AccountRef,
        account_id: int,
        *,
        login: bool,
        work_dir: str = "",
        session_id: str | None = None,
    ) -> tuple[ClaudeSession, HostKeys]:
        async with self._lock:
            key = (account.owner_id, account_id)
            if key not in self.claude and (
                len(self.claude) >= ASSISTANT_MAX_CONNECTIONS
                or sum(owner == account.owner_id for owner, _ in self.claude)
                >= ASSISTANT_MAX_SESSIONS
            ):
                raise SlurmError("Disconnect another Claude session before opening this one.")
            conn, keys = await self.claude_transport(account)
            if not login:
                status = await conn.run(
                    login_command("claude auth status"),
                    check=False,
                    timeout=self.settings.ssh_command_timeout_seconds,
                )
                try:
                    auth = json.loads(str(status.stdout or "{}"))
                except ValueError:
                    auth = {}
                if not isinstance(auth, dict) or not auth.get("loggedIn"):
                    raise SlurmError(
                        "Claude isn't signed in on this cluster. "
                        "Use Sign in on cluster, then connect again."
                    )
                if auth.get("authMethod") != "claude.ai":
                    raise SlurmError(
                        "Remote Control needs Claude's native subscription sign-in. "
                        "Check the cluster's Claude authentication settings, then sign in again."
                    )
            if previous := self.claude.pop(key, None):
                await previous.close()
            command = (
                "exec claude auth login"
                if login
                else remote_command(work_dir, session_id, TRAINING_INSTRUCTIONS)
            )
            process = await conn.create_process(
                login_command(command),
                encoding="utf-8",
                errors="replace",
                stderr=asyncssh.STDOUT,
                **({"term_type": "xterm-256color", "term_size": (180, 40)} if not login else {}),
            )
            native = ClaudeSession(process, login=login, work_dir=work_dir, session_id=session_id)
            self.claude[key] = native
            return native, keys

    async def claude_threads(self, account: AccountRef) -> tuple[AssistantThreads, HostKeys]:
        conn, keys = await self.claude_transport(account)
        # auth status returns public metadata (including configDirectory), never tokens.
        status = await conn.run(
            login_command("claude auth status"),
            check=False,
            timeout=self.settings.ssh_command_timeout_seconds,
        )
        try:
            metadata = json.loads(str(status.stdout or "{}"))
        except ValueError:
            metadata = {}
        if not isinstance(metadata, dict):
            raise SlurmError(
                "Claude returned unreadable account metadata. Update the CLI and retry."
            )
        root = metadata.get("configDirectory")
        if root is not None and (not isinstance(root, str) or not root.startswith("/")):
            raise SlurmError(
                "Claude returned an invalid configuration directory. Check its installation."
            )
        result = await conn.run(
            login_command("python3 -c " + shlex.quote(HISTORY_SCRIPT)),
            input=json.dumps({"root": root}),
            check=False,
            timeout=self.settings.ssh_command_timeout_seconds,
        )
        if result.exit_status != 0:
            raise SlurmError(
                "Couldn't read Claude conversations. Check Python 3 and Claude Code on the cluster."
            )
        try:
            return AssistantThreads.model_validate_json(str(result.stdout)), keys
        except ValueError as exc:
            raise SlurmError(
                "Couldn't read Claude's conversation list. Check the cluster connection."
            ) from exc

    async def stop_claude(self, user_id: int, account_id: int) -> None:
        native = self.claude.pop((user_id, account_id), None)
        if native:
            await native.close()

    def get(self, user_id: int, account_id: int) -> CodexConnection | None:
        return self._connections.get((user_id, account_id))

    async def connect(
        self, account: AccountRef, account_id: int
    ) -> tuple[CodexConnection, HostKeys]:
        async with self._lock:
            existing = self.get(account.owner_id, account_id)
            if existing is not None and existing.connected:
                return existing, HostKeys()
            if existing is not None:
                await existing.close()
                del self._connections[(account.owner_id, account_id)]
            if self.ssh is None or account.simulated_since is not None:
                raise SlurmError("Assistants need a real cluster connected directly over SSH.")
            if (
                len(self._connections) >= ASSISTANT_MAX_CONNECTIONS
                or sum(key[0] == account.owner_id for key in self._connections)
                >= ASSISTANT_MAX_SESSIONS
            ):
                raise SlurmError("Disconnect another cluster assistant before connecting this one.")
            conn, keys = await self.ssh.connection(account)
            probe = await conn.run(
                login_command("command -v codex >/dev/null"),
                check=False,
                timeout=self.settings.ssh_command_timeout_seconds,
            )
            if probe.exit_status != 0:
                raise SlurmError(
                    "Codex isn't in this cluster's login PATH. "
                    "Install or load the Codex CLI, then reconnect."
                )
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
            self._connections[(account.owner_id, account_id)] = connection
            return connection, keys

    async def disconnect(self, user_id: int, account_id: int) -> None:
        connection = self._connections.pop((user_id, account_id), None)
        if connection:
            await connection.close()

    def keys(self) -> list[tuple[int, int]]:
        return list(self._connections)

    async def watch(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        while True:
            await asyncio.sleep(ASSISTANT_CHECK_SECONDS)
            for user_id, account_id in self.keys():
                connection = self.get(user_id, account_id)
                if connection is None:
                    continue
                async with sessions() as db:
                    account = await db.get(Account, account_id)
                    user = await db.get(User, user_id)
                    valid_login = await db.scalar(
                        select(LoginSession.id)
                        .where(
                            LoginSession.id.in_(connection.authorized_logins),
                            LoginSession.user_id == user_id,
                            LoginSession.expires_at > utcnow(),
                        )
                        .limit(1)
                    )
                valid = (
                    account is not None
                    and account.user_id == user_id
                    and account.connection == "direct"
                    and not account.simulated
                    and user is not None
                    and not user.is_guest
                    and valid_login is not None
                    and self.settings.assistants_enabled
                )
                idle = (
                    not connection.active
                    and time.monotonic() - connection.last_used
                    > self.settings.assistant_idle_seconds
                )
                if not valid or idle or not connection.connected:
                    await self.disconnect(user_id, account_id)
                else:
                    with contextlib.suppress(SlurmError, asyncssh.Error, OSError):
                        await connection.expire_approvals()
            for (user_id, account_id), native in list(self.claude.items()):
                async with sessions() as db:
                    account = await db.get(Account, account_id)
                    user = await db.get(User, user_id)
                    login = await db.scalar(
                        select(LoginSession.id)
                        .where(
                            LoginSession.id.in_(native.authorized_logins),
                            LoginSession.user_id == user_id,
                            LoginSession.expires_at > utcnow(),
                        )
                        .limit(1)
                    )
                valid = (
                    account is not None
                    and account.user_id == user_id
                    and account.connection == "direct"
                    and not account.simulated
                    and user is not None
                    and not user.is_guest
                    and login is not None
                    and self.settings.assistants_enabled
                )
                # Native Remote Control owns its activity; don't idle out someone
                # who is working in the Claude app rather than in the Pulse tab.
                idle = native.state.phase != "ready" and (
                    time.monotonic() - native.last_used > self.settings.assistant_idle_seconds
                )
                if not valid or idle:
                    await self.stop_claude(user_id, account_id)

    async def close(self) -> None:
        for user_id, account_id in self.keys():
            await self.disconnect(user_id, account_id)
        for user_id, account_id in list(self.claude):
            await self.stop_claude(user_id, account_id)
