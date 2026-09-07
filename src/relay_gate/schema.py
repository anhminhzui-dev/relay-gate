"""Trajectory schema.

A trajectory is one coding agent's session, recorded as an ordered list of
tool calls plus a final claim. This module is the single place that knows
the on-disk JSON shape; every other module imports typed objects from here
instead of poking at raw dicts.

Shape (informal, see tests/fixtures/*.json for real examples):

{
  "trajectory_id": "t-001",
  "allowed_tools": ["read_file", "write_file", "delete_file", "run_tests", "git_commit"],
  "steps": [
    {"tool": "read_file", "args": {"path": "app/config.py"}, "output": "..."},
    {"tool": "delete_file", "args": {"path": "app/config.py"}, "output": "ok"},
    {"tool": "run_tests", "args": {}, "output": "12 passed"}
  ],
  "final_claim": "Removed the dead config module. All tests pass."
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Step:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    output: str = ""

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Step":
        if "tool" not in raw:
            raise ValueError("step is missing required field 'tool'")
        return Step(
            tool=raw["tool"],
            args=dict(raw.get("args", {})),
            output=str(raw.get("output", "")),
        )


@dataclass(frozen=True)
class Trajectory:
    trajectory_id: str
    allowed_tools: tuple[str, ...]
    steps: tuple[Step, ...]
    final_claim: str

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Trajectory":
        missing = [k for k in ("trajectory_id", "steps") if k not in raw]
        if missing:
            raise ValueError(f"trajectory is missing required field(s): {missing}")
        steps = tuple(Step.from_dict(s) for s in raw["steps"])
        return Trajectory(
            trajectory_id=raw["trajectory_id"],
            allowed_tools=tuple(raw.get("allowed_tools", [])),
            steps=steps,
            final_claim=str(raw.get("final_claim", "")),
        )

    @staticmethod
    def load(path: str) -> "Trajectory":
        import json

        with open(path, "r", encoding="utf-8") as fh:
            return Trajectory.from_dict(json.load(fh))
