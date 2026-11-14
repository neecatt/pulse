"""Claude Code's own sign-in (`claude auth login`), run on the cluster for the user.

The CLI owns the OAuth exchange and token storage. Pulse only relays its official
authorization link and, if asked, the one-time code; it never sees tokens.
"""

import asyncio
import contextlib
import re
import secrets
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


def provider_url(value: str) -> str | None:
    """Only HTTPS links to Anthropic's own sign-in hosts are shown to the user."""
    try:
        parsed = urlsplit(value.rstrip(".,);"))
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        return None
    return parsed.geturl() if parsed.hostname in AUTH_HOSTS else None


@contextlib.asynccontextmanager
async def claude_errors() -> AsyncIterator[None]:
    try:
        yield
    except (asyncssh.Error, OSError, TimeoutError) as exc:
        raise SlurmError(
            "Couldn't reach Claude Code on the cluster. Check the SSH connection and retry."
        ) from exc


class ClaudeSession:
    def __init__(self, process: asyncssh.SSHClientProcess[str]) -> None:
        self.process = process
        self.connected = True
        self.authorized_logins: set[str] = set()
        self.last_used = time.monotonic()
        self.state = ClaudeState(connection_id=secrets.token_hex(16), phase="sign_in", running=True)
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
                tail = (tail + chunk)[-16384:]
                self.state.setup_text = ANSI.sub("", tail).replace("\r", "\n")[-8000:]
                for match in URL.finditer(tail):
                    if match.end() == len(tail):
                        continue  # wait for a delimiter instead of forwarding a partial URL
                    if url := provider_url(match.group()):
                        self.state.login_url = url
                self.changed()
        except (asyncssh.Error, OSError, ValueError):
            self.state.error = "Claude's SSH connection closed. Try signing in again."
        finally:
            self.connected = False
            self.state.running = False
            if self.process.exit_status == 0:
                self.state.phase = "authorized"
                self.state.setup_text = ""
                self.state.login_url = None
            elif self.state.phase != "closed":
                self.state.phase = "error"
                self.state.error = self.state.error or (
                    "Claude's sign-in didn't finish. Check its message, then try again."
                )
            self.changed()

    async def input(self, action: str, code: str) -> None:
        if not self.connected:
            return
        if action == "code":
            if not self.state.login_url:
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
            raise ValueError("Close another Claude sign-in screen and retry.")
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
