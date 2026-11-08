"""Offline stand-in for the OpenRouter client. It reads the *rendered prompt*
(so the prompt/parse path is exercised end to end) and answers like a noisy
scoreboard learner. Occasionally returns malformed output to exercise the
re-ask/fallback path.

FlakyFakeClient (model name "fake-flaky") additionally fails like a gateway
504 storm: its first `fail_calls` calls in a process succeed, then the next
`outage` calls raise TransientAPIError, then it recovers. Replies are a pure
function of the prompt, so an interrupted-and-resumed run must equal an
uninterrupted one exactly."""

from __future__ import annotations

import json
import re
import zlib

import numpy as np

_ROW = re.compile(r"^(\d+) \| (\S+)(?: \(auto-assigned\))? \| ([^|\n]+?)(?: \| ([+-][\d.]+))?$", re.M)
# Qualitative framing hides points; the fake scores outcomes the same way.
_QUAL_POINTS = {"objected": -5.0, "completed": 10.0}
_AVAIL = re.compile(r"^Available workers: (.+)$", re.M)


class FakeClient:
    def __init__(self, lam: float = 0.5, malformed_rate: float = 0.02, preamble_rate: float = 0.1):
        self.lam, self.malformed_rate, self.preamble_rate = lam, malformed_rate, preamble_rate
        self.spent = 0.0

    def respond(self, *, model: str, instructions: str, input: str,
                max_output_tokens: int = 512, temperature: float | None = None,
                on_attempt=None) -> dict:
        rng = np.random.default_rng(zlib.crc32(input.encode()))
        avail = _AVAIL.search(input).group(1).split(", ")
        tot = {a: 0.0 for a in avail}
        cnt = {a: 0 for a in avail}
        for _, lab, result, pts in _ROW.findall(input):
            tot[lab] += float(pts) if pts else _QUAL_POINTS.get(result.strip(), -30.0)
            cnt[lab] += 1
        est = np.array([(tot[a] + 10.0) / (cnt[a] + 1) for a in avail])
        p = np.exp(self.lam * (est - est.max()))
        p /= p.sum()
        choice = avail[int(rng.choice(len(avail), p=p))]
        if "could not be used" not in input and rng.random() < self.malformed_rate:
            text = "I think the best choice is probably the second worker."
        else:
            text = json.dumps({"assign": choice, "notes": f"tried {sum(cnt.values())} rounds"})
            if rng.random() < self.preamble_rate:   # some models reason in text first
                text = "Looking at the history, I will pick a worker with good results.\n" + text
        n_in = len(input) // 4
        if on_attempt is not None:   # same record shape as the real client
            on_attempt({"attempt": 1, "status": 200, "latency_s": 0.0,
                        "request": {"model": model, "instructions": instructions, "input": input,
                                    "max_output_tokens": max_output_tokens, "temperature": temperature,
                                    "store": False, "agentic_memory": False, "background": False},
                        "response": {"model": model, "output_text": text},
                        "usage": {"input_tokens": n_in, "output_tokens": 20}, "served_model": model})
        return {"text": text, "usage": {"input": n_in, "output": 20, "reasoning": 0},
                "latency_s": 0.0, "credits": 0.0, "attempts": 1, "status": "completed",
                "served_model": model}


class FlakyFakeClient(FakeClient):
    def __init__(self, fail_calls: int = 25, outage: int = 3, **kw):
        super().__init__(**kw)
        self.fail_calls, self.outage, self.calls = fail_calls, outage, 0
        import threading
        self._lock = threading.Lock()

    def respond(self, **kw) -> dict:
        from ..api import TransientAPIError
        with self._lock:
            self.calls += 1
            n = self.calls
        if self.fail_calls < n <= self.fail_calls + self.outage:
            if kw.get("on_attempt") is not None:
                kw["on_attempt"]({"attempt": 1, "status": 504, "latency_s": 60.0,
                                  "request": {"model": kw["model"]}, "response": {"body": "gateway timeout"},
                                  "usage": None, "served_model": None})
            raise TransientAPIError("simulated HTTP 504 (gateway timeout)")
        return super().respond(**kw)


class BrokeFakeClient(FakeClient):
    """Model name "fake-broke": every key runs dry after `ok_calls` calls
    (rehearses KeysExhausted -> clean stop, exit code 2)."""
    def __init__(self, ok_calls: int = 10, **kw):
        super().__init__(**kw)
        self.ok_calls, self.calls = ok_calls, 0

    def respond(self, **kw) -> dict:
        from ..api import KeysExhausted
        self.calls += 1
        if self.calls > self.ok_calls:
            raise KeysExhausted("all OpenRouter keys retired: k1: HTTP 402; k2: HTTP 402; k3: HTTP 402")
        return super().respond(**kw)


class RateLimitedFakeClient(FakeClient):
    """Model name "fake-ratelimited": sustained 429 after `ok_calls` calls
    (rehearses per-model containment: this model stops, others continue)."""
    def __init__(self, ok_calls: int = 10, **kw):
        super().__init__(**kw)
        self.ok_calls, self.calls = ok_calls, 0
        import threading
        self._lock = threading.Lock()

    def respond(self, **kw) -> dict:
        from ..api import RateLimited
        with self._lock:
            self.calls += 1
            n = self.calls
        if n > self.ok_calls:
            raise RateLimited(f"sustained rate limiting on {kw['model']}: simulated")
        return super().respond(**kw)
