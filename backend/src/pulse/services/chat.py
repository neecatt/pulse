"""What every cluster assistant chat shares: live items, approvals and subscribers.

Providers (Codex's app-server, Claude Code's stream-json mode) translate their own
protocol into these normalized messages, so the API and the UI stay provider-neutral.
"""

import asyncio
import contextlib
import shlex
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from pulse.constants import (
    ASSISTANT_MAX_ITEMS,
    ASSISTANT_MAX_SESSIONS,
    ASSISTANT_MAX_STATE_CHARS,
)
from pulse.schemas import (
    AssistantApproval,
    AssistantConnection,
    AssistantConversation,
    AssistantLive,
    AssistantMessage,
    AssistantModel,
    AssistantThread,
    AssistantThreads,
)
from pulse.slurm.base import SlurmError

TRAINING_INSTRUCTIONS = (
    "You are running on an HPC login node through Pulse. Use Slurm for training "
    "and heavy computation, never run training directly on the login node. "
    "Read the project's instructions and inspect available partitions first. "
    "Show the batch script and resource request and ask the user before submitting, "
    "cancelling or modifying a job. Report the Slurm job ID after submission."
)
APPROVAL_SECONDS = 600


def login_command(command: str) -> str:
    return "bash -lc " + shlex.quote(command)


@dataclass
class PendingApproval:
    rpc_id: str | int
    method: str
    item: AssistantApproval
    expires: float
    # The provider's original request, for answers that must echo it back.
    payload: dict[str, Any] = field(default_factory=dict)


class ChatConnection:
    name = "The assistant"

    def __init__(self) -> None:
        self.connected = True
        self.account = AssistantConnection(connected=True, signed_in=False)
        self.approvals: dict[str, PendingApproval] = {}
        # thread -> item -> (revision it last changed in, item), so streams send only changes
        self.messages: OrderedDict[str, OrderedDict[str, tuple[int, AssistantMessage]]] = (
            OrderedDict()
        )
        self.active: dict[str, str] = {}
        self.allowed_threads: set[str] = set()  # only explicitly opened conversations can act
        self.authorized_logins: set[str] = set()
        self.error: str | None = None
        self.revision = 0
        self.last_used = time.monotonic()
        self.action_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[None]] = set()

    def changed(self) -> None:
        self.revision += 1
        for queue in self._subscribers:
            if queue.empty():
                queue.put_nowait(None)

    def _item(self, thread_id: str, item_id: str) -> AssistantMessage | None:
        stored = self.messages.get(thread_id, OrderedDict()).get(item_id)
        return stored[1] if stored else None

    def _remember(self, thread_id: str, item: AssistantMessage) -> None:
        if not thread_id:
            return
        items = self.messages.setdefault(thread_id, OrderedDict())
        items[item.id] = (self.revision + 1, item)  # changed() bumps revision to match
        while len(items) > ASSISTANT_MAX_ITEMS:
            items.popitem(last=False)
        self.messages.move_to_end(thread_id)
        while len(self.messages) > ASSISTANT_MAX_SESSIONS:
            self.messages.popitem(last=False)
        while (
            sum(len(item.text) for items in self.messages.values() for _, item in items.values())
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

    def _drop_approvals(self, thread_id: str) -> None:
        for key in [k for k, p in self.approvals.items() if p.item.thread_id == thread_id]:
            del self.approvals[key]

    async def expire_approvals(self) -> None:
        for key in [
            key for key, pending in self.approvals.items() if pending.expires <= time.monotonic()
        ]:
            await self.decide(key, False, {})

    def snapshot(self, since: int | None = None) -> AssistantLive:
        """Everything, or with ``since`` only the items changed after that revision."""
        messages = {
            key: [item for revision, item in items.values() if since is None or revision > since]
            for key, items in self.messages.items()
        }
        return AssistantLive(
            connection=self.account,
            messages={key: items for key, items in messages.items() if items or since is None},
            partial=since is not None,
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

    # Provider operations.

    async def refresh_account(self) -> AssistantConnection:
        raise NotImplementedError

    async def threads(self, cursor: str | None) -> AssistantThreads:
        raise NotImplementedError

    async def history(self, thread_id: str) -> AssistantConversation:
        raise NotImplementedError

    async def start_thread(self, work_dir: str) -> AssistantThread:
        raise NotImplementedError

    async def resume_thread(self, thread: AssistantThread) -> AssistantThread:
        raise NotImplementedError

    async def models(self) -> list[AssistantModel]:
        """The models this cluster's CLI offers, with their thinking levels."""
        raise NotImplementedError

    async def check_choice(self, model: str | None, effort: str | None) -> None:
        """Only models and thinking levels the CLI itself offers reach it."""
        if model is None and effort is None:
            return
        models = await self.models()
        chosen = next((m for m in models if m.id == model), None)
        if model is not None and chosen is None:
            raise SlurmError(f"{self.name} doesn't offer that model on this cluster.")
        levels = chosen.efforts if chosen else {e for m in models for e in m.efforts}
        if effort is not None and effort not in levels:
            raise SlurmError("That thinking level isn't available for this model.")

    async def send_turn(
        self, thread_id: str, prompt: str, model: str | None = None, effort: str | None = None
    ) -> None:
        raise NotImplementedError

    async def interrupt(self, thread_id: str) -> bool:
        """Stop the running turn; False if nothing was running."""
        raise NotImplementedError

    async def decide(self, key: str, accept: bool, answers: dict[str, list[str]]) -> str:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError
