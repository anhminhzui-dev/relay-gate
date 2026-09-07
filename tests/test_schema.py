import pytest

from relay_gate.schema import Step, Trajectory


def test_step_from_dict_requires_tool():
    with pytest.raises(ValueError):
        Step.from_dict({"args": {}})


def test_trajectory_from_dict_requires_id_and_steps():
    with pytest.raises(ValueError):
        Trajectory.from_dict({"steps": []})
    with pytest.raises(ValueError):
        Trajectory.from_dict({"trajectory_id": "x"})


def test_trajectory_from_dict_defaults_allowed_tools_and_claim():
    t = Trajectory.from_dict({"trajectory_id": "x", "steps": [{"tool": "read_file"}]})
    assert t.allowed_tools == ()
    assert t.final_claim == ""
    assert t.steps[0].args == {}
