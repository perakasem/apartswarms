"""Non-LLM coordinators that see exactly what the LLM sees (review Section 4.1).

  uniform   drift-free floor
  oracle    knows true U_i (rho = 1): the social optimum
  softmax   scoreboard learner, logit choice over running mean points (Eq. 5);
            used for power simulation and to validate the lambda estimator
  bayes     Thompson sampling over each worker's type; knows the four type
            profiles and rho, maximises the scoreboard value U~(rho) -- the
            same objective the LLM is given. "Generous" (Section 2.11).
"""

from __future__ import annotations

import zlib

import numpy as np

from ..env import Cell, Decision, Observation
from ..params import SLOT_TYPES, TYPES, perceived_value, true_value, worker_profiles
from ..tapes import Tapes


class _Base:
    name = "base"

    def reset(self, cell: Cell, tapes: Tapes, T: int) -> None:
        self.cell, self.tapes, self.T = cell, tapes, T
        self.rng = np.random.default_rng([tapes.seed, zlib.crc32(self.name.encode())])

    def _pick(self, labels: list[str], scores: np.ndarray) -> str:
        best = np.flatnonzero(np.isclose(scores, scores.max()))
        return labels[int(self.rng.choice(best))]


class Uniform(_Base):
    name = "uniform"

    def choose(self, obs: Observation) -> Decision:
        return Decision(obs.available[int(self.rng.integers(len(obs.available)))])


class Oracle(_Base):
    name = "oracle"

    def reset(self, cell, tapes, T):
        super().reset(cell, tapes, T)
        prof = worker_profiles(cell.pi)
        self.value = {lab: true_value(prof[SLOT_TYPES[i]], cell.pi, cell.payoffs)
                      for i, lab in enumerate(tapes.labels)}

    def choose(self, obs):
        return Decision(self._pick(obs.available, np.array([self.value[l] for l in obs.available])))


class Softmax(_Base):
    """Logit choice over a shrunk running mean of observed points.

    estimate = (sum of points + n0 * m0) / (n + n0), with an optimistic prior
    m0 = v so unseen workers get tried."""

    def __init__(self, lam: float = 0.5, n0: float = 1.0):
        self.lam, self.n0 = lam, n0
        self.name = f"softmax{lam:g}"

    def choose(self, obs):
        m0 = self.cell.v
        tot = {l: 0.0 for l in obs.available}
        cnt = {l: 0 for l in obs.available}
        for fb in obs.history:
            tot[fb.label] += fb.points
            cnt[fb.label] += 1
        est = np.array([(tot[l] + self.n0 * m0) / (cnt[l] + self.n0) for l in obs.available])
        z = self.lam * (est - est.max())
        p = np.exp(z) / np.exp(z).sum()
        return Decision(obs.available[int(self.rng.choice(len(p), p=p))])


RHO_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)   # every audit level used in the design


class Bayes(_Base):
    """Information-matched Thompson sampler over worker types.

    rho_known=False (spec "bayes", the H3 comparator; review fix 1.3): it has
    the LLM's information about audits, i.e. "some completed tasks may be
    audited", with no frequency. That is encoded as a uniform prior over
    RHO_GRID = {0, .25, .5, .75, 1} (every audit level in the design, so the
    true rho of any cell has prior support, including 0). It holds a joint
    posterior over rho and each worker's type and learns about rho only from
    flags and their absence. rho_known=True (spec "bayes_known")
    is the earlier, more generous baseline, kept as an upper bound.

    Where the LLM could verify theta from what it was shown (reason feedback on
    an objection; every round in the task-visible condition) the likelihood
    uses the joint (outcome, theta), otherwise the marginal. In the task-visible
    condition it values each worker for this task's visible theta.
    """

    def __init__(self, rho_known: bool = False):
        self.rho_known = rho_known
        self.name = "bayes_known" if rho_known else "bayes"

    def reset(self, cell, tapes, T):
        super().reset(cell, tapes, T)
        prof = worker_profiles(cell.pi)
        pi, pay = cell.pi, cell.payoffs
        self.rhos = (cell.rho,) if self.rho_known else RHO_GRID
        self.loglik, self.type_value = [], []
        for rho in self.rhos:
            joint = {}   # (outcome, theta) -> P(outcome, theta | type, rho)
            for o in ("objected", "completed", "flagged"):
                for th in ("O", "P"):
                    vals = []
                    for k in TYPES:
                        r, f = prof[k].r, prof[k].f
                        if th == "O":
                            p = {"objected": r, "completed": (1 - r) * (1 - rho),
                                 "flagged": (1 - r) * rho}[o] * pi
                        else:
                            p = {"objected": f, "completed": 1 - f, "flagged": 0.0}[o] * (1 - pi)
                        vals.append(p)
                    joint[(o, th)] = np.array(vals)
            ll = {}
            for o in ("objected", "completed", "flagged"):
                ll[(o, None)] = np.log(np.clip(joint[(o, "O")] + joint[(o, "P")], 1e-300, None))
                for th in ("O", "P"):
                    ll[(o, th)] = np.log(np.clip(joint[(o, th)], 1e-300, None))
            self.loglik.append(ll)
            self.type_value.append({
                None: np.array([perceived_value(prof[k], pi, rho, pay) for k in TYPES]),
                "O": np.array([-prof[k].r * pay.c + (1 - prof[k].r) * (pay.v - rho * pay.L) for k in TYPES]),
                "P": np.array([-prof[k].f * pay.c + (1 - prof[k].f) * pay.v for k in TYPES]),
            })
        # log P(type, history_of_worker | rho), per rho, per worker (uniform type prior)
        self.logjoint = [{lab: np.full(len(TYPES), -np.log(len(TYPES))) for lab in tapes.labels}
                         for _ in self.rhos]
        self._seen = 0

    def rho_posterior(self) -> np.ndarray:
        """P(rho | history): the type sums factorise over workers given rho."""
        lp = np.array([sum(np.logaddexp.reduce(v) for v in lj.values()) for lj in self.logjoint])
        p = np.exp(lp - lp.max())
        return p / p.sum()

    def choose(self, obs):
        for fb in obs.history[self._seen:]:
            for j in range(len(self.rhos)):
                self.logjoint[j][fb.label] = self.logjoint[j][fb.label] + self.loglik[j][(fb.outcome, fb.verifiable_theta)]
        self._seen = len(obs.history)
        p_rho = self.rho_posterior()
        j = int(self.rng.choice(len(self.rhos), p=p_rho))
        values = self.type_value[j][obs.visible_theta]
        draws = []
        for lab in obs.available:
            lp = self.logjoint[j][lab]
            p = np.exp(lp - lp.max())
            p /= p.sum()
            draws.append(values[int(self.rng.choice(len(TYPES), p=p))])
        meta = {} if self.rho_known else {"p_rho": [round(float(x), 4) for x in p_rho]}
        return Decision(self._pick(obs.available, np.array(draws)), meta=meta)


def make_baseline(spec: str):
    """'uniform' | 'oracle' | 'bayes' (rho-uncertain) | 'bayes_known' | 'softmax' | 'softmax:<lambda>'"""
    if spec == "uniform":
        return Uniform()
    if spec == "oracle":
        return Oracle()
    if spec == "bayes":
        return Bayes(rho_known=False)
    if spec == "bayes_known":
        return Bayes(rho_known=True)
    if spec.startswith("softmax"):
        _, _, lam = spec.partition(":")
        return Softmax(float(lam) if lam else 0.5)
    raise ValueError(f"unknown baseline {spec!r}")
