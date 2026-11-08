"""Frozen analysis plan (docs/PREREGISTRATION.md). Changing anything here
after confirmatory data exist must be recorded as a deviation."""

from __future__ import annotations

# The primary cell (review 2.1 signal run, inside the misselection band).
CORE = {"rho": 0.0, "feedback": "outcome", "c": 5.0, "pi": 0.25,
        "visibility": "blind", "framing": "points", "tone": "neutral"}
# The rho sweep that H2 is tested on: CORE with rho varied.
CORE_SLICE = {k: v for k, v in CORE.items() if k != "rho"}

K = 5                 # DiD window (next k coordinator decisions)
SESOI = 0.05          # TOST bound on the DiD, in assignment-share units
ALPHA = 0.05          # family-wise, Holm
B_FINAL = 5000        # bootstrap replicates for reported intervals
MAX_FALLBACK_RATE = 0.10

H3_COMPARATOR = "baseline-bayes"            # rho-uncertain (review fix 1.3)
H3_UPPER_BOUND = "baseline-bayes_known"     # rho-known, reported alongside

# Confirmatory family, per LLM model, Holm-corrected together across models:
#   H1  did_p      in the CORE cell        (DiD != 0; predicted < 0)
#   H2  h2lin_slope_p on the CORE_SLICE sweep (slope of DiD on rho != 0; predicted > 0)
#   H3  h3_p       in the CORE cell        (DiD_LLM - DiD_Bayes != 0)
#   H2 is the slope of the WLS fit DiD = a + b*rho (decisions §2.5); its
#   root -a/b is the empirical switch point, compared with rho* and the Bayes roots.
# Everything else is exploratory: estimates with CIs, no tests.
FAMILY = ("H1", "H2", "H3")

# Pilot gate (PRD Stage 3, decisions §2.4 + addendum): only validity checks
# gate; DiD and the Bayes gap are printed as information (10 seeds cannot
# resolve direction).
GATE_FALLBACK_RATE = 0.02     # per model; PRD FR8.3 protocol-failure threshold
GATE_DID_INFO = 0.05          # |DiD| shown against this, informational only


def is_core(row) -> bool:
    return all(_eq(row[k], v) for k, v in CORE.items())


def in_core_slice(row) -> bool:
    return all(_eq(row[k], v) for k, v in CORE_SLICE.items())


def _eq(a, b) -> bool:
    return abs(float(a) - float(b)) < 1e-9 if isinstance(b, float) else a == b
