"""Run unmodified Claude Code and hand off to its official Remote Control UI."""

import asyncio
import contextlib
import re
import secrets
import shlex
import time
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import asyncssh

from pulse.schemas import ClaudeState
from pulse.slurm.base import SlurmError

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
URL = re.compile(r"https://[^\s\x00-\x20\x7f\x1b<>\"']+")
AUTH_HOSTS = {"claude.ai", "console.anthropic.com", "platform.claude.com"}
HISTORY_SCRIPT = (Path(__file__).parents[1] / "assistants" / "claude_history.py").read_text()


def provider_url(value: str, *, remote: bool) -> str | None:
    try:
        parsed = urlsplit(value.rstrip(".,);"))
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        return None
    if remote:
        if (
            parsed.hostname != "claude.ai"
            or not parsed.path.startswith("/code/")
            or parsed.path == "/code/"
        ):
            return None
    elif parsed.hostname not in AUTH_HOSTS:
        return None
    return parsed.geturl()


@contextlib.asynccontextmanager
async def claude_errors() -> AsyncIterator[None]:
    try:
        yield
    except (asyncssh.Error, OSError, TimeoutError) as exc:
        raise SlurmError(
            "Couldn't reach Claude Code on the cluster. Check the SSH connection and retry."
        ) from exc


def remote_command(work_dir: str, session_id: str | None, instructions: str = "") -> str:
    argv = ["claude", "--remote-control", "--permission-mode", "manual"]
    if session_id:
        argv += ["--resume", session_id]
    if instructions:
        argv += ["--append-system-prompt", instructions]
    # No prompt is sent by Pulse. Chat and approvals stay in Claude's own UI.
    return "cd -- " + shlex.quote(work_dir) + " && exec " + shlex.join(argv)


class ClaudeSession:
    def __init__(
        self,
        process: asyncssh.SSHClientProcess[str],
        *,
        login: bool,
        work_dir: str = "",
        session_id: str | None = None,
    ) -> None:
        self.process = process
        self.is_login = login
        self.connected = True
        self.authorized_logins: set[str] = set()
        self.last_used = time.monotonic()
        self.state = ClaudeState(
            connection_id=secrets.token_hex(16),
            phase="sign_in" if login else "starting",
            running=True,
            work_dir=work_dir,
            session_id=session_id,
        )
        self._subscribers: set[asyncio.Queue[None]] = set()
        self._task = asyncio.create_task(self._read())

    def changed(self) -> None:
        for queue in self._subscribers:
            if queue.empty():
                queue.put_nowait(None)

    async def _read(self) -> None:
        tail = ""
        try:
            while chunk := await self.process.stdout.read(4096):
                self.last_used = time.monotonic()
                if self.state.phase == "ready":
                    continue  # drain tool activity without retaining a second transcript
                tail = (tail + chunk)[-16384:]
                clean = ANSI.sub("", tail).replace("\r", "\n")
                self.state.setup_text = clean[-8000:]
                for match in URL.finditer(tail):
                    if match.end() == len(tail):
                        continue  # wait for a delimiter instead of forwarding a partial URL
                    url = provider_url(match.group(), remote=not self.is_login)
                    if url:
                        if self.is_login:
                            self.state.login_url = url
                        else:
                            self.state.remote_url = url
                            self.state.phase = "ready"
                            self.state.setup_text = ""
                self.changed()
        except (asyncssh.Error, OSError, ValueError):
            self.state.error = "Claude's SSH connection closed. Reconnect to continue."
        finally:
            self.connected = False
            self.state.running = False
            if self.is_login and self.process.exit_status == 0:
                self.state.phase = "authorized"
                self.state.setup_text = ""
                self.state.login_url = None
            elif self.state.phase != "closed":
                self.state.phase = "error"
                hint = self.state.setup_text.lower()
                if "logged in" in hint or "subscription auth" in hint:
                    self.state.error = (
                        "Sign in on this cluster with an eligible Claude subscription, "
                        "then connect again."
                    )
                elif "policy" in hint or "not enabled" in hint:
                    self.state.error = (
                        "Remote Control isn't enabled for this Claude account. "
                        "Ask your organization owner to enable it."
                    )
                elif "unknown option" in hint or "unknown command" in hint:
                    self.state.error = (
                        "Update Claude Code on this cluster to use Remote Control, then reconnect."
                    )
                self.state.error = self.state.error or (
                    "Claude stopped before it could connect. Check its setup message, "
                    "subscription access and cluster connection, then retry."
                )
            self.changed()

    async def input(self, action: str, code: str) -> None:
        if not self.connected or self.state.phase == "ready":
            return
        if action == "code":
            if not self.is_login or not self.state.login_url:
                raise ValueError("Start Claude sign-in before entering its one-time code.")
            if not code.strip():
                raise ValueError("Enter the one-time code from Claude first.")
            value = code.strip() + "\n"
        else:
            value = {
                "enter": "\r",
                "yes": "y\r",
                "up": "\x1b[A",
                "down": "\x1b[B",
                "cancel": "\x03",
            }[action]
        self.process.stdin.write(value)
        await self.process.stdin.drain()
        self.last_used = time.monotonic()

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[None]]:
        if len(self._subscribers) >= 4:
            raise ValueError("Close another Claude setup screen and retry.")
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def close(self) -> None:
        self.state.phase = "closed"
        self.process.close()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        with contextlib.suppress(TimeoutError, asyncssh.Error, OSError):
            await asyncio.wait_for(self.process.wait_closed(), 5)
        self.connected = False
        self.state.running = False
        self.changed()
