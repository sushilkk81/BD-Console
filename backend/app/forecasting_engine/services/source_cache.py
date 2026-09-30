"""A small bounded TTL cache for upstream source searches.

Scope, stated plainly: this is per-process. With several uvicorn workers each holds
its own copy, so it reduces upstream load and latency but is not a shared cache and is
never treated as one.

Forecast RESULTS are deliberately not cached. Two logistic scenarios are twenty
`expit` evaluations; adding shared infrastructure to memoize that would cost more than
it saves and would introduce a staleness problem where none exists today.
"""
from __future__ import annotations

import threading
import time
from typing import Any

#: Evidence datasets update on the order of months; a few minutes of reuse is plenty
#: to collapse repeated searches within one review session.
DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MAX_ENTRIES = 256


class TTLCache:
    """Thread-safe, size-bounded, FIFO-evicting cache."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 max_entries: int = DEFAULT_MAX_ENTRIES):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            if len(self._entries) >= self._max_entries:
                # Oldest insertion first; dicts preserve insertion order.
                self._entries.pop(next(iter(self._entries)), None)
            self._entries[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


#: Module-level instance used by the router. Keyed by the full query so two different
#: searches can never collide.
SOURCE_SEARCH_CACHE = TTLCache()
