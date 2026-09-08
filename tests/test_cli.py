import json
import pathlib

from relay_gate.cli import main

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def test_cli_check_clean_exits_zero(capsys):
    code = main(["check", str(FIXTURES_DIR / "clean_trajectory.json")])
    assert code == 0
    out = capsys.readouterr().out
    assert '"decision": "GO"' in out


def test_cli_check_hold_exits_two(capsys):
    code = main(["check", str(FIXTURES_DIR / "destructive_without_read.json")])
    assert code == 2
    out = capsys.readouterr().out
    assert '"decision": "HOLD"' in out


def test_cli_check_list_of_trajectories(tmp_path, capsys):
    clean = json.loads((FIXTURES_DIR / "clean_trajectory.json").read_text())
    bad = json.loads((FIXTURES_DIR / "destructive_without_read.json").read_text())
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(json.dumps([clean, bad]))

    code = main(["check", str(batch_path)])
    assert code == 2
    out = capsys.readouterr().out
    assert "2 trajectories, 1 GO, 1 HOLD, 0 judge call(s)" in out


def test_cli_coverage_wrong_format_exits_two_with_one_line_stderr_no_traceback(capsys):
    """--format arb on a native trajectory file must exit 2 with one clean
    line on stderr naming the mismatch -- not a twelve-line traceback, and
    nothing at all on stdout (no junk all-DEAD table printed either)."""
    code = main(["coverage", str(FIXTURES_DIR / "clean_trajectory.json"), "--format", "arb"])
    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    err_lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(err_lines) == 1, captured.err
    assert "Traceback" not in captured.err
    assert "clean_trajectory.json" in err_lines[0]
    assert "arb" in err_lines[0]


def test_cli_coverage_right_format_still_prints_the_table(capsys):
    code = main(["coverage", str(FIXTURES_DIR / "clean_trajectory.json"), "--format", "native"])
    assert code == 0
    out = capsys.readouterr().out
    assert "CHECK" in out
    assert "STATUS" in out


def test_cli_check_ambiguous_with_mock_canned_file(tmp_path, capsys):
    canned_path = tmp_path / "canned.json"
    canned_path.write_text(json.dumps({"ambiguous-001": {"verdict": "PASS", "reason": "confirmed same file"}}))

    code = main(
        [
            "check",
            str(FIXTURES_DIR / "ambiguous_trajectory.json"),
            "--provider",
            "mock",
            "--mock-canned",
            str(canned_path),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert '"decision": "GO"' in out
    assert "1 judge call(s)" in out
