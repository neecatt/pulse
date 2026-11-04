"""In-memory limit on failed logins, per client address and per username."""

import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def blocked(self, *keys: str) -> bool:
        return any(len(self._recent(key)) >= self._max for key in keys)

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        for key in keys:
            self._recent(key).append(now)

    def reset(self, *keys: str) -> None:
        for key in keys:
            self._failures.pop(key, None)

    def _recent(self, key: str) -> deque[float]:
        window = self._failures[key]
        cutoff = time.monotonic() - self._window
        while window and window[0] < cutoff:
            window.popleft()
        return window
