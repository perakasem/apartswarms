"""Prompt approval (change 10): the hash the team approves, and where the
approval is recorded.

The approval hash covers every text the coordinator can be shown: the system
prompt for both framings and both friction levels, a synthetic round prompt
that exercises every rendering branch (objected / completed / flagged /
auto-assigned rows, the reason line, notes, task details) in both framings,
the re-ask message, and the worker text templates. Code comments do not
affect it; any wording change does.

Approval is read from APPROVED_PROMPT_HASH (repo root, one line) or, failing
that, the "Prompt hash" row of docs/PREREGISTRATION.md §0. Only
scripts/render_prompts.py writes docs/PROMPTS_RENDERED.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .env import Cell, Feedback, Observation
from .prompts import NOTES_MAX_CHARS, REASK, round_prompt, system_prompt

ROOT = Path(__file__).resolve().parent.parent
# SAS_APPROVED_FILE lets tests point at a scratch approval file.
APPROVED_FILE = Path(os.environ.get("SAS_APPROVED_FILE", ROOT / "APPROVED_PROMPT_HASH"))
PREREG = ROOT / "docs" / "PREREGISTRATION.md"
RENDERED = ROOT / "docs" / "PROMPTS_RENDERED.md"
HASH_LINE = re.compile(r"Approval hash: `([0-9a-f]{16})`")


def synthetic_observation(framing_fact: bool) -> Observation:
    hist = [Feedback(1, "K7Q2", "completed", 10.0),
            Feedback(2, "A3B4", "objected", -5.0,
                     reason='Objection: "<objection text>" Task fact: <task fact>', verifiable_theta="O"),
            Feedback(3, "K7Q2", "flagged", -30.0),
            Feedback(4, "Z9X8", "completed", 10.0, auto=True)]
    return Observation(5, 60, "<task title>", ["K7Q2", "A3B4", "Z9X8"], hist, -15.0, "<notes>",
                       fact="<task details>" if framing_fact else None)


def approval_hash() -> str:
    from .grid import templates_hash
    parts = []
    for framing in ("points", "qualitative"):
        for c in (5.0, 15.0):
            parts.append(system_prompt(Cell(rho=0.0, c=c, framing=framing), 60))
        for fact in (False, True):
            parts.append(round_prompt(synthetic_observation(fact), framing))
    parts += [REASK, str(NOTES_MAX_CHARS), templates_hash()]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:16]


def approved_hash() -> str | None:
    if APPROVED_FILE.exists():
        h = APPROVED_FILE.read_text().strip()
        return h or None
    if PREREG.exists():
        m = re.search(r"\|\s*Prompt hash[^|]*\|\s*`?([0-9a-f]{16})`?\s*\|", PREREG.read_text())
        if m:
            return m.group(1)
    return None


def rendered_doc_hash() -> str | None:
    if not RENDERED.exists():
        return None
    m = HASH_LINE.search(RENDERED.read_text())
    return m.group(1) if m else None
