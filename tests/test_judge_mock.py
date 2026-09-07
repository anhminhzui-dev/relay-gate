from relay_gate.judge import MockJudgeProvider
from relay_gate.rules import Finding
from relay_gate.reasons import ReasonCode
from relay_gate.schema import Trajectory

_T = Trajectory.from_dict({"trajectory_id": "t-1", "steps": [{"tool": "read_file"}]})
_FINDING = Finding(ReasonCode.AMBIGUOUS_PATH_MATCH, "ambiguous", "test detail")


def test_mock_returns_registered_canned_verdict():
    provider = MockJudgeProvider(canned={"t-1": ("PASS", "looks fine")})
    v = provider.judge(_T, [_FINDING])
    assert v.verdict == "PASS"
    assert v.reason == "looks fine"
    assert v.provider == "mock"


def test_mock_fails_closed_when_id_not_registered():
    provider = MockJudgeProvider(canned={})
    v = provider.judge(_T, [_FINDING])
    assert v.verdict == "FAIL"


def test_mock_with_no_canned_dict_at_all_still_fails_closed():
    provider = MockJudgeProvider()
    v = provider.judge(_T, [_FINDING])
    assert v.verdict == "FAIL"
