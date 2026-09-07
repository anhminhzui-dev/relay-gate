import pathlib

import pytest

from relay_gate.schema import Trajectory

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> Trajectory:
        return Trajectory.load(str(FIXTURES_DIR / name))

    return _load
