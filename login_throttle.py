"""In-memory sign-in throttle for the shared dashboard account.

The dashboard form and the legacy REST endpoint accept one configured
ID/password pair. This module slows repeated failures per
(client address, account) without adding a database: state lives in process
memory and resets on restart, which is acceptable because the lockouts are
short and only guard guessing speed.
"""
import threading
import time


class LoginThrottle:
    def __init__(
        self,
        free_attempts=5,
        base_delay=10,
        max_delay=300,
        window=900,
        max_entries=1000,
        clock=time.monotonic,
    ):
        self.free_attempts = free_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.window = window
        self.max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        # key -> {"failures": int, "last": float, "locked_until": float}
        self._entries = {}

    def retry_after(self, key):
        """Return the whole seconds the caller must wait before another attempt, or 0."""
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return 0
            if now - entry["last"] > self.window:
                del self._entries[key]
                return 0
            remaining = entry["locked_until"] - now
            if remaining <= 0:
                return 0
            return int(remaining) + (0 if remaining == int(remaining) else 1)

    def record_failure(self, key):
        """Count a failed attempt and return the lock now in effect (0 while attempts are still free)."""
        now = self._clock()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(key)
            if entry is None or now - entry["last"] > self.window:
                entry = {"failures": 0, "last": now, "locked_until": 0.0}
                self._entries[key] = entry
            entry["failures"] += 1
            entry["last"] = now
            excess = entry["failures"] - self.free_attempts
            if excess <= 0:
                return 0
            delay = min(self.max_delay, self.base_delay * (2 ** (excess - 1)))
            entry["locked_until"] = now + delay
            return delay

    def record_success(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def _prune(self, now):
        stale = [key for key, entry in self._entries.items() if now - entry["last"] > self.window]
        for key in stale:
            del self._entries[key]
        overflow = len(self._entries) - self.max_entries + 1
        if overflow > 0:
            # A flood of distinct keys must not grow memory without bound; drop the oldest first.
            oldest = sorted(self._entries.items(), key=lambda item: item[1]["last"])[:overflow]
            for key, _ in oldest:
                del self._entries[key]
