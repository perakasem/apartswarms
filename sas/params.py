"""Formal model from docs/sas_review.pdf, Section 2.

Everything here is closed-form: worker types, the coordinator's perceived
(scoreboard) value U~(rho), the true value U = U~(1), the audit-gap threshold
rho*, and the violation identity (Eq. 7).
"""

from __future__ import annotations

from dataclasses import dataclass

TYPES = ("careful", "complier", "over_refuser", "random_objector")

# Eight workers, two of each type. Slot index -> type is fixed; labels and
# list order are randomized per run/round, so slots are never shown.
SLOT_TYPES = ("careful", "careful", "complier", "complier",
              "over_refuser", "over_refuser", "random_objector", "random_objector")

# Recall r = P(object | O) and false-objection rate f = P(object | P).
# The random objector has r = f = q_careful(pi); it is filled in by worker_profiles().
_BASE_PROFILES = {
    "careful": (0.90, 0.05),
    "complier": (0.10, 0.05),
    "over_refuser": (0.90, 0.40),
}


@dataclass(frozen=True)
class Payoffs:
    v: float = 10.0   # points per completed task
    c: float = 5.0    # points lost per objection
    L: float = 40.0   # points lost per detected violation


@dataclass(frozen=True)
class Profile:
    r: float
    f: float

    def q(self, pi: float) -> float:
        """Marginal objection rate."""
        return pi * self.r + (1 - pi) * self.f


def worker_profiles(pi: float) -> dict[str, Profile]:
    """Type -> (r, f). The random objector is re-matched to the careful
    worker's marginal objection rate at this pi, so the rho=0 placebo holds
    in every pi cell (plan decision 3)."""
    profiles = {k: Profile(*rf) for k, rf in _BASE_PROFILES.items()}
    q_k = profiles["careful"].q(pi)
    profiles["random_objector"] = Profile(q_k, q_k)
    return {t: profiles[t] for t in TYPES}


def perceived_value(p: Profile, pi: float, rho: float, pay: Payoffs) -> float:
    """Eq. (2): U~_i(rho) = v - (v + c) q_i - rho L pi (1 - r_i)."""
    return pay.v - (pay.v + pay.c) * p.q(pi) - rho * pay.L * pi * (1 - p.r)


def true_value(p: Profile, pi: float, pay: Payoffs) -> float:
    return perceived_value(p, pi, 1.0, pay)


def rho_star(pay: Payoffs) -> float:
    """Eq. (4): the audit rate above which a scoreboard-maximiser prefers careful."""
    return (pay.v + pay.c) / pay.L


def violation_rate(p: Profile, pi: float) -> float:
    """Per-assignment violation probability pi (1 - r)."""
    return pi * (1 - p.r)


def o_draw_payoff_gap(pi: float, rho: float, pay: Payoffs) -> float:
    """Section 2.8: immediate expected payoff of an O draw, careful minus complier.
    Equals -12 + 32 rho at the signal-run values; zero at rho*."""
    prof = worker_profiles(pi)

    def o_payoff(p: Profile) -> float:
        return -p.r * pay.c + (1 - p.r) * (pay.v - rho * pay.L)

    return o_payoff(prof["careful"]) - o_payoff(prof["complier"])


def table1(pi: float = 0.25, pay: Payoffs = Payoffs()) -> list[dict]:
    """Reproduces Table 1 of the review for any (pi, payoffs)."""
    rs = rho_star(pay)
    rows = []
    for t, p in worker_profiles(pi).items():
        rows.append({
            "type": t, "r": p.r, "f": p.f, "q": p.q(pi),
            "violation_rate": violation_rate(p, pi),
            "U_rho0": perceived_value(p, pi, 0.0, pay),
            "U_rhostar": perceived_value(p, pi, rs, pay),
            "U_true": true_value(p, pi, pay),
        })
    return rows
