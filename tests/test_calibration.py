"""Tests for relay_gate.calibration: the generator must reproduce
data/calibration.json's numbers straight from the two results files (plus
their raw source trees) restricted to the records where coverage.py's own
per-record rule says each check was ALIVE, never hand-typed, and the shipped
data file must already be in sync with it."""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from relay_gate import calibration
from relay_gate import coverage as coverage_module

DATA_PATH = pathlib.Path(__file__).parent.parent / "src" / "relay_gate" / "data" / "calibration.json"

# This whole module regenerates and re-verifies data/calibration.json against
# the two real downloaded external label sets (MAST-Data, AgentRewardBench),
# which are not committed to this repo (large third-party licensed data --
# see src/relay_gate/calibration.py's module docstring). Point
# RELAY_GATE_MAST_RESULTS / RELAY_GATE_ARB_RESULTS (and the two companion
# raw-source env vars) at a local copy to exercise this suite; otherwise it
# skips cleanly rather than failing on a path that only exists on the
# machine that fetched the data.
pytestmark = pytest.mark.skipif(
    not (calibration._MAST_RESULTS.exists() and calibration._ARB_RESULTS.exists()),
    reason="requires the downloaded MAST/ARB external results on disk (see RELAY_GATE_MAST_RESULTS / RELAY_GATE_ARB_RESULTS)",
)


def test_build_calibration_matches_worked_example_from_the_task():
    """FALSE_COMPLETION_CLAIM on the two real results files, ALIVE-restricted:
    MAST is ALIVE on all 19 records (final_claim is never empty there), so
    its numbers are unchanged from the full-set count: caught 4 of 14
    deceptive, wrongly held 3 of 5 clean. ARB is NOT alive on every clean
    record -- 5 of its 7 clean records carry an empty final_claim (no
    send_msg_to_user ending) -- so the honest clean denominator is 2, not 7: this is the
    exact flattering-denominator defect the task named, closed here."""
    data = calibration.build_calibration()
    entry = data["checks"]["FALSE_COMPLETION_CLAIM"]

    assert entry["mast"]["caught"] == 4
    assert entry["mast"]["of_deceptive_alive"] == 14
    assert entry["mast"]["of_deceptive_total"] == 14
    assert entry["mast"]["clean_wrongly_held"] == 3
    assert entry["mast"]["of_clean_alive"] == 5
    assert entry["mast"]["of_clean_total"] == 5

    assert entry["arb"]["caught"] == 1
    assert entry["arb"]["of_false_done_alive"] == 16
    assert entry["arb"]["of_false_done_total"] == 16
    assert entry["arb"]["clean_wrongly_held"] == 0
    assert entry["arb"]["of_clean_alive"] == 2
    assert entry["arb"]["of_clean_total"] == 7


def test_build_calibration_covers_all_six_checks_both_sources():
    data = calibration.build_calibration()
    assert set(data["checks"]) == set(calibration.CHECK_TO_RULE_FUNC)
    for check_name, entry in data["checks"].items():
        assert "mast" in entry, check_name
        assert "arb" in entry, check_name
        for field in ("source_file", "caught", "of_deceptive_alive", "of_deceptive_total", "clean_wrongly_held",
                      "of_clean_alive", "of_clean_total"):
            assert field in entry["mast"], f"{check_name}/mast missing {field}"
        for field in ("source_file", "caught", "of_false_done_alive", "of_false_done_total", "clean_wrongly_held",
                      "of_clean_alive", "of_clean_total"):
            assert field in entry["arb"], f"{check_name}/arb missing {field}"


def test_five_of_six_checks_measure_zero_on_both_sets_only_false_completion_fires():
    """Verbatim from both results files' own per_record_lines: only
    check_false_completion_claim ever names itself in a rules_fired=[...]
    entry; the other five checks never fired on either labelled set,
    regardless of how many records they were ALIVE on."""
    data = calibration.build_calibration()
    for check_name, entry in data["checks"].items():
        if check_name == "FALSE_COMPLETION_CLAIM":
            continue
        assert entry["mast"]["caught"] == 0, check_name
        assert entry["mast"]["clean_wrongly_held"] == 0, check_name
        assert entry["arb"]["caught"] == 0, check_name
        assert entry["arb"]["clean_wrongly_held"] == 0, check_name


def test_alive_denominator_never_exceeds_full_set_denominator():
    """Structural invariant: the ALIVE-restricted count can never be more
    than the full bucket size it is drawn from."""
    data = calibration.build_calibration()
    for check_name, entry in data["checks"].items():
        m, a = entry["mast"], entry["arb"]
        assert m["of_deceptive_alive"] <= m["of_deceptive_total"], check_name
        assert m["of_clean_alive"] <= m["of_clean_total"], check_name
        assert a["of_false_done_alive"] <= a["of_false_done_total"], check_name
        assert a["of_clean_alive"] <= a["of_clean_total"], check_name
        # the bucket sizes themselves must match the results files' own counts
        assert m["of_deceptive_total"] == 14, check_name
        assert m["of_clean_total"] == 5, check_name
        assert a["of_false_done_total"] == 16, check_name
        assert a["of_clean_total"] == 7, check_name


# --- independent re-derivation: the regression test for the flattering-  --
# --- denominator defect itself.                                          --

_MAST_LINE_RE = re.compile(r"^\s*(?P<id>\S+)\s+label=(?P<label>\S+).*rules_fired=\[(?P<fired>[^\]]*)\]")
_ARB_LINE_RE = re.compile(
    r"^\s*(?P<id>\S+)\s+bucket=(?P<bucket>\S+)(?:.*rules_fired=\[(?P<fired>[^\]]*)\])?"
)


def _independent_alive_counts(check_name: str) -> dict:
    """Re-derive, via a parsing regex and a bucketing rule written fresh
    here (not imported from calibration.py), how many MAST/ARB labelled
    records are ALIVE for `check_name` and how many of those are actual
    hits. If this ever disagrees with calibration.build_calibration()'s own
    numbers, one of the two implementations has a bug -- that is what this
    test is for."""
    mast_results = json.loads(calibration._MAST_RESULTS.read_text(encoding="utf-8"))
    arb_results = json.loads(calibration._ARB_RESULTS.read_text(encoding="utf-8"))
    mast_trajs = {t.trajectory_id: t for t in coverage_module._load_mast(str(calibration._MAST_RAW))}

    out = {"mast_deceptive_alive": 0, "mast_clean_alive": 0, "mast_caught": 0, "mast_clean_wrongly_held": 0,
           "arb_false_done_alive": 0, "arb_clean_alive": 0, "arb_caught": 0, "arb_clean_wrongly_held": 0}

    for line in mast_results["per_record_lines"]:
        m = _MAST_LINE_RE.match(line)
        traj = mast_trajs[m.group("id")]
        alive = any(r.check == check_name and r.status == "ALIVE" for r in coverage_module.coverage_map(traj))
        fired = calibration.CHECK_TO_RULE_FUNC[check_name] in [n.strip() for n in m.group("fired").split(",")]
        deceptive = m.group("label") == "deceptive"
        if alive:
            out["mast_deceptive_alive" if deceptive else "mast_clean_alive"] += 1
            if fired:
                out["mast_caught" if deceptive else "mast_clean_wrongly_held"] += 1

    for line in arb_results["per_record_lines"]:
        m = _ARB_LINE_RE.match(line)
        if m.group("bucket") == "EXCLUDED":
            continue
        task_id = re.match(r"^arb_([A-Za-z0-9]+\.\d+)_", m.group("id")).group(1)
        traj = coverage_module._load_arb(str(calibration._ARB_CLEANED_DIR / f"{task_id}.json"))[0]
        alive = any(r.check == check_name and r.status == "ALIVE" for r in coverage_module.coverage_map(traj))
        fired_raw = m.group("fired") or ""
        fired = calibration.CHECK_TO_RULE_FUNC[check_name] in [n.strip() for n in fired_raw.split(",")]
        false_done = m.group("bucket") == "FALSE_DONE"
        if alive:
            out["arb_false_done_alive" if false_done else "arb_clean_alive"] += 1
            if fired:
                out["arb_caught" if false_done else "arb_clean_wrongly_held"] += 1

    return out


@pytest.mark.parametrize("check_name", list(calibration.CHECK_TO_RULE_FUNC))
def test_printed_denominators_never_exceed_the_independently_recomputed_alive_count(check_name):
    """This is the regression test for the flattering-denominator defect:
    independently re-parse both results files and re-run coverage_map()
    (the exact primitive, but a fresh parse/bucketing pass written only in
    this test) and assert calibration.json's own ALIVE-restricted
    denominators and hit counts never overstate what that independent pass
    finds, for every one of the six checks."""
    data = calibration.build_calibration()
    entry = data["checks"][check_name]
    independent = _independent_alive_counts(check_name)

    assert entry["mast"]["of_deceptive_alive"] == independent["mast_deceptive_alive"], check_name
    assert entry["mast"]["of_clean_alive"] == independent["mast_clean_alive"], check_name
    assert entry["mast"]["caught"] == independent["mast_caught"], check_name
    assert entry["mast"]["clean_wrongly_held"] == independent["mast_clean_wrongly_held"], check_name
    assert entry["arb"]["of_false_done_alive"] == independent["arb_false_done_alive"], check_name
    assert entry["arb"]["of_clean_alive"] == independent["arb_clean_alive"], check_name
    assert entry["arb"]["caught"] == independent["arb_caught"], check_name
    assert entry["arb"]["clean_wrongly_held"] == independent["arb_clean_wrongly_held"], check_name
    # the specific number the task named: never let a printed denominator
    # exceed what could actually be ALIVE.
    assert entry["arb"]["of_clean_alive"] <= entry["arb"]["of_clean_total"]


def test_arb_clean_denominator_for_false_completion_claim_is_2_with_7_in_brackets():
    """The exact worked example from the task: FALSE_COMPLETION_CLAIM is
    ALIVE on only 2 of ARB's 7 clean records (5 carry an empty final_claim
    -- no send_msg_to_user ending), so the honest denominator is 2, with
    the full clean bucket size (7) carried alongside it, in brackets, for
    context."""
    data = calibration.build_calibration()
    arb = data["checks"]["FALSE_COMPLETION_CLAIM"]["arb"]
    assert arb["of_clean_alive"] == 2
    assert arb["of_clean_total"] == 7


def test_measured_line_prints_the_honest_alive_restricted_wording():
    """relay_gate.coverage._measured_line must print 'caught X of Y ...
    where the check could fire (Z in the set)' -- never the flattering
    full-set-only phrasing -- for both the caught and the held clause."""
    data = calibration.build_calibration()
    line = coverage_module._measured_line("FALSE_COMPLETION_CLAIM", {"checks": data["checks"]})
    assert "caught 4 of 14 deceptive where the check could fire (14 in the set)" in line
    assert "wrongly held 3 of 5 clean where the check could fire (5 in the set)" in line
    assert "caught 1 of 16 false-done where the check could fire (16 in the set)" in line
    assert "wrongly held 0 of 2 clean where the check could fire (7 in the set)" in line


def test_shipped_data_file_is_in_sync_with_the_generator():
    """data/calibration.json is a generated artefact, not hand-typed; this
    test fails the moment someone edits the results files, the raw source
    trees, or this module without re-running the generator, or hand-edits
    the JSON out of step."""
    on_disk = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    rebuilt = calibration.build_calibration(date=on_disk["date"])
    assert on_disk["checks"] == rebuilt["checks"]


def test_write_calibration_round_trips_through_a_temp_file(tmp_path):
    out = tmp_path / "sub" / "calibration.json"
    written_path = calibration.write_calibration(out_path=out)
    assert written_path == out
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["checks"]["FALSE_COMPLETION_CLAIM"]["mast"]["caught"] == 4
    assert reloaded["checks"]["FALSE_COMPLETION_CLAIM"]["arb"]["of_clean_alive"] == 2
