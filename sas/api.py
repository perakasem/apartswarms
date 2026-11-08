"""Provider-neutral pieces shared by the OpenRouter client (sas/openrouter.py):
error types, the spend ledger and the per-model rate gate.

Rate gate: paces calls per model (rps, max in flight) and keeps a window of
recent outcomes. HTTP 429 retries only the rejected call after a short
jittered wait (sas/openrouter.py); the model stops only when rate limiting is
sustained: more than `saturation` of its last `window` attempts were 429.
The key lives only in memory and is redacted from any stored error text
(sas/openrouter.py).
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


class APIError(RuntimeError):
    pass


class TransientAPIError(APIError):
    """Retries exhausted on 5xx / timeout / connection errors. Safe to resume."""


class KeysExhausted(APIError):
    """Every API key is retired (balance below threshold, 402 or 401). Resumable."""


class ReasoningControlError(APIError):
    """The response did not confirm reasoning was disabled."""


class BudgetExceeded(APIError):
    pass


def ledger_total(path: Path | None) -> float:
    if not path or not Path(path).exists():
        return 0.0
    total = 0.0
    for line in Path(path).read_text().splitlines():
        try:
            total += float(json.loads(line)["credits"])
        except (ValueError, KeyError, TypeError):
            continue   # a line torn by a kill mid-write; the entry is lost, not the ledger
    return total


class RateLimited(APIError):
    """Sustained HTTP 429 on one model (see RateGate.saturated). Resumable."""


@dataclass
class RateGate:
    """Per-model pacing. `max_inflight` is the normal in-flight limit; with
    `floor` set below it, the limit falls back to `floor` while more than
    `degrade_at` of the last `health_window` attempts were 429s or provider
    errors (5xx, timeouts), and returns to `max_inflight` once that share is
    at most `restore_at`. Separately, `rate_limited()` reports sustained 429
    (over `saturation` of the last `window` attempts), which stops the model."""
    rps: float = 4.0
    max_inflight: int = 4
    floor: int | None = None
    window: int = 50
    saturation: float = 0.5
    health_window: int = 50
    degrade_at: float = 0.10
    restore_at: float = 0.02
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _cond: threading.Condition | None = None
    _next: float = 0.0
    _recent: deque = field(default_factory=deque)
    _health: deque = field(default_factory=deque)
    inflight: int = 0
    limit: int = 0
    rate_limits: int = 0                      # 429s seen this invocation
    fallbacks: int = 0                        # times the limit fell back to `floor`

    def __post_init__(self):
        self._cond = threading.Condition(self._lock)
        self._recent = deque(maxlen=self.window)
        self._health = deque(maxlen=self.health_window)
        self.limit = self.max_inflight

    def acquire(self):
        with self._cond:
            while self.inflight >= self.limit:
                self._cond.wait()
            self.inflight += 1
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + 1.0 / self.rps
        time.sleep(max(0.0, start - time.monotonic()))

    def release(self):
        with self._cond:
            self.inflight -= 1
            self._cond.notify_all()

    def _health_update(self, error: bool):
        """Caller holds the lock."""
        self._health.append(error)
        if self.floor is None or self.floor >= self.max_inflight or len(self._health) < self.health_window // 2:
            return
        frac = sum(self._health) / len(self._health)
        if self.limit > self.floor and frac > self.degrade_at:
            self.limit = self.floor
            self.fallbacks += 1
        elif self.limit < self.max_inflight and frac <= self.restore_at and len(self._health) == self.health_window:
            self.limit = self.max_inflight
            self._cond.notify_all()

    def ok(self):
        with self._lock:
            self._recent.append(False)
            self._health_update(False)

    def provider_error(self):
        """A 5xx / timeout / transport failure (not a 429)."""
        with self._lock:
            self._health_update(True)

    def rate_limited(self) -> bool:
        """Record a 429; True if rate limiting is now sustained (stop the model)."""
        with self._lock:
            self.rate_limits += 1
            self._recent.append(True)
            self._health_update(True)
            return (len(self._recent) >= self.window
                    and sum(self._recent) / len(self._recent) > self.saturation)
