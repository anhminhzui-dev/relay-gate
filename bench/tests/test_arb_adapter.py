"""Tests for bench/arb_adapter.py.

Uses hand-made AgentRewardBench-shaped fixture records (not downloaded
data) so the adapter's action parsing, final-claim extraction, and label
bucketing are checked independently of whatever is on disk under the
directory named by ``RELAY_GATE_ARB_CLEANED_DIR``'s parent (default
``./external_data/arb/data/``). A second, real-shaped
smoke test runs against the actual downloaded data when present, skipped
otherwise.

No network call is made by anything imported here.
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

import pytest

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_BENCH_DIR = _TESTS_DIR.parent
_REPO_DIR = _BENCH_DIR.parent
_SRC_DIR = _REPO_DIR / "src"
for _p in (_BENCH_DIR, _SRC_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import arb_adapter as aa  # noqa: E402
from relay_gate.gate import evaluate_trajectory  # noqa: E402

# Downloaded data lives OUTSIDE the repo (fetch rule), see arb_adapter.py
# module docstring for the exact source and how it was fetched.
_PORTFOLIO_DIR = _REPO_DIR.parent.parent
REAL_DATA_DIR = _PORTFOLIO_DIR / "bench" / "external" / "arb" / "data" / "cleaned"
REAL_ANNOTATIONS = _PORTFOLIO_DIR / "bench" / "external" / "arb" / "data" / "annotations.csv"


def _rec(steps: list[dict], benchmark: str = "webarena", exp: str = "GenericAgent-gpt-4o-2024-11-20_on_webarena") -> dict:
    return {
        "benchmark": benchmark,
        "agent": "GenericAgent-gpt-4o-2024-11-20",
        "experiment": exp,
        "goal": "a fixture goal",
        "summary_info": {"n_steps": len(steps)},
        "steps": steps,
    }


# ---------------------------------------------------------------------
# _parse_action
# ---------------------------------------------------------------------

def test_parse_action_quoted_single():
    tool, args = aa._parse_action("click('147')")
    assert tool == "click"
    assert args["text"] == "147"
    assert args["raw"] == "click('147')"


def test_parse_action_quoted_double_with_content():
    tool, args = aa._parse_action('send_msg_to_user("The answer is 9 minutes.")')
    assert tool == "send_msg_to_user"
    assert args["text"] == "The answer is 9 minutes."


def test_parse_action_no_args_no_text_key():
    tool, args = aa._parse_action("noop()")
    assert tool == "noop"
    assert "text" not in args


def test_parse_action_malformed_falls_back():
    tool, args = aa._parse_action("not an action at all")
    assert tool == "unknown_action"
    assert args == {"raw": "not an action at all"}


# ---------------------------------------------------------------------
# _last_action_kind
# ---------------------------------------------------------------------

def test_last_action_kind_send_msg():
    rec = _rec([
        {"num": 0, "reasoning": "look", "action": "goto(\"https://x\")"},
        {"num": 1, "reasoning": "answer", "action": 'send_msg_to_user("It is 9 minutes.")'},
        {"num": 2, "reasoning": None, "action": None},  # trailing observation-only step
    ])
    kind, text = aa._last_action_kind(rec)
    assert kind == "SEND_MSG"
    assert text == "It is 9 minutes."


def test_last_action_kind_infeasible():
    rec = _rec([{"num": 0, "action": 'report_infeasible("No results found.")'}])
    kind, text = aa._last_action_kind(rec)
    assert kind == "INFEASIBLE"
    assert text == "No results found."


def test_last_action_kind_other():
    rec = _rec([{"num": 0, "action": "click('12')"}, {"num": 1, "action": "scroll(0, 200)"}])
    kind, text = aa._last_action_kind(rec)
    assert kind == "OTHER"
    assert text == ""


def test_last_action_kind_none_when_no_actions():
    rec = _rec([{"num": 0, "action": None, "reasoning": None}])
    kind, text = aa._last_action_kind(rec)
    assert kind == "NONE"
    assert text == ""


# ---------------------------------------------------------------------
# record_to_trajectory: final_claim mapping
# ---------------------------------------------------------------------

def test_trajectory_final_claim_from_send_msg():
    rec = _rec([
        {"num": 0, "reasoning": "r0", "action": "goto(\"https://x\")", "last_action_error": ""},
        {"num": 1, "reasoning": "r1", "action": 'send_msg_to_user("The total is $42.")', "last_action_error": ""},
    ])
    traj = aa.record_to_trajectory(rec, "webarena.999")
    assert traj.final_claim == "The total is $42."
    assert traj.trajectory_id == "arb_webarena.999_GenericAgent-gpt-4o-2024-11-20_on_webarena"
    assert traj.allowed_tools == ()
    assert len(traj.steps) == 2  # trailing None-action step, if any, is excluded
    assert traj.steps[-1].tool == "send_msg_to_user"


def test_trajectory_final_claim_from_infeasible():
    rec = _rec([{"num": 0, "action": 'report_infeasible("Cannot find that page.")'}])
    traj = aa.record_to_trajectory(rec, "webarena.998")
    assert traj.final_claim == "Cannot find that page."


def test_trajectory_final_claim_empty_when_no_message():
    rec = _rec([{"num": 0, "action": "click('5')"}, {"num": 1, "action": None}])
    traj = aa.record_to_trajectory(rec, "webarena.997")
    assert traj.final_claim == ""
    assert len(traj.steps) == 1  # the None-action trailing step is dropped


def test_trajectory_excludes_trailing_none_action_step():
    rec = _rec([
        {"num": 0, "action": "click('1')"},
        {"num": 1, "action": None, "reasoning": None},
    ])
    traj = aa.record_to_trajectory(rec, "webarena.996")
    assert len(traj.steps) == 1


# ---------------------------------------------------------------------
# task_id verification guard
# ---------------------------------------------------------------------

def test_verify_task_id_matches_screenshot_path():
    rec = _rec([{
        "num": 0, "action": "click('1')",
        "screenshot_path": "trajectories/screenshots/webarena/GenericAgent-gpt-4o-2024-11-20/webarena.42/screenshot_step_0.png",
    }])
    # should not raise
    aa.record_to_trajectory(rec, "webarena.42")


def test_verify_task_id_mismatch_raises():
    rec = _rec([{
        "num": 0, "action": "click('1')",
        "screenshot_path": "trajectories/screenshots/webarena/GenericAgent-gpt-4o-2024-11-20/webarena.42/screenshot_step_0.png",
    }])
    with pytest.raises(ValueError):
        aa.record_to_trajectory(rec, "webarena.999")  # filename disagrees with embedded id


# ---------------------------------------------------------------------
# expert_label / bucket_of
# ---------------------------------------------------------------------

def _write_annotations(tmp_path: pathlib.Path, rows: list[dict]) -> str:
    p = tmp_path / "annotations.csv"
    fieldnames = [
        "annotator_name", "benchmark", "task_id", "model_name", "exp_name",
        "trajectory_success", "trajectory_side_effect", "trajectory_optimality", "trajectory_looping",
    ]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(p)


_BASE_ROW = {
    "annotator_name": "A", "benchmark": "webarena", "task_id": "webarena.1",
    "model_name": "GenericAgent-gpt-4o-2024-11-20", "exp_name": "GenericAgent-gpt-4o-2024-11-20_on_webarena",
    "trajectory_side_effect": "No", "trajectory_optimality": "4. Completely Optimal", "trajectory_looping": "No",
}


def test_expert_label_unanimous_successful(tmp_path):
    rows = [
        {**_BASE_ROW, "annotator_name": "A", "trajectory_success": "Successful"},
        {**_BASE_ROW, "annotator_name": "B", "trajectory_success": "Successful"},
    ]
    votes = aa.load_annotation_votes(_write_annotations(tmp_path, rows))
    assert aa.expert_label(votes, "webarena", "webarena.1", _BASE_ROW["exp_name"]) == "Successful"


def test_expert_label_unanimous_unsuccessful(tmp_path):
    rows = [{**_BASE_ROW, "annotator_name": "A", "trajectory_success": "Unsuccessful"}]
    votes = aa.load_annotation_votes(_write_annotations(tmp_path, rows))
    assert aa.expert_label(votes, "webarena", "webarena.1", _BASE_ROW["exp_name"]) == "Unsuccessful"


def test_expert_label_disagreement(tmp_path):
    rows = [
        {**_BASE_ROW, "annotator_name": "A", "trajectory_success": "Successful"},
        {**_BASE_ROW, "annotator_name": "B", "trajectory_success": "Unsuccessful"},
    ]
    votes = aa.load_annotation_votes(_write_annotations(tmp_path, rows))
    lbl = aa.expert_label(votes, "webarena", "webarena.1", _BASE_ROW["exp_name"])
    assert lbl.startswith("DISAGREE:")


def test_expert_label_no_annotation(tmp_path):
    votes = aa.load_annotation_votes(_write_annotations(tmp_path, []))
    assert aa.expert_label(votes, "webarena", "webarena.404", "nope") == "NO_ANNOTATION"


def test_bucket_of_false_done():
    bucket, reason = aa.bucket_of("Unsuccessful", "SEND_MSG")
    assert bucket == "FALSE_DONE"
    assert "send_msg_to_user" in reason


def test_bucket_of_clean():
    bucket, _ = aa.bucket_of("Successful", "OTHER")
    assert bucket == "CLEAN"
    bucket2, _ = aa.bucket_of("Successful", "SEND_MSG")
    assert bucket2 == "CLEAN"  # CLEAN is decided by expert label alone


def test_bucket_of_excluded_unsuccessful_no_claim():
    bucket, reason = aa.bucket_of("Unsuccessful", "OTHER")
    assert bucket == "EXCLUDED"
    assert "no completion claim" in reason
    bucket2, _ = aa.bucket_of("Unsuccessful", "INFEASIBLE")
    assert bucket2 == "EXCLUDED"
    bucket3, _ = aa.bucket_of("Unsuccessful", "NONE")
    assert bucket3 == "EXCLUDED"


def test_bucket_of_excluded_disagree_and_no_annotation():
    bucket, reason = aa.bucket_of("DISAGREE:Successful,Unsuccessful", "SEND_MSG")
    assert bucket == "EXCLUDED"
    assert "disagreement" in reason
    bucket2, reason2 = aa.bucket_of("NO_ANNOTATION", "SEND_MSG")
    assert bucket2 == "EXCLUDED"
    assert "no expert annotation" in reason2


# ---------------------------------------------------------------------
# End-to-end gate proof: this is the structural finding the brief asks
# for -- check_false_completion_claim only fires when final_claim TEXT
# contains one of Relay Gate's own completion-marker words (done,
# complete, fixed, resolved, ...). A web agent's completion message is
# usually a direct factual answer, not that phrasing. Both cases are
# proven here, not asserted in prose alone.
# ---------------------------------------------------------------------

def test_gate_holds_when_claim_uses_a_marker_word():
    rec = _rec([{"num": 0, "action": 'send_msg_to_user("The task is now done and complete.")'}])
    traj = aa.record_to_trajectory(rec, "webarena.900")
    verdict = evaluate_trajectory(traj, provider=None)
    assert verdict.decision == "HOLD"
    assert any(code.value == "FALSE_COMPLETION_CLAIM" for code, _ in verdict.reasons)


def test_gate_goes_when_claim_is_a_plain_factual_answer():
    rec = _rec([{"num": 0, "action": 'send_msg_to_user("The minimum travel time is 9 minutes.")'}])
    traj = aa.record_to_trajectory(rec, "webarena.901")
    verdict = evaluate_trajectory(traj, provider=None)
    assert verdict.decision == "GO"  # no marker word -> check_false_completion_claim returns []


# ---------------------------------------------------------------------
# Smoke test against real downloaded data (skipped if absent)
# ---------------------------------------------------------------------

@pytest.mark.skipif(not REAL_DATA_DIR.exists() or not REAL_ANNOTATIONS.exists(), reason="downloaded ARB data not present")
def test_real_data_smoke():
    records = list(aa.iter_labelled_trajectories(str(REAL_DATA_DIR), str(REAL_ANNOTATIONS)))
    assert len(records) > 0
    buckets = {"FALSE_DONE", "CLEAN", "EXCLUDED"}
    for traj, bucket, detail in records:
        assert bucket in buckets
        assert isinstance(traj.trajectory_id, str) and traj.trajectory_id
        assert len(traj.final_claim) <= aa.MAX_CLAIM_CHARS
        assert detail["task_id"]
