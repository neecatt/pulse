"""Claude Code's headless stream-json mode, as a chat inside Pulse.

Each opened conversation runs the cluster's unmodified CLI (``claude -p``) in its
project directory, with Pulse as its permission prompt: every tool request that the
user's own Claude rules don't already allow becomes an approval card. Sign-in, tokens
and transcripts stay with the CLI on the cluster; Pulse never reads credentials.
"""

import asyncio
import contextlib
import json
import re
import secrets
import shlex
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import asyncssh

from pulse.assistants.claude_history import conversation_record
from pulse.constants import (
    ASSISTANT_MAX_ITEMS,
    ASSISTANT_MAX_PENDING,
    ASSISTANT_MAX_RPC_BYTES,
    ASSISTANT_MAX_SESSIONS,
    ASSISTANT_MAX_TEXT,
)
from pulse.schemas import (
    AssistantApproval,
    AssistantConnection,
    AssistantConversation,
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
from pulse.services.claude import HISTORY_SCRIPT
from pulse.slurm.base import SlurmError

SESSION_ID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
FILE_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
DECLINED = "The user declined this in Pulse."
STDERR_CHARS = 2000


HEADLESS = [
    "claude",
    "-p",
    "--input-format",
    "stream-json",
    "--output-format",
    "stream-json",
    "--verbose",
]
INITIALIZE = {
    "type": "control_request",
    "request_id": "pulse-init",
    "request": {"subtype": "initialize", "hooks": None},
}


def chat_command(
    work_dir: str,
    session_id: str,
    *,
    resume: bool,
    model: str | None = None,
    effort: str | None = None,
) -> str:
    argv = [
        *HEADLESS,
        "--include-partial-messages",
        # Pulse answers every permission prompt; the user's own allow rules still apply.
        "--permission-prompt-tool",
        "stdio",
        "--permission-mode",
        "default",
        "--resume" if resume else "--session-id",
        session_id,
        "--append-system-prompt",
        TRAINING_INSTRUCTIONS,
    ]
    if model:
        argv += ["--model", model]
    if effort:
        argv += ["--effort", effort]
    return "cd -- " + shlex.quote(work_dir) + " && exec " + shlex.join(argv)


def listed_models(value: Any) -> list[AssistantModel] | None:
    """The models in Claude's initialize response, with their thinking levels."""
    if not isinstance(value, list):
        return None
    return [
        AssistantModel(
            id=str(m["value"]),
            name=str(m.get("displayName") or m["value"]),
            description=str(m.get("description") or ""),
            efforts=[str(e) for e in m.get("supportedEffortLevels") or []]
            if m.get("supportsEffort")
            else [],
            is_default=m["value"] == "default",
        )
        for m in value[:50]
        if isinstance(m, dict) and isinstance(m.get("value"), str)
    ]


def tool_summary(name: str, value: dict[str, Any]) -> tuple[str, str]:
    """The chat item kind and readable text for one tool call."""
    if name == "Bash":
        return "commandExecution", str(value.get("command", ""))
    if name in FILE_TOOLS:
        path = str(value.get("file_path") or value.get("notebook_path") or "")
        edits = value.get("edits")
        changes = [
            "\n".join(
                [
                    *("- " + line for line in str(edit.get("old_string", "")).splitlines()),
                    *("+ " + line for line in str(edit.get("new_string", "")).splitlines()),
                ]
            )
            for edit in (edits if isinstance(edits, list) else [value])
            if isinstance(edit, dict) and ("old_string" in edit or "new_string" in edit)
        ]
        body = "\n\n".join(changes) or str(value.get("content") or value.get("new_source") or "")
        return "fileChange", path + "\n" + body
    return "toolCall", name + "\n" + json.dumps(value, ensure_ascii=False, indent=2)


class Transcript:
    """Turns Claude Code messages into chat items with the same ids live and from
    saved history, so reloading a conversation never duplicates what was streamed."""

    def __init__(self) -> None:
        self._texts: dict[str, int] = {}
        self._streamed: dict[str, int] = {}

    @staticmethod
    def _next(counter: dict[str, int], message_id: str) -> str:
        n = counter.get(message_id, 0)
        counter[message_id] = n + 1
        return f"{message_id}:{n}"

    def streamed_id(self, message_id: str) -> str:
        return self._next(self._streamed, message_id)

    def items(
        self, record: dict[str, Any], known: Callable[[str], AssistantMessage | None]
    ) -> list[AssistantMessage]:
        if record["type"] == "user":
            if "prompt" in record:
                return [
                    AssistantMessage(
                        id=str(record.get("uuid") or secrets.token_hex(8)),
                        role="user",
                        kind="userMessage",
                        text=record["prompt"][-ASSISTANT_MAX_TEXT:],
                    )
                ]
            updated = []
            for result in record.get("results", []):
                tool = known(str(result.get("tool_use_id", "")))
                if tool is not None:
                    output = str(result.get("text", ""))
                    text = tool.text + ("\n\n" + output if output else "")
                    status = "failed" if result.get("is_error") else "completed"
                    updated.append(
                        tool.model_copy(
                            update={"text": text[-ASSISTANT_MAX_TEXT:], "status": status}
                        )
                    )
            return updated
        items = []
        for block in record.get("blocks", []):
            if block["type"] == "text":
                items.append(
                    AssistantMessage(
                        id=self._next(self._texts, str(record.get("id", ""))),
                        role="assistant",
                        kind="agentMessage",
                        text=block["text"][-ASSISTANT_MAX_TEXT:],
                    )
                )
            else:
                kind, text = tool_summary(str(block["name"]), block["input"])
                items.append(
                    AssistantMessage(
                        id=str(block["id"]),
                        role="tool",
                        kind=kind,
                        text=text[-ASSISTANT_MAX_TEXT:],
                        status="inProgress",
                    )
                )
        return items


def result_error(value: dict[str, Any]) -> str:
    detail = (str(value.get("result") or "") + " " + json.dumps(value.get("errors") or [])).lower()
    if any(hint in detail for hint in ("login", "log in", "authenticat", "api key", "oauth")):
        return (
            "Claude isn't signed in on this cluster, or its sign-in expired. "
            "Use Sign in on cluster, then reopen the conversation."
        )
    if "limit" in detail:
        return "Claude's usage limit was reached. Try again when it resets."
    return "Claude couldn't finish this turn. Check its setup on the cluster and try again."


@dataclass
class _Run:
    """One conversation's CLI process."""

    process: asyncssh.SSHClientProcess[str]
    model: str | None = None
    effort: str | None = None
    resumed: bool = False  # started with --resume; or a prompt was sent, so it can be
    transcript: Transcript = field(default_factory=Transcript)
    message_id: str = ""
    blocks: dict[int, str] = field(default_factory=dict)  # content index -> streamed item id
    stderr: str = ""
    closing: bool = False
    interrupted: bool = False
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, value: dict[str, Any]) -> None:
        try:
            async with self.write_lock:
                self.process.stdin.write(json.dumps(value) + "\n")
                await self.process.stdin.drain()
        except (asyncssh.Error, OSError) as exc:
            raise SlurmError("Claude's process on the cluster closed. Reopen the chat.") from exc


class ClaudeChat(ChatConnection):
    name = "Claude"

    def __init__(
        self, conn: asyncssh.SSHClientConnection, *, timeout: float, auth: dict[str, Any]
    ) -> None:
        super().__init__()
        self.conn = conn
        self.timeout = timeout
        self.root: str | None = None
        self._runs: dict[str, _Run] = {}
        self._threads: dict[str, AssistantThread] = {}
        self._models: list[AssistantModel] | None = None
        self._apply_auth(auth)

    def _apply_auth(self, auth: dict[str, Any]) -> None:
        root = auth.get("configDirectory")
        if root is not None and (not isinstance(root, str) or not root.startswith("/")):
            raise SlurmError("Claude returned an invalid configuration directory. Check its setup.")
        self.root = root
        self.account.signed_in = bool(auth.get("loggedIn"))
        email = auth.get("email")
        self.account.email = email if isinstance(email, str) and len(email) <= 320 else None

    async def refresh_account(self) -> AssistantConnection:
        self._apply_auth(await claude_auth(self.conn, self.timeout))
        self.changed()
        return self.account

    async def _script(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self.conn.run(
                login_command("python3 -c " + shlex.quote(HISTORY_SCRIPT)),
                input=json.dumps({"root": self.root, **request}),
                check=False,
                timeout=self.timeout,
            )
            if result.exit_status != 0:
                raise ValueError
            value = json.loads(str(result.stdout))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, asyncssh.Error, OSError, TimeoutError) as exc:
            raise SlurmError(
                "Couldn't read Claude conversations. Check Python 3 and Claude Code on the cluster."
            ) from exc

    async def threads(self, cursor: str | None) -> AssistantThreads:
        try:
            return AssistantThreads.model_validate(await self._script({}))
        except ValueError as exc:
            raise SlurmError("Couldn't read Claude's conversation list. Try again.") from exc

    async def history(self, thread_id: str) -> AssistantConversation:
        if not SESSION_ID.fullmatch(thread_id):
            raise SlurmError("That isn't a Claude conversation.")
        value = await self._script({"session": thread_id})
        if value.get("thread") is None:
            started = self._threads.get(thread_id)
            if started is None:
                raise SlurmError("This conversation isn't on the cluster anymore.")
            return AssistantConversation(thread=started, messages=[])  # nothing sent yet
        try:
            thread = AssistantThread.model_validate(value["thread"])
        except ValueError as exc:
            raise SlurmError("Couldn't read this Claude conversation. Try again.") from exc
        transcript = Transcript()
        found: dict[str, AssistantMessage] = {}
        for record in value.get("records", []):
            if isinstance(record, dict) and record.get("type") in {"user", "assistant"}:
                with contextlib.suppress(KeyError, TypeError, AttributeError, ValueError):
                    for item in transcript.items(record, found.get):
                        found.pop(item.id, None)  # a tool's result keeps its call's place
                        found[item.id] = item
        return AssistantConversation(
            thread=thread, messages=list(found.values())[-ASSISTANT_MAX_ITEMS:]
        )

    async def start_thread(self, work_dir: str) -> AssistantThread:
        thread = AssistantThread(
            id=str(uuid.uuid4()),
            title="New conversation",
            work_dir=work_dir,
            updated_at=int(time.time()),
        )
        await self._open(thread, resume=False)
        return thread

    async def resume_thread(self, thread: AssistantThread) -> AssistantThread:
        await self._open(thread, resume=True)
        return thread

    async def models(self) -> list[AssistantModel]:
        """Claude lists its models when it starts; ask a short-lived CLI if no chat
        is open yet. Starting without a prompt makes no request and saves nothing."""
        if self._models is not None:
            return self._models
        try:
            process = await self.conn.create_process(
                login_command("exec " + shlex.join(HEADLESS)), encoding="utf-8", errors="replace"
            )
        except (asyncssh.Error, OSError) as exc:
            raise SlurmError("Couldn't start Claude on the cluster. Check the connection.") from exc
        try:
            process.stdin.write(json.dumps(INITIALIZE) + "\n")
            async with asyncio.timeout(self.timeout):
                while line := await process.stdout.readline():
                    with contextlib.suppress(ValueError):
                        self._remember_models(json.loads(line))
                    if self._models is not None:
                        return self._models
        except (TimeoutError, asyncssh.Error, OSError):
            pass
        finally:
            await finish(process)
        raise SlurmError("Claude didn't list its models. Update Claude Code on the cluster.")

    def _remember_models(self, value: Any) -> None:
        if isinstance(value, dict) and value.get("type") == "control_response":
            response = value.get("response") or {}
            if response.get("request_id") == "pulse-init":
                models = listed_models((response.get("response") or {}).get("models"))
                if models is not None:
                    self._models = models

    async def _open(
        self,
        thread: AssistantThread,
        *,
        resume: bool,
        model: str | None = None,
        effort: str | None = None,
    ) -> None:
        if thread.id in self._runs:
            self.allow(thread.id)
            return
        if len(self._runs) >= ASSISTANT_MAX_SESSIONS:
            idle = next((key for key in self._runs if key not in self.active), None)
            if idle is None:
                raise SlurmError("Stop one of your running Claude chats before opening another.")
            await self._stop(idle)
        try:
            command = chat_command(
                thread.work_dir, thread.id, resume=resume, model=model, effort=effort
            )
            process = await self.conn.create_process(
                login_command(command), encoding="utf-8", errors="replace"
            )
        except (asyncssh.Error, OSError) as exc:
            raise SlurmError("Couldn't start Claude on the cluster. Check the connection.") from exc
        run = _Run(process, model=model, effort=effort, resumed=resume)
        self._runs[thread.id] = run
        self._threads[thread.id] = thread
        run.tasks = [
            asyncio.create_task(self._read(thread.id, run)),
            asyncio.create_task(self._read_stderr(run)),
        ]
        await run.send(INITIALIZE)
        self.error = None
        self.allow(thread.id)
        self.changed()

    async def send_turn(
        self, thread_id: str, prompt: str, model: str | None = None, effort: str | None = None
    ) -> None:
        run = self._runs.get(thread_id)
        if run is None:
            raise SlurmError("This chat closed. Open it again to continue.")
        model = None if model == "default" else model  # Claude's default is no flag
        if (model, effort) != (run.model, run.effort):
            # The thinking level is fixed when Claude starts, so restart this chat's
            # CLI with the new choice; --resume keeps the whole conversation.
            await self._stop(thread_id)
            thread = self._threads[thread_id]
            await self._open(thread, resume=run.resumed, model=model, effort=effort)
            run = self._runs[thread_id]
        run.resumed = True
        item_id = str(uuid.uuid4())  # Claude keeps it, so saved history matches this item
        self._remember(
            thread_id,
            AssistantMessage(id=item_id, role="user", kind="userMessage", text=prompt),
        )
        self.active[thread_id] = item_id
        run.interrupted = False
        self.error = None
        try:
            await run.send(
                {
                    "type": "user",
                    "uuid": item_id,
                    "session_id": "",
                    "parent_tool_use_id": None,
                    "message": {"role": "user", "content": prompt},
                }
            )
        except SlurmError:
            self.active.pop(thread_id, None)
            raise
        finally:
            self.changed()

    async def interrupt(self, thread_id: str) -> bool:
        run = self._runs.get(thread_id)
        if run is None or thread_id not in self.active:
            return False
        run.interrupted = True
        await run.send(
            {
                "type": "control_request",
                "request_id": "pulse-" + secrets.token_hex(8),
                "request": {"subtype": "interrupt"},
            }
        )
        return True

    async def _read_stderr(self, run: _Run) -> None:
        with contextlib.suppress(asyncssh.Error, OSError):
            while chunk := await run.process.stderr.read(4096):
                # Only used to explain a failed start; never forwarded or logged.
                run.stderr = (run.stderr + chunk)[-STDERR_CHARS:]

    async def _read(self, thread_id: str, run: _Run) -> None:
        buffer = ""
        try:
            while chunk := await run.process.stdout.read(8192):
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if len(line.encode()) > ASSISTANT_MAX_RPC_BYTES:
                        raise ValueError
                    if line.strip():
                        value = json.loads(line)
                        if isinstance(value, dict):
                            await self._message(thread_id, run, value)
                if len(buffer.encode()) > ASSISTANT_MAX_RPC_BYTES:
                    raise ValueError
        except SlurmError as exc:
            self.error = str(exc)
        except (ValueError, TypeError, KeyError, AttributeError, asyncssh.Error, OSError):
            self.error = (
                "Claude sent an unreadable response. Update Claude Code and reopen the chat."
            )
        finally:
            if self._runs.get(thread_id) is run:
                del self._runs[thread_id]
            self.active.pop(thread_id, None)
            self._drop_approvals(thread_id)
            self.allowed_threads.discard(thread_id)
            if not run.closing and self.error is None:
                self.error = (
                    result_error({"result": run.stderr})
                    if run.stderr
                    else "Claude stopped on the cluster. Open the chat again to continue."
                )
            if self.conn.is_closed():
                self.connected = False
                self.account.connected = False
            self.changed()

    async def _message(self, thread_id: str, run: _Run, value: dict[str, Any]) -> None:
        self.last_used = time.monotonic()
        kind = value.get("type")
        if kind in {"stream_event", "assistant", "user"} and value.get("parent_tool_use_id"):
            return  # a subagent's internal steps; its final answer arrives as a tool result
        if kind == "stream_event":
            self._delta(thread_id, run, value.get("event") or {})
        elif kind in {"assistant", "user"}:
            record = conversation_record(value)
            if record is not None:
                for item in run.transcript.items(record, lambda key: self._item(thread_id, key)):
                    self._remember(thread_id, item)
        elif kind == "result":
            self.active.pop(thread_id, None)
            self._drop_approvals(thread_id)
            failed = value.get("is_error") or value.get("subtype") != "success"
            self.error = result_error(value) if failed and not run.interrupted else None
        elif kind == "control_request":
            await self._control(thread_id, run, value)
        elif kind == "control_response":
            self._remember_models(value)
            return
        elif kind == "control_cancel_request":
            for key in [
                key
                for key, pending in self.approvals.items()
                if pending.rpc_id == value.get("request_id")
            ]:
                del self.approvals[key]
        else:
            return
        self.changed()

    def _delta(self, thread_id: str, run: _Run, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "message_start":
            run.message_id = str((event.get("message") or {}).get("id", ""))
            run.blocks.clear()
        elif kind == "content_block_start":
            if (event.get("content_block") or {}).get("type") == "text":
                run.blocks[int(event.get("index", 0))] = run.transcript.streamed_id(run.message_id)
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            item_id = run.blocks.get(int(event.get("index", 0)))
            if item_id is None or delta.get("type") != "text_delta":
                return
            item = self._item(thread_id, item_id) or AssistantMessage(
                id=item_id, role="assistant", kind="agentMessage", text=""
            )
            text = (item.text + str(delta.get("text", "")))[-ASSISTANT_MAX_TEXT:]
            self._remember(thread_id, item.model_copy(update={"text": text}))

    async def _control(self, thread_id: str, run: _Run, value: dict[str, Any]) -> None:
        request = value.get("request") or {}
        request_id = str(value.get("request_id", ""))
        tool_input = request.get("input")
        if (
            request.get("subtype") != "can_use_tool"
            or not isinstance(tool_input, dict)
            or thread_id not in self.allowed_threads
            or len(self.approvals) >= ASSISTANT_MAX_PENDING
        ):
            await run.send(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "error",
                        "request_id": request_id,
                        "error": "This request isn't supported by Pulse.",
                    },
                }
            )
            return
        name = str(request.get("tool_name", ""))
        questions: list[dict[str, Any]] = []
        if name == "AskUserQuestion":
            kind, title, detail = "question", "Claude needs your answer", ""
            questions = [
                {
                    "id": str(index),
                    "question": str(question.get("question", "")),
                    "options": [
                        {
                            "label": str(option.get("label", "")),
                            "description": str(option.get("description", "")),
                        }
                        for option in question.get("options", [])[:20]
                        if isinstance(option, dict)
                    ],
                }
                for index, question in enumerate(tool_input.get("questions", [])[:10])
                if isinstance(question, dict)
            ]
        elif name == "ExitPlanMode":
            kind, title, detail = "plan", "Approve this plan?", str(tool_input.get("plan", ""))
        else:
            summary_kind, detail = tool_summary(name, tool_input)
            kind, title = {
                "commandExecution": ("command", "Run this command?"),
                "fileChange": ("files", "Apply these file changes?"),
            }.get(summary_kind, ("tool", f"Allow {request.get('display_name') or name}?"))
            if kind == "command" and request.get("description"):
                detail = f"# {request['description']}\n{detail}"
        key = secrets.token_urlsafe(16)
        item = AssistantApproval(
            id=key,
            thread_id=thread_id,
            kind=kind,
            title=title,
            detail=detail[-ASSISTANT_MAX_TEXT:],
            questions=questions,
        )
        self.approvals[key] = PendingApproval(
            request_id, name, item, time.monotonic() + APPROVAL_SECONDS, tool_input
        )

    async def decide(self, key: str, accept: bool, answers: dict[str, list[str]]) -> str:
        pending = self.approvals.pop(key, None)
        if pending is None:
            raise SlurmError("That request is no longer waiting for a response.")
        thread_id = pending.item.thread_id
        run = self._runs.get(thread_id)
        if run is None:
            raise SlurmError("This chat closed. Open it again to continue.")
        if pending.expires <= time.monotonic():
            accept = False
        response: dict[str, Any] = {"behavior": "deny", "message": DECLINED}
        if accept:
            updated = dict(pending.payload)
            if pending.item.kind == "question":
                updated["answers"] = {
                    str(q["question"]): ", ".join(answers.get(str(q["id"]), []))
                    for q in pending.item.questions
                }
            response = {"behavior": "allow", "updatedInput": updated}
        await run.send(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": pending.rpc_id,
                    "response": response,
                },
            }
        )
        self.changed()
        return thread_id

    async def _stop(self, thread_id: str) -> None:
        run = self._runs.pop(thread_id, None)
        if run is None:
            return
        run.closing = True
        await finish(run.process)
        for task in run.tasks:
            task.cancel()
        await asyncio.gather(*run.tasks, return_exceptions=True)

    async def close(self) -> None:
        for thread_id in list(self._runs):
            await self._stop(thread_id)
        self.connected = False
        self.account.connected = False
        self.changed()


async def finish(process: asyncssh.SSHClientProcess[str]) -> None:
    """End a CLI the way a terminal would: close its input so it exits on its own,
    and only cut the channel if it doesn't within a few seconds."""
    with contextlib.suppress(TimeoutError, asyncssh.Error, OSError):
        process.stdin.write_eof()
        await asyncio.wait_for(process.wait_closed(), 3)
    process.close()


async def claude_auth(conn: asyncssh.SSHClientConnection, seconds: float) -> dict[str, Any]:
    """``claude auth status``: public metadata (sign-in method, config directory), never tokens."""
    status = await conn.run(login_command("claude auth status"), check=False, timeout=seconds)
    try:
        value = json.loads(str(status.stdout or "{}"))
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise SlurmError(
            "Claude returned unreadable account details. Update Claude Code and retry."
        )
    return value
