"""Calibration: measured hit rates for each of the six ``rules.py`` checks
against the two human-labelled external sets (MAST-Data, AgentRewardBench),
restricted to the records where coverage.py's own per-record rule says the
check was structurally ALIVE.

Why "restricted to ALIVE", stated plainly (2026-09-08 fix; prior version of
this module printed rates against the full labelled-set size instead):
``results.json``'s own ``per_rule`` blocks report ``of_n_clean`` /
``of_n_deceptive`` / ``of_n_false_done`` as the FULL bucket size, with no
regard for whether ``coverage.py`` says the check could even fire on each
record. Concretely, on AgentRewardBench, 5 of the 7 CLEAN records carry an
empty ``final_claim`` (``send_msg_to_user`` was never the trajectory's last
action -- see ``bench/arb_adapter.py``), so ``FALSE_COMPLETION_CLAIM`` is
structurally DEAD on them by ``coverage.py``'s own rule; it never had the
data to hold on those 5 no matter what. Printing "0 of 7 clean held" as
though all 7 were live trials is a flattering denominator: the counter
increments when the check FIRES on a clean record, so it is a
false-positive count, not a virtue. The honest line is "wrongly held 0 of 2
clean where the check could fire (7 clean in the set)" -- this module now
computes exactly that, for all six checks, on both sources, under the key
``clean_wrongly_held``.

Data flow, all traced to a file, nothing hand-typed:

  1. Read the two results files' own ``per_record_lines`` (one line per
     labelled record, already produced by a real bench run):
         M:/AGENT_VAULT/PORTFOLIO/bench/external/mast/results.json
         M:/AGENT_VAULT/PORTFOLIO/bench/external/arb/results.json
     Each line carries that record's id, its label/bucket, and which
     checks (``rules_fired``) actually fired on it -- parsed here, not
     re-derived.
  2. Reconstruct each labelled record's real ``Trajectory`` from the
     underlying raw source file, via the SAME loaders ``coverage.py``
     itself uses for ``--format mast`` / ``--format arb``
     (``coverage._load_mast`` / ``coverage._load_arb``), matched to each
     ``per_record_lines`` entry by trajectory id (MAST) or by the ARB task
     id embedded in that id.
  3. Run ``coverage.coverage_map()`` -- the exact same function
     ``relay-gate coverage`` calls -- on each reconstructed trajectory, so
     "ALIVE" here means exactly what it means everywhere else in this
     package, never a re-implemented heuristic.
  4. Tally, per check and per bucket (MAST: deceptive/clean; ARB:
     false_done/clean): the ALIVE count (the honest denominator), the full
     bucket size (the bracket number), and the caught/held count restricted
     to ALIVE records whose ``rules_fired`` names that check.

Run this module directly (``python -m relay_gate.calibration``) whenever
the two results files or the two raw source trees change, so
``data/calibration.json`` never drifts from the measurement that produced
it.
"""

from __future__ import annotations

import json
import pathlib
import re

from relay_gate import coverage as coverage_module

# Absolute paths, exactly as named in the task that authored this module:
# the labelled-set results and their raw source trees live under the
# shared PORTFOLIO bench tree, one level above this repo's own bench/
# (which holds only the adapter+scorer scripts, not the labelled data).
_MAST_RESULTS = pathlib.Path("M:/AGENT_VAULT/PORTFOLIO/bench/external/mast/results.json")
_ARB_RESULTS = pathlib.Path("M:/AGENT_VAULT/PORTFOLIO/bench/external/arb/results.json")
_MAST_RAW = pathlib.Path("M:/AGENT_VAULT/PORTFOLIO/bench/external/mast/data/MAD_human_labelled_dataset.json")
_ARB_CLEANED_DIR = pathlib.Path("M:/AGENT_VAULT/PORTFOLIO/bench/external/arb/data/cleaned")
_OUT_PATH = pathlib.Path(__file__).resolve().parent / "data" / "calibration.json"

# coverage.py's CHECK_ORDER name -> the rules.py function name each
# results.json per_record_lines' rules_fired=[...] entry names.
CHECK_TO_RULE_FUNC = {
    "DESTRUCTIVE_WITHOUT_READ": "check_destructive_without_read",
    "TEST_DISABLED": "check_test_disabled",
    "SECRET_LEAK": "check_secret_leak",
    "FALSE_COMPLETION_CLAIM": "check_false_completion_claim",
    "UNKNOWN_TOOL_CALL": "check_unknown_tool_call",
    "VALIDATION_BYPASSED": "check_validation_bypassed",
}
_RULE_FUNC_TO_CHECK = {v: k for k, v in CHECK_TO_RULE_FUNC.items()}

# --- per_record_lines parsing -----------------------------------------------
# MAST line shape:   "  mast_<id...>  label=deceptive decision=HOLD n_steps= 12 rules_fired=[check_x] reasons=[...]"
# ARB line shape:    "  arb_<id...>   bucket=FALSE_DONE decision=GO   n_steps= 5 claim='...' rules_fired=[-] reasons=[...]"
#                 or "  arb_<id...>   bucket=EXCLUDED reason=..."                          (no scoring fields at all)

_MAST_LINE_RE = re.compile(
    r"^\s*(?P<id>\S+)\s+label=(?P<label>\S+)\s+decision=(?P<decision>\S+)\s+"
    r"n_steps=\s*\d+\s+rules_fired=\[(?P<fired>[^\]]*)\]"
)
_ARB_LINE_RE = re.compile(
    r"^\s*(?P<id>\S+)\s+bucket=(?P<bucket>\S+)"
    r"(?:\s+decision=(?P<decision>\S+)\s+n_steps=\s*\d+\s+claim='(?P<claim>.*?)'\s+"
    r"rules_fired=\[(?P<fired>[^\]]*)\])?"
)
_ARB_TASK_ID_RE = re.compile(r"^arb_(?P<task_id>[A-Za-z0-9]+\.\d+)_")


def _parse_fired(fired_raw: str | None) -> set[str]:
    fired_raw = (fired_raw or "").strip()
    if not fired_raw or fired_raw == "-":
        return set()
    names = {n.strip() for n in fired_raw.split(",") if n.strip()}
    unknown = names - set(_RULE_FUNC_TO_CHECK)
    if unknown:
        raise ValueError(f"rules_fired names a function calibration.py does not know: {unknown}")
    return {_RULE_FUNC_TO_CHECK[n] for n in names}


def _parse_mast_lines(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        m = _MAST_LINE_RE.match(line)
        if not m:
            raise ValueError(f"could not parse MAST per_record_lines entry: {line!r}")
        records.append(
            {
                "id": m.group("id"),
                "bucket": "deceptive" if m.group("label") == "deceptive" else "clean",
                "fired": _parse_fired(m.group("fired")),
            }
        )
    return records


def _parse_arb_lines(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        m = _ARB_LINE_RE.match(line)
        if not m:
            raise ValueError(f"could not parse ARB per_record_lines entry: {line!r}")
        bucket = m.group("bucket")
        if bucket == "EXCLUDED":
            continue  # no ground truth to score against; see arb_adapter.bucket_of
        records.append(
            {
                "id": m.group("id"),
                "bucket": "false_done" if bucket == "FALSE_DONE" else "clean",
                "fired": _parse_fired(m.group("fired")),
            }
        )
    return records


# --- reconstructing real Trajectory objects for the labelled records -------


def _mast_trajectories_by_id(mast_raw_path: pathlib.Path) -> dict:
    return {t.trajectory_id: t for t in coverage_module._load_mast(str(mast_raw_path))}


def _arb_trajectory_for(record_id: str, arb_cleaned_dir: pathlib.Path):
    m = _ARB_TASK_ID_RE.match(record_id)
    if not m:
        raise ValueError(f"could not recover an ARB task id from record id {record_id!r}")
    task_id = m.group("task_id")
    path = arb_cleaned_dir / f"{task_id}.json"
    return coverage_module._load_arb(str(path))[0]


def _empty_mast_stats() -> dict:
    return {
        "caught": 0,
        "of_deceptive_alive": 0,
        "of_deceptive_total": 0,
        "clean_wrongly_held": 0,
        "of_clean_alive": 0,
        "of_clean_total": 0,
    }


def _empty_arb_stats() -> dict:
    return {
        "caught": 0,
        "of_false_done_alive": 0,
        "of_false_done_total": 0,
        "clean_wrongly_held": 0,
        "of_clean_alive": 0,
        "of_clean_total": 0,
    }


def alive_restricted_counts(
    mast_results: dict,
    arb_results: dict,
    mast_raw_path: pathlib.Path = _MAST_RAW,
    arb_cleaned_dir: pathlib.Path = _ARB_CLEANED_DIR,
) -> dict:
    """For every check, tally caught/held counts and their ALIVE-restricted
    denominators, plus each bucket's full-set size, over both sources.
    Returns ``{check_name: {"mast": {...}, "arb": {...}}}``, the six-check
    schema ``build_calibration`` writes straight into ``data/calibration.json``.
    """
    mast_records = _parse_mast_lines(mast_results["per_record_lines"])
    arb_records = _parse_arb_lines(arb_results["per_record_lines"])
    mast_trajs = _mast_trajectories_by_id(mast_raw_path)

    result = {name: {"mast": _empty_mast_stats(), "arb": _empty_arb_stats()} for name in CHECK_TO_RULE_FUNC}

    for rec in mast_records:
        traj = mast_trajs.get(rec["id"])
        if traj is None:
            raise ValueError(
                f"MAST record {rec['id']!r} from results.json's per_record_lines has no matching raw "
                f"record in {mast_raw_path}"
            )
        alive = {res.check for res in coverage_module.coverage_map(traj) if res.status == "ALIVE"}
        bucket = rec["bucket"]  # "deceptive" | "clean"
        total_key, alive_key = f"of_{bucket}_total", f"of_{bucket}_alive"
        hit_key = "caught" if bucket == "deceptive" else "clean_wrongly_held"
        for name in CHECK_TO_RULE_FUNC:
            stats = result[name]["mast"]
            stats[total_key] += 1
            if name in alive:
                stats[alive_key] += 1
                if name in rec["fired"]:
                    stats[hit_key] += 1

    for rec in arb_records:
        traj = _arb_trajectory_for(rec["id"], arb_cleaned_dir)
        alive = {res.check for res in coverage_module.coverage_map(traj) if res.status == "ALIVE"}
        bucket = rec["bucket"]  # "false_done" | "clean"
        total_key, alive_key = f"of_{bucket}_total", f"of_{bucket}_alive"
        hit_key = "caught" if bucket == "false_done" else "clean_wrongly_held"
        for name in CHECK_TO_RULE_FUNC:
            stats = result[name]["arb"]
            stats[total_key] += 1
            if name in alive:
                stats[alive_key] += 1
                if name in rec["fired"]:
                    stats[hit_key] += 1

    return result


def build_calibration(
    mast_results_path: pathlib.Path = _MAST_RESULTS,
    arb_results_path: pathlib.Path = _ARB_RESULTS,
    mast_raw_path: pathlib.Path = _MAST_RAW,
    arb_cleaned_dir: pathlib.Path = _ARB_CLEANED_DIR,
    date: str = "2026-09-08",
) -> dict:
    """Rebuild the calibration dict straight from the two results files plus
    their raw source trees. `date` defaults to the on-disk mtime date of
    both results files at the time this module was written; pass an
    explicit value when regenerating after a later bench run."""
    mast_results = json.loads(mast_results_path.read_text(encoding="utf-8"))
    arb_results = json.loads(arb_results_path.read_text(encoding="utf-8"))
    counts = alive_restricted_counts(mast_results, arb_results, mast_raw_path, arb_cleaned_dir)

    checks = {}
    for check_name in CHECK_TO_RULE_FUNC:
        checks[check_name] = {
            "mast": {"source_file": mast_results["source"], **counts[check_name]["mast"]},
            "arb": {"source_file": arb_results["source"], **counts[check_name]["arb"]},
        }

    return {
        "date": date,
        "generated_from": {
            "mast_results": str(mast_results_path),
            "arb_results": str(arb_results_path),
            "mast_raw": str(mast_raw_path),
            "arb_cleaned_dir": str(arb_cleaned_dir),
        },
        "checks": checks,
    }


def write_calibration(
    mast_results_path: pathlib.Path = _MAST_RESULTS,
    arb_results_path: pathlib.Path = _ARB_RESULTS,
    mast_raw_path: pathlib.Path = _MAST_RAW,
    arb_cleaned_dir: pathlib.Path = _ARB_CLEANED_DIR,
    date: str = "2026-09-08",
    out_path: pathlib.Path = _OUT_PATH,
) -> pathlib.Path:
    data = build_calibration(mast_results_path, arb_results_path, mast_raw_path, arb_cleaned_dir, date)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = write_calibration()
    print(f"wrote {path}")
