"""In-memory limits on repeated attempts (failed logins, sign-ups), per key such as
a client address or a username."""

import time
from collections import deque

from pulse.constants import RATE_LIMIT_MAX_KEYS


class LoginRateLimiter:
    def __init__(
        self, max_failures: int, window_seconds: int, max_keys: int = RATE_LIMIT_MAX_KEYS
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._max_keys = max_keys
        self._failures: dict[str, deque[float]] = {}

    def blocked(self, *keys: str) -> bool:
        return any(len(self._recent(key)) >= self._max for key in keys)

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        for key in keys:
            self._failures.setdefault(key, deque()).append(now)
        if len(self._failures) > self._max_keys:
            self._evict()

    def reset(self, *keys: str) -> None:
        for key in keys:
            self._failures.pop(key, None)

    def _recent(self, key: str) -> deque[float]:
        """Attempts still inside the window. Looking a key up never stores it, so
        probing random usernames costs no memory."""
        window = self._failures.get(key)
        if window is None:
            return deque()
        cutoff = time.monotonic() - self._window
        while window and window[0] < cutoff:
            window.popleft()
        if not window:
            del self._failures[key]
        return window

    def _evict(self) -> None:
        """Bound memory: drop expired keys, then the oldest ones if still too many."""
        for key in list(self._failures):
            self._recent(key)
        excess = len(self._failures) - self._max_keys
        for key in list(self._failures)[: max(excess, 0)]:
            del self._failures[key]
