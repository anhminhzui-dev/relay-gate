from relay_gate.gate import evaluate_trajectory
from relay_gate.judge import MockJudgeProvider
from relay_gate.reasons import ReasonCode


def test_clean_trajectory_is_go(load_fixture):
    v = evaluate_trajectory(load_fixture("clean_trajectory.json"))
    assert v.decision == "GO"
    assert v.judge_calls == 0


def test_destructive_without_read_is_hold_no_judge_call(load_fixture):
    v = evaluate_trajectory(load_fixture("destructive_without_read.json"))
    assert v.decision == "HOLD"
    assert v.judge_calls == 0
    assert any(code == ReasonCode.DESTRUCTIVE_WITHOUT_READ for code, _ in v.reasons)


def test_secret_leak_is_hold(load_fixture):
    v = evaluate_trajectory(load_fixture("secret_leak.json"))
    assert v.decision == "HOLD"
    assert any(code == ReasonCode.SECRET_LEAK for code, _ in v.reasons)


def test_false_completion_is_hold(load_fixture):
    v = evaluate_trajectory(load_fixture("false_completion.json"))
    assert v.decision == "HOLD"


def test_unknown_tool_is_hold(load_fixture):
    v = evaluate_trajectory(load_fixture("unknown_tool.json"))
    assert v.decision == "HOLD"


def test_validation_bypassed_is_hold(load_fixture):
    v = evaluate_trajectory(load_fixture("validation_bypassed.json"))
    assert v.decision == "HOLD"


def test_validation_guard_moved_is_go(load_fixture):
    v = evaluate_trajectory(load_fixture("validation_guard_moved.json"))
    assert v.decision == "GO"


def test_ambiguous_with_no_provider_fails_closed(load_fixture):
    v = evaluate_trajectory(load_fixture("ambiguous_trajectory.json"), provider=None)
    assert v.decision == "HOLD"
    assert v.judge_calls == 0
    assert any(code == ReasonCode.JUDGE_UNAVAILABLE for code, _ in v.reasons)


def test_ambiguous_with_mock_provider_pass_becomes_go(load_fixture):
    provider = MockJudgeProvider(canned={"ambiguous-001": ("PASS", "case-only path difference, same file confirmed")})
    v = evaluate_trajectory(load_fixture("ambiguous_trajectory.json"), provider=provider)
    assert v.decision == "GO"
    assert v.judge_calls == 1
    assert any(code == ReasonCode.ESCALATED_PASS for code, _ in v.reasons)


def test_ambiguous_with_mock_provider_fail_stays_hold(load_fixture):
    provider = MockJudgeProvider(canned={"ambiguous-001": ("FAIL", "different files, do not clear")})
    v = evaluate_trajectory(load_fixture("ambiguous_trajectory.json"), provider=provider)
    assert v.decision == "HOLD"
    assert v.judge_calls == 1
    assert any(code == ReasonCode.ESCALATED_FAIL for code, _ in v.reasons)


def test_ambiguous_with_unregistered_mock_id_fails_closed(load_fixture):
    provider = MockJudgeProvider(canned={})  # no entry for ambiguous-001
    v = evaluate_trajectory(load_fixture("ambiguous_trajectory.json"), provider=provider)
    assert v.decision == "HOLD"


def test_hold_finding_never_calls_the_judge_even_with_provider_configured(load_fixture):
    """The relay principle under direct test: a definite HOLD must short-circuit
    before any judge call, even when a provider is available."""
    provider = MockJudgeProvider(canned={"destructive-001": ("PASS", "should never be consulted")})
    v = evaluate_trajectory(load_fixture("destructive_without_read.json"), provider=provider)
    assert v.decision == "HOLD"
    assert v.judge_calls == 0


def test_to_dict_shape(load_fixture):
    v = evaluate_trajectory(load_fixture("clean_trajectory.json"))
    d = v.to_dict()
    assert d["trajectory_id"] == "clean-001"
    assert d["decision"] == "GO"
    assert isinstance(d["reasons"], list)
