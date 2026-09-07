"""The gate: relay only the ambiguous cases to a judge.

Order of operations, always:
  1. Run every deterministic rule (free, offline, instant).
  2. If any rule produced a definite HOLD finding, stop there. HOLD.
     No judge call is made; a definite finding needs no second opinion.
  3. Else, if any rule produced an AMBIGUOUS finding, that is the only
     time a judge is consulted, and it is consulted once per trajectory
     (all ambiguous findings for that trajectory go into one call).
  4. If no provider is configured, an ambiguous trajectory fails closed
     to HOLD rather than guessing.
  5. No findings at all: GO.

This ordering is the whole point of the project: the judge (and its
network/token cost) is reserved for exactly the cases free rules cannot
resolve, never called on trajectories the rules already settled.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from relay_gate.judge import JudgeProvider
from relay_gate.reasons import ReasonCode
from relay_gate.rules import run_all_rules
from relay_gate.schema import Trajectory


@dataclass(frozen=True)
class GateVerdict:
    trajectory_id: str
    decision: str  # "GO" | "HOLD"
    reasons: tuple[tuple[ReasonCode, str], ...]
    judge_calls: int
    judge_provider: str | None = None

    def to_dict(self) -> dict:
        return {
            "trajectory_id": self.trajectory_id,
            "decision": self.decision,
            "reasons": [{"code": code.value, "detail": detail} for code, detail in self.reasons],
            "judge_calls": self.judge_calls,
            "judge_provider": self.judge_provider,
        }


def evaluate_trajectory(trajectory: Trajectory, provider: JudgeProvider | None = None) -> GateVerdict:
    findings = run_all_rules(trajectory)
    hold = [f for f in findings if f.category == "hold"]
    ambiguous = [f for f in findings if f.category == "ambiguous"]

    if hold:
        reasons = tuple((f.reason, f.detail) for f in hold + ambiguous)
        return GateVerdict(trajectory.trajectory_id, "HOLD", reasons, judge_calls=0)

    if ambiguous:
        if provider is None:
            reasons = tuple((f.reason, f.detail) for f in ambiguous) + (
                (ReasonCode.JUDGE_UNAVAILABLE, "no judge provider configured; ambiguous findings fail closed"),
            )
            return GateVerdict(trajectory.trajectory_id, "HOLD", reasons, judge_calls=0)

        verdict = provider.judge(trajectory, ambiguous)
        code = ReasonCode.ESCALATED_PASS if verdict.verdict == "PASS" else ReasonCode.ESCALATED_FAIL
        decision = "GO" if verdict.verdict == "PASS" else "HOLD"
        reasons = tuple((f.reason, f.detail) for f in ambiguous) + ((code, verdict.reason),)
        return GateVerdict(trajectory.trajectory_id, decision, reasons, judge_calls=1, judge_provider=verdict.provider)

    return GateVerdict(trajectory.trajectory_id, "GO", ((ReasonCode.CLEAN, "no rule findings"),), judge_calls=0)
