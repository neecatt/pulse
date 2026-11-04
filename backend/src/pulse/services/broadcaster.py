"""In-process fan-out of live updates to connected browsers (Server-Sent Events)."""

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pulse.constants import STREAM_QUEUE_SIZE


class Broadcaster:
    def __init__(self) -> None:
        self._queues: dict[int, set[asyncio.Queue[str]]] = defaultdict(set)

    @property
    def has_subscribers(self) -> bool:
        return any(self._queues.values())

    def has_subscribers_for(self, user_id: int) -> bool:
        return bool(self._queues.get(user_id))

    @asynccontextmanager
    async def subscribe(self, user_id: int) -> AsyncIterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(STREAM_QUEUE_SIZE)
        self._queues[user_id].add(queue)
        try:
            yield queue
        finally:
            self._queues[user_id].discard(queue)

    def publish(self, user_id: int, message: dict[str, Any]) -> None:
        data = json.dumps(message)
        for queue in self._queues.get(user_id, ()):
            # A slow client misses an update rather than stalling the poller; the
            # next update makes it refetch anyway.
            if not queue.full():
                queue.put_nowait(data)
