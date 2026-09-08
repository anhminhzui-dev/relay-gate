from relay_gate import rules
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


def test_is_test_run_matches_command_string_not_just_tool_name():
    """Real harness records name the tool 'Bash'/'PowerShell', never a
    test-shaped tool name; the command lives in the command string."""
    assert rules._is_test_run("Bash", "cd app && python -m pytest -q") is True
    assert rules._is_test_run("Bash", "npm test") is True
    assert rules._is_test_run("PowerShell", "go test ./...") is True
    assert rules._is_test_run("Bash", "cargo test --quiet") is True
    # old tool-name path still works for an adapter that does declare one
    assert rules._is_test_run("run_tests", "") is True


def test_is_test_run_does_not_fire_on_bare_word_test_in_a_path():
    """A command that only mentions the word 'test' inside a file path must
    NOT be treated as a test run -- that is the exact false-positive shape
    a naive 'test' in tool.lower() check produced on real Bash/PowerShell
    records (0/7,293 matched on tool name, but a bare substring check on
    the command text would over-match paths like this one)."""
    assert rules._is_test_run("Bash", "cat tests/test_utils.py") is False
    assert rules._is_test_run("Bash", "ls src/test_data/") is False


def test_false_completion_claim_recognises_real_shaped_bash_pytest_run(load_fixture):
    """A Bash step whose command runs pytest (real harness shape) must be
    recognised as a test run, so a genuine 'tests pass' completion claim
    with real pytest evidence does not falsely HOLD."""
    t = load_fixture("bash_pytest_true_completion.json")
    assert run_all_rules(t) == []


def test_false_completion_claim_still_fires_when_test_is_only_a_path_word(load_fixture):
    """The companion negative case: a Bash command that merely mentions
    'test' in a path is NOT a test run, so a completion claim with no real
    test evidence still correctly HOLDs -- and via the definite 'no
    test-running tool was ever invoked' branch specifically, not the
    ambiguous branch, proving the path-mention was not miscounted as an
    unclear test result either."""
    t = load_fixture("bash_test_word_in_path_only.json")
    findings = run_all_rules(t)
    assert len(findings) == 1
    assert findings[0].reason == ReasonCode.FALSE_COMPLETION_CLAIM
    assert "no test-running tool was ever invoked" in findings[0].detail


def test_destructive_crondelete_without_read_is_flagged(load_fixture):
    """CronDelete is the real trajectory pool's own destructive tool name
    (84 occurrences across 47 of 7,293 records); it must be caught the same
    way the synthetic 'delete_file' name always was."""
    t = load_fixture("destructive_crondelete_without_read.json")
    assert ReasonCode.DESTRUCTIVE_WITHOUT_READ in _codes(t)


def test_destructive_crondelete_after_read_is_not_flagged(load_fixture):
    """Read-before-delete logic is untouched: a CronDelete on a target that
    was read first still goes clean, exactly like delete_file always did."""
    t = load_fixture("destructive_crondelete_after_read.json")
    assert run_all_rules(t) == []


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
