"""Relay Gate: a deterministic-first, LLM-escalation-second safety gate for
coding-agent trajectories.

See README.md for the full design. This package exposes the pieces a caller
needs: `evaluate_trajectory` (the gate entry point), the reason codes, and the
two judge providers (mock and Nebius/NVIDIA).
"""

from relay_gate.gate import evaluate_trajectory, GateVerdict
from relay_gate.reasons import ReasonCode

__all__ = ["evaluate_trajectory", "GateVerdict", "ReasonCode"]

__version__ = "0.1.0"
