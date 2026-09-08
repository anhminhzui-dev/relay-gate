#!/usr/bin/env python3
"""Stream-count pool-wide test-run detectability and operator-A eligibility.

RESULTS.md's "Rework 2" section cites three pool-wide figures -- 496 of
7,293 records with a detectable test run, 93 of 7,293 operator-A-eligible,
0 of 3,283 codex-sourced with a detectable test run -- that were produced by
a transient shell count, never written to a file on disk. This script
recomputes the same three figures from the same source
(trajectories/{claude,codex}.jsonl) using the exact same logic
mutate_and_score.py uses (relay_gate.rules._is_test_run via
mutate_and_score.find_test_index, and mutate_and_score.op_a_applicable for
the operator-A precondition), and writes them to
bench/fake_done/pool_counts.json so every number in RESULTS.md can cite a
file, not a shell scrollback.

Memory/runtime contract, same as mutate_and_score.py:
  - both trajectories/*.jsonl files are streamed line by line, never a
    whole-file read.
  - a wall-clock cap (--max-seconds) is checked periodically; a run that
    hits it reports timed_out=True and how far it got, never fabricates
    the rest.
  - no background jobs, no network sockets.
  - trajectories/{claude,codex}.jsonl are read-only here.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

_THIS_DIR = pathlib.Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import mutate_and_score as mas  # noqa: E402  (also wires src/ onto sys.path for relay_gate)
from relay_gate import rules as rg_rules  # noqa: E402

DEFAULT_TRAJECTORIES_DIR = mas.DEFAULT_TRAJECTORIES_DIR
MAX_SECONDS_DEFAULT = 300.0

# The bench's own synthetic mutation-operator tool name; see rules.py's own
# comment on why it is kept as an explicit marker despite 0 real occurrences.
DELETE_FILE_TOOL = "delete_file"
CRON_DELETE_TOOL = "CronDelete"


def run(trajectories_dir: pathlib.Path, max_seconds: float) -> dict:
    start = time.monotonic()
    deadline = start + max_seconds

    records_seen = {"claude": 0, "codex": 0}
    detectable_test_run = {"claude": 0, "codex": 0}
    operator_a_eligible = {"claude": 0, "codex": 0}
    timed_out = False

    # Five pool-wide figures that RESULTS.md / README.md / rules.py's own
    # comments and CLAUDE.md have so far only carried in prose, never a
    # results file on disk (fourth hostile-judge finding). Same streamed,
    # never-whole-file-read pass as the two blocks above.
    completion_marker_records = 0  # claim_text contains a rules._COMPLETION_MARKERS substring
    test_in_tool_name_records = 0  # a preceding_action's tool name contains "test" (case-insensitive)
    delete_file_records = 0  # a preceding_action's tool name is exactly "delete_file"
    cron_delete_records = 0  # a preceding_action's tool name is exactly "CronDelete" (case-insensitive)
    cron_delete_occurrences = 0  # total CronDelete actions, not just records that have >=1

    for source in ("claude", "codex"):
        path = trajectories_dir / f"{source}.jsonl"
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if time.monotonic() > deadline:
                    timed_out = True
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records_seen[source] += 1
                actions = list(obj.get("preceding_actions", []) or [])
                claim_text = obj.get("claim_text", "")
                # Same logic mutate_and_score.py uses -- find_test_index calls
                # relay_gate.rules._is_test_run(tool, command) per action, and
                # op_a_applicable additionally requires a completion-marker
                # claim in the same preceding_actions window.
                if mas.find_test_index(actions) is not None:
                    detectable_test_run[source] += 1
                if mas.op_a_applicable(claim_text, actions):
                    operator_a_eligible[source] += 1

                claim_lower = (claim_text or "").lower()
                if any(m in claim_lower for m in rg_rules._COMPLETION_MARKERS):
                    completion_marker_records += 1

                tool_names = [str(a.get("tool") or "") for a in actions]
                if any("test" in t.lower() for t in tool_names):
                    test_in_tool_name_records += 1
                if any(t == DELETE_FILE_TOOL for t in tool_names):
                    delete_file_records += 1
                record_cron_deletes = sum(1 for t in tool_names if t.lower() == CRON_DELETE_TOOL.lower())
                if record_cron_deletes:
                    cron_delete_records += 1
                    cron_delete_occurrences += record_cron_deletes
        if timed_out:
            break

    total_records = records_seen["claude"] + records_seen["codex"]
    total_test_run = detectable_test_run["claude"] + detectable_test_run["codex"]
    total_op_a = operator_a_eligible["claude"] + operator_a_eligible["codex"]

    def _frac(n: int, d: int) -> str:
        return f"{n}/{d}"

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": (
            "Streamed line-by-line count over trajectories/{claude,codex}.jsonl, "
            "using mutate_and_score.find_test_index (relay_gate.rules._is_test_run, "
            "the command-string-aware version) for test-run detectability and "
            "mutate_and_score.op_a_applicable (completion-marker claim AND a "
            "detectable test-run action in the same preceding_actions window) for "
            "operator-A eligibility. Never a whole-file read."
        ),
        "trajectories_dir": str(trajectories_dir),
        "timed_out": timed_out,
        "records_seen": {
            "claude": records_seen["claude"],
            "codex": records_seen["codex"],
            "total": total_records,
        },
        "detectable_test_run": {
            "claude": detectable_test_run["claude"],
            "codex": detectable_test_run["codex"],
            "total": total_test_run,
            "claude_of_total_claude": _frac(detectable_test_run["claude"], records_seen["claude"]),
            "codex_of_total_codex": _frac(detectable_test_run["codex"], records_seen["codex"]),
            "total_of_total_records": _frac(total_test_run, total_records),
        },
        "operator_a_eligible": {
            "claude": operator_a_eligible["claude"],
            "codex": operator_a_eligible["codex"],
            "total": total_op_a,
            "total_of_total_records": _frac(total_op_a, total_records),
        },
        "prose_only_figures": {
            "note": (
                "Five figures previously carried only in prose (README.md, rules.py comments, "
                "CLAUDE.md) with no results-file backing -- computed here from the same streamed "
                "pass as the two blocks above, over the same trajectories/{claude,codex}.jsonl pool."
            ),
            "completion_marker_claims": {
                "records": completion_marker_records,
                "of_total_records": _frac(completion_marker_records, total_records),
                "definition": "claim_text contains a relay_gate.rules._COMPLETION_MARKERS substring",
            },
            "tool_name_contains_test": {
                "records": test_in_tool_name_records,
                "of_total_records": _frac(test_in_tool_name_records, total_records),
                "definition": "record has >=1 preceding_action whose tool name contains 'test' (case-insensitive)",
            },
            "delete_file_tool_name": {
                "records": delete_file_records,
                "of_total_records": _frac(delete_file_records, total_records),
                "definition": f"record has >=1 preceding_action whose tool name is exactly '{DELETE_FILE_TOOL}'",
            },
            "cron_delete_tool_name": {
                "occurrences": cron_delete_occurrences,
                "records": cron_delete_records,
                "of_total_records": _frac(cron_delete_records, total_records),
                "definition": f"occurrences = total actions with tool name '{CRON_DELETE_TOOL}' (case-insensitive); "
                "records = distinct records with >=1 such action",
            },
        },
    }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories-dir", default=DEFAULT_TRAJECTORIES_DIR)
    parser.add_argument("--out", required=True, help="path to write pool_counts.json")
    parser.add_argument("--max-seconds", type=float, default=MAX_SECONDS_DEFAULT)
    args = parser.parse_args(argv)

    trajectories_dir = pathlib.Path(args.trajectories_dir)
    out_path = pathlib.Path(args.out)
    result = run(trajectories_dir, args.max_seconds)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    pf = result["prose_only_figures"]
    print(
        "POOL_COUNTS: records_total={t} detectable_test_run={tr} "
        "(claude={trc} codex={trx}) operator_a_eligible={oa} "
        "completion_marker_claims={cm} tool_name_contains_test={tt} "
        "delete_file_tool_name={df} cron_delete_tool_name occurrences={co} records={cr} "
        "timed_out={to}".format(
            t=result["records_seen"]["total"],
            tr=result["detectable_test_run"]["total_of_total_records"],
            trc=result["detectable_test_run"]["claude_of_total_claude"],
            trx=result["detectable_test_run"]["codex_of_total_codex"],
            oa=result["operator_a_eligible"]["total_of_total_records"],
            cm=pf["completion_marker_claims"]["of_total_records"],
            tt=pf["tool_name_contains_test"]["of_total_records"],
            df=pf["delete_file_tool_name"]["of_total_records"],
            co=pf["cron_delete_tool_name"]["occurrences"],
            cr=pf["cron_delete_tool_name"]["of_total_records"],
            to=result["timed_out"],
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
