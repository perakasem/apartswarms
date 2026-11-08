"""LLM coordinator: stateless per call; history comes from the harness log."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..env import Cell, Decision, Observation
from ..prompts import NOTES_MAX_CHARS, REASK, round_prompt, system_prompt
from ..tapes import Tapes

_JSON = re.compile(r"\{.*\}", re.S)


def parse_reply(text: str, available: list[str]) -> tuple[str, str] | None:
    """Return (label, notes) or None. Tolerates code fences and surrounding text,
    and case/whitespace differences in the worker name."""
    m = _JSON.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    label = str(obj.get("assign", "")).strip()
    canon = {a.upper(): a for a in available}
    if label.upper() not in canon:
        return None
    notes = obj.get("notes", "")
    notes = notes if isinstance(notes, str) else json.dumps(notes)
    return canon[label.upper()], notes[:NOTES_MAX_CHARS]


class LLMCoordinator:
    def __init__(self, client, model: str, *, max_output_tokens: int = 512,
                 temperature: float | None = None, max_reasks: int = 2):
        self.client, self.model = client, model
        self.max_output_tokens, self.temperature = max_output_tokens, temperature
        self.max_reasks = max_reasks
        self.name = model
        self.attempt_log: Path | None = None

    def set_attempt_log(self, path: Path) -> None:
        """Append-only log of every API attempt for this run (CLAUDE.md invariant 6)."""
        self.attempt_log = path

    def reset(self, cell: Cell, tapes: Tapes, T: int) -> None:
        self.instructions = system_prompt(cell, T)
        self.framing = cell.framing
        self.tapes = tapes

    def _call(self, text: str, round_: int, call: int) -> dict:
        def log(rec):
            if self.attempt_log is not None:
                with open(self.attempt_log, "a") as f:
                    f.write(json.dumps({"round": round_, "call": call, **rec}, default=str) + "\n")
        return self.client.respond(model=self.model, instructions=self.instructions, input=text,
                                   max_output_tokens=self.max_output_tokens,
                                   temperature=self.temperature, on_attempt=log)

    def choose(self, obs: Observation) -> Decision:
        prompt = round_prompt(obs, self.framing)
        calls = [self._call(prompt, obs.round, 0)]
        parsed = parse_reply(calls[-1]["text"], obs.available)
        while parsed is None and len(calls) <= self.max_reasks:   # re-ask (DEVIATIONS B12)
            calls.append(self._call(prompt + "\n\n" + REASK, obs.round, len(calls)))
            parsed = parse_reply(calls[-1]["text"], obs.available)
        meta = {"calls": len(calls),
                "raw": [c["text"] for c in calls],
                "served_model": sorted({str(c.get("served_model")) for c in calls}),
                "in_tokens": sum(c["usage"]["input"] for c in calls),
                "out_tokens": sum(c["usage"]["output"] for c in calls),
                "credits": sum(c["credits"] for c in calls),
                "latency_s": sum(c["latency_s"] for c in calls),
                "api_attempts": [int(c.get("attempts", 1)) for c in calls]}
        if parsed is None:
            # Uniform fallback, flagged. Drawn from the tape so a resumed run
            # makes the same choice as an uninterrupted one.
            u = self.tapes.u_coord[obs.round - 1]
            label = obs.available[min(int(u * len(obs.available)), len(obs.available) - 1)]
            return Decision(label, obs.notes, fallback=True, meta=meta)
        label, notes = parsed
        return Decision(label, notes, meta=meta)
