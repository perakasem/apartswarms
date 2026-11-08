"""Behaviour fingerprints: the cache key of the shared run store (review fix 1.2).

A completed run is reused only if everything that could change the
coordinator's behaviour is unchanged. Rather than hashing source files (where
a comment edit would orphan paid runs), the fingerprint hashes *behaviour*:

  LLM coordinators: every prompt of a canonical episode (system prompt and
    all T round prompts, rendered from a uniform-random run on a fixed seed),
    the outcomes the environment produced, the re-ask text, the notes limit,
    the reply parser, and the call settings (model ID, temperature, output
    limit, re-ask count, reasoning control).
  Baselines: the decisions and outcomes of the baseline itself on canonical
    episodes, plus its spec.

Any change to prompts, payoffs, tasks, tapes, feedback rendering, T or call
settings changes the key, so stale runs are never silently reused.
The provider can still update a model behind the same ID; the served model
string is recorded per call and checked in build_dataset.py.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from functools import lru_cache

from .env import REPLAY_KEYS, Cell, run_episode
from .tapes import make_tapes

FINGERPRINT_SEEDS = (424242, 434343)
LLM_SETTING_KEYS = ("api", "max_output_tokens", "temperature", "max_reasks", "require_no_reasoning")


def _h(parts: list) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _outcomes(records: list[dict]) -> list:
    return [[r[k] for k in REPLAY_KEYS] for r in records]


@lru_cache(maxsize=4096)
def _llm_fp(cell: Cell, T: int, model: str, settings: tuple, api_host: str, route: str) -> str:
    from .coordinators import Uniform, parse_reply
    from .prompts import NOTES_MAX_CHARS, REASK, round_prompt, system_prompt

    prompts = []

    class Rec(Uniform):
        def choose(self, obs):
            prompts.append(round_prompt(obs, cell.framing))
            return super().choose(obs)

    recs = run_episode(cell, make_tapes(FINGERPRINT_SEEDS[0], T), Rec(), T)
    return _h(["llm", model, sorted(settings), api_host, route, system_prompt(cell, T), prompts,
               _outcomes(recs),
               REASK, NOTES_MAX_CHARS, inspect.getsource(parse_reply)])


@lru_cache(maxsize=4096)
def _baseline_fp(cell: Cell, T: int, spec: str) -> str:
    from .coordinators import make_baseline

    parts = ["baseline", spec]
    for seed in FINGERPRINT_SEEDS:
        parts.append(_outcomes(run_episode(cell, make_tapes(seed, T), make_baseline(spec), T)))
    return _h(parts)


def llm_fingerprint(cell: Cell, T: int, model: str, llm: dict, api_host: str = "",
                    route: dict | None = None) -> str:
    """route = the pinned OpenRouter route (slug, provider, reasoning); prices are
    excluded (projection only). API keys are never an input."""
    r = {k: v for k, v in (route or {}).items() if k in ("slug", "provider", "reasoning")}
    return _llm_fp(cell, T, model, tuple((k, llm.get(k)) for k in LLM_SETTING_KEYS),
                   api_host, json.dumps(r, sort_keys=True))


def baseline_fingerprint(cell: Cell, T: int, spec: str) -> str:
    return _baseline_fp(cell, T, spec)
