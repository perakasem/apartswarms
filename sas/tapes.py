"""Common random numbers (plan decision 2).

Every stochastic element of a run is pre-drawn from the run seed alone, so the
LLM and every baseline face the same task stream, the same worker coin flips
and the same audit draws. Tapes do not depend on the cell: the same seed under
pi = 0.15 and pi = 0.35 differs only where u_theta falls between the two.
"""

from __future__ import annotations

import string
from dataclasses import dataclass

import numpy as np

from .params import SLOT_TYPES

N_WORKERS = len(SLOT_TYPES)


@dataclass(frozen=True)
class Tapes:
    seed: int
    T: int
    u_theta: np.ndarray   # (T,)    theta_t = O iff u_theta < pi
    u_kind: np.ndarray    # (T,)    permission iff u_kind < 0.5
    u_act: np.ndarray     # (T, 8)  worker i objects iff u_act[t, i] < (r_i if O else f_i)
    u_audit: np.ndarray   # (T,)    audited iff u_audit < rho
    u_coord: np.ndarray   # (T,)    spare uniform for baseline tie-breaking / fallbacks
    labels: tuple         # slot -> label, fixed within the run
    orders: np.ndarray    # (T, 8)  slot order in which workers are listed each round

    def theta(self, t: int, pi: float) -> str:
        return "O" if self.u_theta[t] < pi else "P"

    def kind(self, t: int) -> str:
        return "permission" if self.u_kind[t] < 0.5 else "evidence"


def _labels(rng: np.random.Generator) -> tuple:
    letters = [c for c in string.ascii_uppercase if c not in "IO"]
    digits = "23456789"
    out: set[str] = set()
    while len(out) < N_WORKERS:
        out.add("".join([rng.choice(letters), rng.choice(list(digits)),
                         rng.choice(letters), rng.choice(list(digits))]))
    labels = sorted(out)
    rng.shuffle(labels)
    return tuple(labels)


def make_tapes(seed: int, T: int) -> Tapes:
    rng = np.random.default_rng([seed, 20261108])
    u_theta = rng.random(T)
    u_kind = rng.random(T)
    u_act = rng.random((T, N_WORKERS))
    u_audit = rng.random(T)
    u_coord = rng.random(T)
    labels = _labels(rng)
    orders = np.stack([rng.permutation(N_WORKERS) for _ in range(T)])
    return Tapes(seed, T, u_theta, u_kind, u_act, u_audit, u_coord, labels, orders)
