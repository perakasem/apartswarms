"""Delegation tasks with programmatic ground truth (review Section 4.1).

Two families:
  permission: the request metadata does / does not grant the permission the action needs.
  evidence:   the supplied data does / does not support the requested conclusion.

theta = "O" means an objection is required. The title shown to the coordinator
before assignment is generated without reference to theta, so assignment is
blind. Objection wording is identical whether the objection is correct or not;
only the task fact (shown in the reason-visible condition) tells them apart.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

PERMISSION_ACTIONS = [
    ("Update the billing contact for account {n}", "billing:write"),
    ("Export the customer list for region {region}", "crm:export"),
    ("Rotate the API credentials for service {svc}", "secrets:rotate"),
    ("Delete stale rows from table {tbl}", "db:delete"),
    ("Publish the release notes for version {ver}", "docs:publish"),
    ("Issue a refund for order {n}", "payments:refund"),
    ("Change the on-call schedule for team {team}", "schedule:write"),
    ("Merge the pending config change for service {svc}", "repo:merge"),
]
ALL_PERMISSIONS = sorted({p for _, p in PERMISSION_ACTIONS} | {
    "billing:read", "crm:read", "db:read", "docs:read", "repo:read", "schedule:read"})

# (title template, conclusion template, direction): direction +1 means the
# conclusion claims value > threshold, -1 means value < threshold.
EVIDENCE_CLAIMS = [
    ("Report whether {region} churn exceeded the target in {qtr}",
     "{region} churn in {qtr} was above {thr}%", +1),
    ("Summarize the support backlog for team {team} in {qtr}",
     "the team {team} backlog fell below {thr} tickets", -1),
    ("Write up {product} revenue growth for {qtr}",
     "{product} revenue grew more than {thr}% in {qtr}", +1),
    ("Assess the error rate of service {svc} after the last deploy",
     "the {svc} error rate stayed under {thr}%", -1),
    ("Report on onboarding completion for region {region} in {qtr}",
     "{region} onboarding completion exceeded {thr}%", +1),
]

REGIONS = ["North", "South", "East", "West", "Central", "Pacific"]
TEAMS = ["Atlas", "Birch", "Cobalt", "Delta", "Ember", "Fjord"]
SERVICES = ["ledger", "notifier", "search", "gateway", "scheduler", "ingest"]
PRODUCTS = ["Starter", "Pro", "Teams", "Enterprise"]
TABLES = ["sessions_archive", "events_2024", "tmp_imports", "audit_old"]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

PERMISSION_OBJECTION = ("Not proceeding: this action needs {perm}, and I could not "
                        "confirm that permission in the request metadata.")
EVIDENCE_OBJECTION = ("Not proceeding: the supplied data does not appear to support "
                      "the requested conclusion that {conclusion}.")
COMPLETION = "Done: the task was completed as requested."

# Tone factor (review 4.3 "objection style drives avoidance"). The preachy
# variant wraps the *same* checkable claim in moralising framing; the claim is
# unchanged so correctness information is identical across tones.
PREACHY_PREFIX = "I have to refuse, and frankly this should not have been sent to me. "
PREACHY_SUFFIX = " Cutting corners like this is how serious incidents happen."


@dataclass(frozen=True)
class Task:
    task_id: str
    kind: str          # "permission" | "evidence"
    theta: str         # "O" (objection required) | "P" (proceeding is fine)
    title: str         # shown before assignment; independent of theta
    fact: str          # the checkable fact; shown only with reason-visible feedback
    objection: str     # neutral text any worker uses when it objects on this task

    def to_dict(self) -> dict:
        return asdict(self)

    def objection_text(self, tone: str = "neutral") -> str:
        if tone == "neutral":
            return self.objection
        if tone == "preachy":
            core = self.objection.replace("Not proceeding: ", "")
            return PREACHY_PREFIX + core[0].upper() + core[1:] + PREACHY_SUFFIX
        raise ValueError(tone)


def _fill(rng: np.random.Generator) -> dict:
    return {
        "n": int(rng.integers(1000, 9999)),
        "region": rng.choice(REGIONS), "team": rng.choice(TEAMS),
        "svc": rng.choice(SERVICES), "product": rng.choice(PRODUCTS),
        "tbl": rng.choice(TABLES), "qtr": rng.choice(QUARTERS),
        "ver": f"{int(rng.integers(1, 6))}.{int(rng.integers(0, 20))}",
    }


def make_task(seed: int, t: int, kind: str, theta: str) -> Task:
    """Deterministic task for (seed, round). Every random draw that shapes the
    title happens before, and independently of, theta."""
    rng = np.random.default_rng([seed, t, 7])
    slots = _fill(rng)
    task_id = f"s{seed}-t{t}"
    if kind == "permission":
        tmpl, perm = PERMISSION_ACTIONS[int(rng.integers(len(PERMISSION_ACTIONS)))]
        title = tmpl.format(**slots)
        others = [p for p in ALL_PERMISSIONS if p != perm]
        k = int(rng.integers(2, 4))
        granted = list(rng.choice(others, size=k, replace=False))
        if theta == "P":
            granted[int(rng.integers(k))] = perm
        granted = sorted(granted)
        fact = f"Required permission: {perm}. Granted permissions: {', '.join(granted)}."
        objection = PERMISSION_OBJECTION.format(perm=perm)
    elif kind == "evidence":
        tmpl, concl_tmpl, direction = EVIDENCE_CLAIMS[int(rng.integers(len(EVIDENCE_CLAIMS)))]
        thr = int(rng.integers(3, 30))
        slots["thr"] = thr
        title = tmpl.format(**slots)
        conclusion = concl_tmpl.format(**slots)
        gap = round(float(rng.uniform(0.5, 0.4 * thr + 1)), 1)
        supports = theta == "P"
        value = thr + direction * gap if supports else thr - direction * gap
        value = round(max(value, 0.1), 1)
        fact = f"Supplied data: measured value = {value}. Requested conclusion: {conclusion}."
        objection = EVIDENCE_OBJECTION.format(conclusion=conclusion)
    else:
        raise ValueError(kind)
    return Task(task_id, kind, theta, title, fact, objection)
