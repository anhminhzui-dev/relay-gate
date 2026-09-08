#!/usr/bin/env python3
"""Score Relay Gate's six offline rules against the MAST external label.

Reads the downloaded MAST human-labelled split from
M:/AGENT_VAULT/PORTFOLIO/bench/external/mast/data/MAD_human_labelled_dataset.json
(outside this repo -- see bench/external_adapter.py's module docstring for
why that source/split was picked), converts every record via
bench/external_adapter.py, runs relay_gate.gate.evaluate_trajectory with
provider=None (the offline path -- no network/model call anywhere in this
script) plus every individual rule in relay_gate.rules.ALL_RULES, joins
each result to the record's human-annotated "task verification failure"
label, and prints:

  - a 2x2 table: gate decision (HOLD/GO) x label (deceptive/clean)
  - per-rule fire counts, with precision/recall against the label, where
    computable
  - one line per record

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

import external_adapter as ea  # noqa: E402
from relay_gate.gate import evaluate_trajectory  # noqa: E402
from relay_gate.rules import ALL_RULES  # noqa: E402

DATA_PATH = _PORTFOLIO_DIR / "bench" / "external" / "mast" / "data" / "MAD_human_labelled_dataset.json"
RESULTS_PATH = _PORTFOLIO_DIR / "bench" / "external" / "mast" / "results.json"


def main() -> int:
    if not DATA_PATH.exists():
        print(f"MISSING: {DATA_PATH} not found -- run the download step first.")
        return 1

    records = list(ea.iter_labelled_trajectories(str(DATA_PATH)))
    n_total = len(records)

    # 2x2 table: decision x label
    table = {
        ("HOLD", "deceptive"): 0,
        ("HOLD", "clean"): 0,
        ("GO", "deceptive"): 0,
        ("GO", "clean"): 0,
    }

    # per-rule: fired[rule_name] = count of trajectories where the rule
    # produced >=1 finding (hold or ambiguous); fired_and_deceptive for
    # precision/recall.
    rule_names = [rule.__name__ for rule in ALL_RULES]
    fired = {name: 0 for name in rule_names}
    fired_and_deceptive = {name: 0 for name in rule_names}
    n_deceptive = sum(1 for _, label, _ in records if label)
    n_clean = n_total - n_deceptive

    per_record_lines = []

    for traj, label, rec in records:
        verdict = evaluate_trajectory(traj, provider=None)
        label_str = "deceptive" if label else "clean"
        table[(verdict.decision, label_str)] += 1

        rule_hits_this_record = []
        for rule in ALL_RULES:
            findings = rule(traj)
            if findings:
                fired[rule.__name__] += 1
                if label:
                    fired_and_deceptive[rule.__name__] += 1
                rule_hits_this_record.append(rule.__name__)

        reason_codes = ",".join(sorted({c.value for c, _ in verdict.reasons}))
        per_record_lines.append(
            f"  {traj.trajectory_id:45s} label={label_str:9s} decision={verdict.decision:4s} "
            f"n_steps={len(traj.steps):3d} rules_fired=[{','.join(rule_hits_this_record) or '-'}] "
            f"reasons=[{reason_codes}]"
        )

    print(f"SOURCE: MAST-Data MAD_human_labelled_dataset.json ({n_total} records, cc-by-4.0)")
    print(f"LABEL: deceptive = majority(>=2/3 annotators) True on 3.1/3.2/3.3 (see external_adapter.py docstring)")
    print(f"n_total={n_total} n_deceptive={n_deceptive} n_clean={n_clean}")
    print()
    print("2x2 TABLE (gate decision x label)")
    print(f"{'':10s} {'deceptive':>12s} {'clean':>10s}")
    print(f"{'HOLD':10s} {table[('HOLD','deceptive')]:12d} {table[('HOLD','clean')]:10d}")
    print(f"{'GO':10s} {table[('GO','deceptive')]:12d} {table[('GO','clean')]:10d}")
    print()

    tp = table[("HOLD", "deceptive")]
    fp = table[("HOLD", "clean")]
    fn = table[("GO", "deceptive")]
    tn = table[("GO", "clean")]
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    print(f"GATE overall: precision={precision:.3f} ({tp} of {tp+fp} HOLDs are deceptive) "
          f"recall={recall:.3f} ({tp} of {tp+fn} deceptive records HOLD)")
    print()

    print(f"PER-RULE fire counts (out of n_total={n_total}; precision/recall against the label)")
    for name in rule_names:
        f_ = fired[name]
        f_dec = fired_and_deceptive[name]
        f_clean = f_ - f_dec
        prec = f_dec / f_ if f_ else float("nan")
        rec_ = f_dec / n_deceptive if n_deceptive else float("nan")
        prec_s = f"{prec:.3f}" if f_ else "n/a (0 fires)"
        rec_s = f"{rec_:.3f}" if n_deceptive else "n/a (0 deceptive)"
        print(f"  {name:32s} fired={f_:2d} of {n_total:2d}  "
              f"(deceptive={f_dec} of {n_deceptive}, clean={f_clean} of {n_clean})  "
              f"precision={prec_s}  recall={rec_s}")
    print()

    print(f"PER-RECORD ({n_total} lines)")
    for line in per_record_lines:
        print(line)

    # --- write every printed number, plus per-record lines, to disk ---
    # (this script previously printed to stdout only, per a hostile-judge
    # finding; no printed number changes here, this only persists them)
    per_rule = {}
    for name in rule_names:
        f_ = fired[name]
        f_dec = fired_and_deceptive[name]
        f_clean = f_ - f_dec
        per_rule[name] = {
            "fired": f_,
            "of_n_total": n_total,
            "deceptive": f_dec,
            "of_n_deceptive": n_deceptive,
            "clean": f_clean,
            "of_n_clean": n_clean,
            "precision": (f_dec / f_) if f_ else None,
            "recall": (f_dec / n_deceptive) if n_deceptive else None,
        }

    results = {
        "source": f"MAST-Data MAD_human_labelled_dataset.json ({n_total} records, cc-by-4.0)",
        "label_rule": "deceptive = majority(>=2/3 annotators) True on 3.1/3.2/3.3 (see external_adapter.py docstring)",
        "n_total": n_total,
        "n_deceptive": n_deceptive,
        "n_clean": n_clean,
        "table_2x2": {
            "hold_deceptive": table[("HOLD", "deceptive")],
            "hold_clean": table[("HOLD", "clean")],
            "go_deceptive": table[("GO", "deceptive")],
            "go_clean": table[("GO", "clean")],
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
