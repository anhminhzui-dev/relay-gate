#!/usr/bin/env python3
"""One-command demo. Run with: python run_demo.py

Does two things, in order, entirely offline (no network call, no API key
needed):

  1. Runs relay-gate's own gate against three bundled example trajectories,
     printed live, to show the relay in action: a clean case (GO, no judge
     call), a rule-caught case (HOLD, no judge call), and an ambiguous case
     resolved by the mock judge provider (GO, one judge call).
  2. Runs the full pytest suite and prints how many tests passed.

No dependency beyond the Python standard library and pytest is required.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC))

from relay_gate.gate import evaluate_trajectory  # noqa: E402
from relay_gate.judge import MockJudgeProvider  # noqa: E402
from relay_gate.schema import Trajectory  # noqa: E402


def _show(title: str, fixture_name: str, provider=None) -> None:
    trajectory = Trajectory.load(str(FIXTURES / fixture_name))
    verdict = evaluate_trajectory(trajectory, provider=provider)
    print(f"\n--- {title} ---")
    print(f"trajectory: {fixture_name}")
    print(json.dumps(verdict.to_dict(), indent=2))


def main() -> int:
    print("=" * 60)
    print("RELAY GATE demo (offline, mock judge provider only)")
    print("=" * 60)

    _show("1. clean trajectory: rules alone say GO, no judge call", "clean_trajectory.json")
    _show(
        "2. rule violation: rules alone say HOLD, no judge call",
        "destructive_without_read.json",
    )

    mock = MockJudgeProvider(canned={"ambiguous-001": ("PASS", "confirmed same file after case-normalised match")})
    _show(
        "3. ambiguous case: rules cannot decide, escalate ONCE to the judge",
        "ambiguous_trajectory.json",
        provider=mock,
    )

    print("\n" + "=" * 60)
    print("Running the test suite (pytest)")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip())
        print("\nDEMO SUMMARY: gate demo ran; test suite FAILED (see above).")
        return 1

    print("\nDEMO SUMMARY: gate demo ran (GO / HOLD / escalated-GO all shown); test suite PASSED.")
    print(
        "To try the real judge provider instead of the mock: set NEBIUS_API_KEY and "
        "NEBIUS_MODEL_ID (see README.md 'Running against the real API'), then run:\n"
        "  python -m relay_gate.cli check tests/fixtures/ambiguous_trajectory.json --provider nebius"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
