#!/usr/bin/env python3
"""Score Relay Gate's six offline rules against the AgentRewardBench label.

Reads every downloaded AgentRewardBench trajectory JSON under
M:/AGENT_VAULT/PORTFOLIO/bench/external/arb/data/cleaned/ (outside this
repo -- see bench/arb_adapter.py's module docstring for source, licence,
and exactly which files were fetched and why), converts each via
bench/arb_adapter.py, buckets each into FALSE_DONE / CLEAN / EXCLUDED
against the expert annotation in data/annotations.csv, runs
relay_gate.gate.evaluate_trajectory with provider=None (the fully offline
path -- no network/model call anywhere in this script) plus every
individual rule in relay_gate.rules.ALL_RULES over the FALSE_DONE+CLEAN
records, and prints:

  - the bucket counts (FALSE_DONE / CLEAN / EXCLUDED, with EXCLUDED
    reasons broken down)
  - a 2x2 table: gate decision (HOLD/GO) x label (FALSE_DONE/CLEAN)
  - per-rule fire counts, with precision/recall against the label, where
    computable
  - one line per record (all records, including EXCLUDED ones, each
    marked with its bucket and reason)

No paid call, no login, no write outside this file's own stdout.
"""

from __future__ import annotations

import json
import pathlib
import sys

_EXTERNAL_DIR = pathlib.Path(__file__).resolve().parent
_BENCH_DIR = _EXTERNAL_DIR.parent
_REPO_DIR = _BENCH_DIR.parent
_SRC_DIR = _REPO_DIR / "src"
_PORTFOLIO_DIR = _REPO_DIR.parent.parent
for _p in (_BENCH_DIR, _SRC_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import arb_adapter as aa  # noqa: E402
from relay_gate.gate import evaluate_trajectory  # noqa: E402
from relay_gate.rules import ALL_RULES  # noqa: E402

DATA_DIR = _PORTFOLIO_DIR / "bench" / "external" / "arb" / "data" / "cleaned"
ANNOTATIONS_PATH = _PORTFOLIO_DIR / "bench" / "external" / "arb" / "data" / "annotations.csv"
RESULTS_PATH = _PORTFOLIO_DIR / "bench" / "external" / "arb" / "results.json"


def main() -> int:
    if not DATA_DIR.exists() or not any(DATA_DIR.glob("*.json")):
        print(f"MISSING: {DATA_DIR} has no downloaded trajectory files -- run the download step first.")
        return 1
    if not ANNOTATIONS_PATH.exists():
        print(f"MISSING: {ANNOTATIONS_PATH} not found -- run the download step first.")
        return 1

    records = list(aa.iter_labelled_trajectories(str(DATA_DIR), str(ANNOTATIONS_PATH)))
    n_total = len(records)

    by_bucket: dict[str, list] = {"FALSE_DONE": [], "CLEAN": [], "EXCLUDED": []}
    for traj, bucket, detail in records:
        by_bucket[bucket].append((traj, detail))

    n_false_done = len(by_bucket["FALSE_DONE"])
    n_clean = len(by_bucket["CLEAN"])
    n_excluded = len(by_bucket["EXCLUDED"])

    excluded_reason_counts: dict[str, int] = {}
    for _, detail in by_bucket["EXCLUDED"]:
        key = detail["reason"].split(" (")[0] if detail["reason"].startswith("annotator disagreement") else detail["reason"]
        # collapse per-value disagreement reasons into one bucket, keep the rest distinct
        if detail["reason"].startswith("annotator disagreement"):
            key = "annotator disagreement (mixed/Unsure votes)"
        elif detail["reason"].startswith("expert=Unsuccessful but last action kind"):
            key = detail["reason"]
        excluded_reason_counts[key] = excluded_reason_counts.get(key, 0) + 1

    max_steps_recorded = max((d.get("n_steps_recorded") or 0) for _, d in (by_bucket["FALSE_DONE"] + by_bucket["CLEAN"] + by_bucket["EXCLUDED"])) if records else 0
    max_steps_in_trajectory = max((len(t.steps) for t, _ in (by_bucket["FALSE_DONE"] + by_bucket["CLEAN"] + by_bucket["EXCLUDED"])), default=0)

    # 2x2 table over FALSE_DONE + CLEAN only (EXCLUDED has no settled label)
    table = {("HOLD", "FALSE_DONE"): 0, ("HOLD", "CLEAN"): 0, ("GO", "FALSE_DONE"): 0, ("GO", "CLEAN"): 0}

    rule_names = [rule.__name__ for rule in ALL_RULES]
    fired = {name: 0 for name in rule_names}
    fired_and_false_done = {name: 0 for name in rule_names}

    per_record_lines = []

    for traj, bucket, detail in records:
        if bucket == "EXCLUDED":
            per_record_lines.append(
                f"  {traj.trajectory_id:70s} bucket=EXCLUDED reason={detail['reason']}"
            )
            continue

        verdict = evaluate_trajectory(traj, provider=None)
        table[(verdict.decision, bucket)] += 1

        rule_hits_this_record = []
        for rule in ALL_RULES:
            findings = rule(traj)
            if findings:
                fired[rule.__name__] += 1
                if bucket == "FALSE_DONE":
                    fired_and_false_done[rule.__name__] += 1
                rule_hits_this_record.append(rule.__name__)

        reason_codes = ",".join(sorted({c.value for c, _ in verdict.reasons}))
        per_record_lines.append(
            f"  {traj.trajectory_id:70s} bucket={bucket:10s} decision={verdict.decision:4s} "
            f"n_steps={len(traj.steps):2d} claim={traj.final_claim[:50]!r:52s} "
            f"rules_fired=[{','.join(rule_hits_this_record) or '-'}] reasons=[{reason_codes}]"
        )

    print(
        f"SOURCE: AgentRewardBench (arXiv 2504.08942, McGill NLP), CC BY 4.0. "
        f"benchmark=webarena exp_name=GenericAgent-gpt-4o-2024-11-20_on_webarena. "
        f"{n_total} downloaded trajectory records (of 100 unique task_ids annotated for this "
        f"benchmark/agent pair in annotations.csv's 1,408 rows)."
    )
    print(
        "LABEL RULE: FALSE_DONE = last action is send_msg_to_user (agent ended as if the task "
        "was done) AND expert annotators unanimously say Unsuccessful. CLEAN = expert annotators "
        "unanimously say Successful. EXCLUDED = everything else (see reasons below). "
        "See bench/arb_adapter.py bucket_of() for the exact rule."
    )
    print(f"n_total={n_total}  n_FALSE_DONE={n_false_done}  n_CLEAN={n_clean}  n_EXCLUDED={n_excluded}")
    print(f"max n_steps recorded in summary_info across all {n_total} records: {max_steps_recorded} "
          f"(adapter's MAX_STEPS_PER_TRAJECTORY={aa.MAX_STEPS_PER_TRAJECTORY} cap; "
          f"max real steps kept in any built Trajectory: {max_steps_in_trajectory} -- cap never exercised on this run)")
    print()
    print(f"EXCLUDED breakdown (of n_EXCLUDED={n_excluded}):")
    for reason, cnt in sorted(excluded_reason_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cnt:3d}  {reason}")
    print()

    print("2x2 TABLE (gate decision x label), n=%d (FALSE_DONE=%d + CLEAN=%d; EXCLUDED not scored)" % (
        n_false_done + n_clean, n_false_done, n_clean))
    print(f"{'':10s} {'FALSE_DONE':>12s} {'CLEAN':>10s}")
    print(f"{'HOLD':10s} {table[('HOLD','FALSE_DONE')]:12d} {table[('HOLD','CLEAN')]:10d}")
    print(f"{'GO':10s} {table[('GO','FALSE_DONE')]:12d} {table[('GO','CLEAN')]:10d}")
    print()

    tp = table[("HOLD", "FALSE_DONE")]
    fp = table[("HOLD", "CLEAN")]
    fn = table[("GO", "FALSE_DONE")]
    tn = table[("GO", "CLEAN")]
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    print(f"GATE overall: precision={precision:.3f} ({tp} of {tp+fp} HOLDs are FALSE_DONE)  "
          f"recall={recall:.3f} ({tp} of {tp+fn} FALSE_DONE records HOLD)  "
          f"[tn={tn} CLEAN records correctly GO]")
    print()

    n_scored = n_false_done + n_clean
    print(f"PER-RULE fire counts (out of n_scored={n_scored} = FALSE_DONE{n_false_done}+CLEAN{n_clean}; "
          f"precision/recall against FALSE_DONE)")
    for name in rule_names:
        f_ = fired[name]
        f_fd = fired_and_false_done[name]
        f_clean = f_ - f_fd
        prec = f_fd / f_ if f_ else float("nan")
        rec_ = f_fd / n_false_done if n_false_done else float("nan")
        prec_s = f"{prec:.3f}" if f_ else "n/a (0 fires)"
        rec_s = f"{rec_:.3f}" if n_false_done else "n/a (0 FALSE_DONE)"
        print(f"  {name:32s} fired={f_:2d} of {n_scored:2d}  "
              f"(FALSE_DONE={f_fd} of {n_false_done}, CLEAN={f_clean} of {n_clean})  "
              f"precision={prec_s}  recall={rec_s}")
    print()

    print(f"PER-RECORD ({n_total} lines, includes EXCLUDED)")
    for line in per_record_lines:
        print(line)

    # --- write every printed number, plus per-record lines, to disk ---
    per_rule = {}
    for name in rule_names:
        f_ = fired[name]
        f_fd = fired_and_false_done[name]
        f_clean = f_ - f_fd
        per_rule[name] = {
            "fired": f_,
            "of_n_scored": n_scored,
            "false_done": f_fd,
            "of_n_false_done": n_false_done,
            "clean": f_clean,
            "of_n_clean": n_clean,
            "precision": (f_fd / f_) if f_ else None,
            "recall": (f_fd / n_false_done) if n_false_done else None,
        }

    results = {
        "source": (
            "AgentRewardBench (arXiv 2504.08942, McGill NLP), CC BY 4.0. "
            "benchmark=webarena exp_name=GenericAgent-gpt-4o-2024-11-20_on_webarena."
        ),
        "n_total_downloaded": n_total,
        "n_false_done": n_false_done,
        "n_clean": n_clean,
        "n_excluded": n_excluded,
        "excluded_breakdown": excluded_reason_counts,
        "max_steps_recorded_in_summary_info": max_steps_recorded,
        "max_steps_kept_in_any_trajectory": max_steps_in_trajectory,
        "n_scored": n_scored,
        "table_2x2": {
            "hold_false_done": table[("HOLD", "FALSE_DONE")],
            "hold_clean": table[("HOLD", "CLEAN")],
            "go_false_done": table[("GO", "FALSE_DONE")],
            "go_clean": table[("GO", "CLEAN")],
        },
        "gate_overall": {
            "precision": precision,
            "precision_of": f"{tp} of {tp + fp}",
            "recall": recall,
            "recall_of": f"{tp} of {tp + fn}",
            "tn": tn,
        },
        "per_rule": per_rule,
        "per_record_lines": per_record_lines,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nWROTE: {RESULTS_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
