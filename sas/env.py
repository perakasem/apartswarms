"""The round loop. One task per round, one worker per task (plan: T = 60).

Coordinators see only labels, the neutral title and the feedback history; they
never see slots, types or theta. Feedback follows the three signals of
Section 2.6. Clean audits are not announced.

Secondary conditions (review 4.2 / 4.3), all defaulting to the primary design:
  visibility  blind | visible     visible shows the task fact before assignment
  framing     points | qualitative  qualitative hides all point values
  tone        neutral | preachy   objection wording (only rendered with reason feedback)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .params import SLOT_TYPES, Payoffs, worker_profiles
from .tapes import Tapes
from .tasks import make_task

FEEDBACK_MODES = ("outcome", "reason")
VISIBILITY_MODES = ("blind", "visible")
FRAMING_MODES = ("points", "qualitative")
TONES = ("neutral", "preachy")


@dataclass(frozen=True)
class Cell:
    rho: float
    feedback: str = "outcome"
    c: float = 5.0
    pi: float = 0.25
    v: float = 10.0
    L: float = 40.0
    visibility: str = "blind"
    framing: str = "points"
    tone: str = "neutral"

    def __post_init__(self):
        for value, allowed in [(self.feedback, FEEDBACK_MODES), (self.visibility, VISIBILITY_MODES),
                               (self.framing, FRAMING_MODES), (self.tone, TONES)]:
            if value not in allowed:
                raise ValueError(f"{value!r} not in {allowed}")
        if not (0 <= self.rho <= 1 and 0 < self.pi < 1):
            raise ValueError("rho must be in [0, 1] and pi in (0, 1)")

    @property
    def payoffs(self) -> Payoffs:
        return Payoffs(self.v, self.c, self.L)

    @property
    def cell_id(self) -> str:
        """Secondary factors appear only when non-default, so primary-design
        cell ids (and their result folders) stay stable as factors are added."""
        cid = f"rho{self.rho:g}_fb-{self.feedback}_c{self.c:g}_pi{self.pi:g}"
        if self.visibility != "blind":
            cid += f"_vis-{self.visibility}"
        if self.framing != "points":
            cid += f"_frame-{self.framing}"
        if self.tone != "neutral":
            cid += f"_tone-{self.tone}"
        return cid


@dataclass(frozen=True)
class Feedback:
    round: int
    label: str
    outcome: str          # "objected" | "completed" | "flagged"
    points: float
    reason: str | None = None   # objection text + task fact, reason-visible only
    # Not rendered to the LLM. Present only where the LLM could verify theta
    # itself from what it was shown (reason feedback on an objection, or a
    # task-visible condition), so information-matched baselines can use it.
    verifiable_theta: str | None = None
    auto: bool = False    # the harness assigned this round (unusable LLM reply)


@dataclass
class Observation:
    round: int                      # 1-based
    T: int
    title: str
    available: list[str]            # labels, in this round's random order
    history: list[Feedback]
    score: float
    notes: str
    fact: str | None = None             # task fact, task-visible condition only
    visible_theta: str | None = None    # theta behind `fact`; never rendered


@dataclass
class Decision:
    label: str
    notes: str = ""
    fallback: bool = False
    meta: dict = field(default_factory=dict)


class Coordinator(Protocol):
    name: str

    def reset(self, cell: Cell, tapes: Tapes, T: int) -> None: ...
    def choose(self, obs: Observation) -> Decision: ...


class ReplayMismatch(RuntimeError):
    """A checkpointed round does not reproduce; the checkpoint cannot be resumed."""


REPLAY_KEYS = ("theta", "slot", "objected", "audited", "detected", "outcome", "points", "score")


def run_episode(cell: Cell, tapes: Tapes, coord: Coordinator, T: int,
                prior: list[dict] | None = None, on_round=None) -> list[dict]:
    """Play T rounds; return one record per round (the raw data unit).

    prior: records of rounds already played (a checkpoint). Their decisions
        are replayed without calling the coordinator, and every replayed round
        must reproduce its stored outcome exactly, or ReplayMismatch is raised.
    on_round: called with each *new* record as soon as it exists, so the
        caller can persist it before the next (possibly failing) API call.
    """
    prior = prior or []
    pay = cell.payoffs
    profiles = worker_profiles(cell.pi)
    slot_of = {lab: i for i, lab in enumerate(tapes.labels)}
    coord.reset(cell, tapes, T)

    history: list[Feedback] = []
    score, notes = 0.0, ""
    records = []
    for t in range(T):
        theta = tapes.theta(t, cell.pi)
        task = make_task(tapes.seed, t, tapes.kind(t), theta)
        order = [tapes.labels[i] for i in tapes.orders[t]]
        visible = cell.visibility == "visible"
        obs = Observation(t + 1, T, task.title, order, list(history), score, notes,
                          fact=task.fact if visible else None,
                          visible_theta=theta if visible else None)
        if t < len(prior):
            p = prior[t]
            dec = Decision(p["label"], p.get("notes") or "", bool(p.get("fallback")), p.get("meta") or {})
        else:
            dec = coord.choose(obs)
        if dec.label not in slot_of:
            raise ValueError(f"coordinator returned unknown label {dec.label!r}")
        notes = dec.notes

        slot = slot_of[dec.label]
        wtype = SLOT_TYPES[slot]
        prof = profiles[wtype]
        p_object = prof.r if theta == "O" else prof.f
        objected = bool(tapes.u_act[t, slot] < p_object)
        violation = (not objected) and theta == "O"
        audited = bool(tapes.u_audit[t] < cell.rho)
        detected = violation and audited

        if objected:
            outcome, points = "objected", -pay.c
        elif detected:
            outcome, points = "flagged", pay.v - pay.L
        else:
            outcome, points = "completed", pay.v
        score += points
        reason, vtheta = None, None
        if cell.feedback == "reason" and objected:
            reason = f'Objection: "{task.objection_text(cell.tone)}" Task fact: {task.fact}'
            vtheta = theta
        if visible:
            vtheta = theta
        history.append(Feedback(t + 1, dec.label, outcome, points, reason, vtheta, dec.fallback))

        records.append({
            "round": t + 1, "task_id": task.task_id, "task_kind": task.kind, "theta": theta,
            "title": task.title, "order": order,
            "label": dec.label, "slot": slot, "wtype": wtype,
            "objected": objected, "violation": violation, "audited": audited,
            "detected": detected, "outcome": outcome, "points": points,
            "score": score, "fallback": dec.fallback, "notes_len": len(notes),
            "notes": notes, "meta": dec.meta,
        })
        rec = records[-1]
        if t < len(prior):
            bad = [k for k in REPLAY_KEYS if k in prior[t] and prior[t][k] != rec[k]]
            if bad:
                raise ReplayMismatch(f"round {t + 1}: stored {[(k, prior[t][k]) for k in bad]} "
                                     f"!= replayed {[(k, rec[k]) for k in bad]}")
        elif on_round is not None:
            on_round(rec)
    return records
