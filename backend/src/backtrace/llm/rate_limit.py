"""Thread-safe per-minute call-rate limiter (§11 Day 3 open item).
max_concurrent_calls only bounds how many calls run at once, not how many
land per minute — a worker at concurrency 4 hit the Free Tier's 15 req/min
cap in ~14 seconds on 2026-10-03/04, and a sequential script with no pacing
hit the same cap on 2026-10-04. This bounds calls per rolling window instead."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """At most `max_calls` calls in any rolling `window_seconds` window.
    acquire() blocks the calling thread until a slot is free."""

    def __init__(self, max_calls: int, window_seconds: float = 60.0, clock=time.monotonic, sleep=time.sleep) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        self._max_calls = max_calls
        self._window = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                while self._timestamps and now - self._timestamps[0] >= self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max_calls:
                    self._timestamps.append(now)
                    return
                wait = self._window - (now - self._timestamps[0])
            self._sleep(max(wait, 0.01))
