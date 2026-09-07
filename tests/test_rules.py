from relay_gate.reasons import ReasonCode
from relay_gate.rules import run_all_rules


def _codes(trajectory):
    return {f.reason for f in run_all_rules(trajectory)}


def test_clean_trajectory_has_no_findings(load_fixture):
    t = load_fixture("clean_trajectory.json")
    assert run_all_rules(t) == []


def test_destructive_without_read_is_flagged(load_fixture):
    t = load_fixture("destructive_without_read.json")
    assert ReasonCode.DESTRUCTIVE_WITHOUT_READ in _codes(t)


def test_secret_leak_is_flagged_only_on_write_like_step(load_fixture):
    t = load_fixture("secret_leak.json")
    findings = run_all_rules(t)
    assert ReasonCode.SECRET_LEAK in {f.reason for f in findings}
    hit = [f for f in findings if f.reason == ReasonCode.SECRET_LEAK][0]
    assert hit.step_index == 1  # the write_file step, not the read_file step


def test_false_completion_claim_is_flagged(load_fixture):
    t = load_fixture("false_completion.json")
    assert ReasonCode.FALSE_COMPLETION_CLAIM in _codes(t)


def test_false_completion_claim_needs_no_test_step(load_fixture):
    t = load_fixture("clean_trajectory.json")
    # sanity: the clean fixture DOES run tests, so this is the negative check
    assert ReasonCode.FALSE_COMPLETION_CLAIM not in _codes(t)


def test_unknown_tool_call_is_flagged(load_fixture):
    t = load_fixture("unknown_tool.json")
    assert ReasonCode.UNKNOWN_TOOL_CALL in _codes(t)


def test_validation_bypassed_when_guard_only_removed(load_fixture):
    t = load_fixture("validation_bypassed.json")
    assert ReasonCode.VALIDATION_BYPASSED in _codes(t)


def test_validation_not_bypassed_when_guard_moved(load_fixture):
    """Regression test for the asymmetric-check bug this rule was written to avoid:
    a guard removed in one step and re-added in a later step must NOT fire."""
    t = load_fixture("validation_guard_moved.json")
    assert ReasonCode.VALIDATION_BYPASSED not in _codes(t)
    assert run_all_rules(t) == []


def test_ambiguous_case_matched(load_fixture):
    t = load_fixture("ambiguous_trajectory.json")
    findings = run_all_rules(t)
    assert len(findings) == 1
    assert findings[0].reason == ReasonCode.AMBIGUOUS_PATH_MATCH
    assert findings[0].category == "ambiguous"


def test_destructive_step_with_no_target_field_is_ambiguous_not_silently_clean():
    from relay_gate.schema import Trajectory

    t = Trajectory.from_dict(
        {
            "trajectory_id": "no-target-001",
            "allowed_tools": ["delete_file"],
            "steps": [{"tool": "delete_file", "args": {}, "output": "deleted something"}],
        }
    )
    findings = run_all_rules(t)
    assert any(f.reason == ReasonCode.AMBIGUOUS_PATH_MATCH for f in findings)
