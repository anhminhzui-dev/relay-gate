"""Command-line entry point.

    python -m relay_gate.cli check trajectory.json [--provider mock|nebius] [--mock-canned canned.json]
    python -m relay_gate.cli coverage trace.json [--format native|mast|arb|claude-jsonl]

`trajectory.json` may hold one trajectory object or a JSON list of them.
Exit code is 0 if every trajectory is GO, 2 if any is HOLD, so the tool is
usable as a CI gate.

`coverage` reports, for a trace file in any of the four supported shapes,
which of the six rules.py checks can physically fire on it and which
field's absence disables each of the rest -- see relay_gate.coverage.
Exit code is 0 on a normal report, 2 if `--format` does not match the
file's shape (a relay_gate.coverage.TraceFormatError, printed as one line
to stderr, never a raw traceback).
"""

from __future__ import annotations

import argparse
import json
import sys

from relay_gate.coverage import FORMATS, TraceFormatError, file_coverage, format_table
from relay_gate.gate import evaluate_trajectory
from relay_gate.judge import JudgeProvider, MockJudgeProvider, NebiusNemotronProvider
from relay_gate.schema import Trajectory


def _load_trajectories(path: str) -> list[Trajectory]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    items = raw if isinstance(raw, list) else [raw]
    return [Trajectory.from_dict(item) for item in items]


def _build_provider(args: argparse.Namespace) -> JudgeProvider | None:
    if args.provider is None:
        return None
    if args.provider == "mock":
        canned = {}
        if args.mock_canned:
            with open(args.mock_canned, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            canned = {tid: (v["verdict"], v["reason"]) for tid, v in raw.items()}
        return MockJudgeProvider(canned=canned)
    if args.provider == "nebius":
        return NebiusNemotronProvider()
    raise ValueError(f"unknown provider: {args.provider}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relay-gate")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="evaluate one or more trajectories")
    check.add_argument("path", help="path to a trajectory JSON file or a JSON list of trajectories")
    check.add_argument(
        "--provider",
        choices=["mock", "nebius"],
        default=None,
        help="judge provider to escalate ambiguous findings to; omit to fail closed with no judge",
    )
    check.add_argument(
        "--mock-canned",
        default=None,
        help="path to a JSON file of {trajectory_id: {verdict, reason}} for the mock provider",
    )

    coverage = sub.add_parser("coverage", help="report which of the six checks can physically fire on a trace file")
    coverage.add_argument("path", help="path to a trace file")
    coverage.add_argument(
        "--format",
        choices=list(FORMATS),
        default="native",
        help="trace file shape; default native (relay_gate.schema.Trajectory JSON)",
    )

    args = parser.parse_args(argv)

    if args.command == "coverage":
        try:
            summary = file_coverage(args.path, fmt=args.format)
        except TraceFormatError as exc:
            print(f"relay-gate: {exc}", file=sys.stderr)
            return 2
        print(format_table(summary))
        print(json.dumps(summary))
        return 0

    if args.command == "check":
        trajectories = _load_trajectories(args.path)
        provider = _build_provider(args)

        verdicts = [evaluate_trajectory(t, provider=provider) for t in trajectories]
        holds = 0
        for v in verdicts:
            print(json.dumps(v.to_dict()))
            if v.decision == "HOLD":
                holds += 1

        total = len(verdicts)
        judge_calls = sum(v.judge_calls for v in verdicts)
        print(f"RELAY-GATE: {total} trajectories, {total - holds} GO, {holds} HOLD, {judge_calls} judge call(s)")
        return 0 if holds == 0 else 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
