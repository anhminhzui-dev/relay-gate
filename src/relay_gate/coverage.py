"""Coverage map: which of rules.py's six checks can physically fire.

For a given trajectory, each of the six checks in ``relay_gate.rules``
reads a specific field. If that field is absent or empty, the check is
structurally DEAD -- it cannot produce a finding no matter what the rest
of the trajectory contains, not because nothing bad happened but because
the check never had the data to look. This module does not re-run the
rules or ask "did it find something"; it inspects the same field each
rule reads (traced to the exact rules.py line in each function's
docstring below) and reports ALIVE (the field is present, the check COULD
fire) or DEAD (the named field is missing, so it cannot).

The six field requirements, decided by reading rules.py itself, not by
guessing:

  TEST_DISABLED            steps[*].args.diff or steps[*].output, and that
                            text must carry a line starting with + or -
                            (rules.py _SKIP_MARK_RE / _ASSERT_REMOVED_RE /
                            _ASSERT_ADDED_RE are all MULTILINE ^[+-] anchors)
  SECRET_LEAK               steps[*].output (non-empty text; check_secret_leak
                            also scans json.dumps(step.args), which is never
                            truly empty, so output is the field that actually
                            gates whether this check sees anything real)
  VALIDATION_BYPASSED       steps[*].args.diff (non-empty text; the guard
                            regexes are the same ^[+-] diff-hunk shape as
                            TEST_DISABLED, read from args["diff"] + output)
  UNKNOWN_TOOL_CALL         allowed_tools (non-empty list; check_unknown_tool_call
                            returns [] unconditionally when it is empty --
                            rules.py line 1: "if not trajectory.allowed_tools: return []")
  DESTRUCTIVE_WITHOUT_READ  steps[*].args.(path|target|table|file) on a step
                            whose tool matches _is_destructive
  FALSE_COMPLETION_CLAIM    final_claim (non-empty text)
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from dataclasses import dataclass

from relay_gate.schema import Trajectory

# Same shape rules.py's own _is_destructive/_target_of use, duplicated
# read-only here (coverage asks "could this fire", not "does it fire", so
# it needs the same tool-name and target-key logic rules.py uses, not the
# rest of the finding-construction machinery).
_DESTRUCTIVE_MARKERS = ("delete_file", "drop", "reset_hard", "rm_rf", "truncate")
_DESTRUCTIVE_SUFFIX_MARKERS = ("delete",)
_TARGET_KEYS = ("path", "target", "table", "file")
_DIFF_LINE_RE = re.compile(r"^[+-]", re.MULTILINE)


def _is_destructive(tool: str) -> bool:
    t = tool.lower()
    if any(m in t for m in _DESTRUCTIVE_MARKERS):
        return True
    return any(t.endswith(m) for m in _DESTRUCTIVE_SUFFIX_MARKERS)


def _target_of(args: dict) -> str | None:
    for key in _TARGET_KEYS:
        val = args.get(key)
        if val:
            return str(val)
    return None


@dataclass(frozen=True)
class CoverageResult:
    check: str
    status: str  # "ALIVE" | "DEAD"
    field: str  # the exact field this check reads
    detail: str  # which step (if any) supplied it, or why none did


# --- the six per-check coverage tests, in relay_gate.rules.ALL_RULES order ---


def _destructive_without_read(t: Trajectory) -> CoverageResult:
    field = "steps[*].args.(path|target|table|file) on a destructive-tool step"
    destructive = [(i, s) for i, s in enumerate(t.steps) if _is_destructive(s.tool)]
    if not destructive:
        return CoverageResult(
            "DESTRUCTIVE_WITHOUT_READ", "DEAD", field,
            "no step names a destructive-shaped tool (rules.py _DESTRUCTIVE_MARKERS / _DESTRUCTIVE_SUFFIX_MARKERS)",
        )
    for i, s in destructive:
        if _target_of(s.args):
            return CoverageResult("DESTRUCTIVE_WITHOUT_READ", "ALIVE", field, f"step {i} ({s.tool}) names a target")
    return CoverageResult(
        "DESTRUCTIVE_WITHOUT_READ", "DEAD", field,
        f"{len(destructive)} destructive step(s) found but none carries a path/target/table/file",
    )


def _test_disabled(t: Trajectory) -> CoverageResult:
    field = "steps[*].args.diff or steps[*].output (a line starting with + or -)"
    for i, step in enumerate(t.steps):
        text = str(step.args.get("diff", "")) + "\n" + step.output
        if _DIFF_LINE_RE.search(text):
            return CoverageResult("TEST_DISABLED", "ALIVE", field, f"step {i} carries diff-shaped text")
    return CoverageResult("TEST_DISABLED", "DEAD", field, "no step has a diff/output line starting with + or -")


def _secret_leak(t: Trajectory) -> CoverageResult:
    field = "steps[*].output (non-empty text)"
    for i, step in enumerate(t.steps):
        if step.output:
            return CoverageResult("SECRET_LEAK", "ALIVE", field, f"step {i} has output text")
    return CoverageResult("SECRET_LEAK", "DEAD", field, "no step carries any output text")


def _false_completion_claim(t: Trajectory) -> CoverageResult:
    field = "final_claim (non-empty text)"
    if t.final_claim.strip():
        return CoverageResult("FALSE_COMPLETION_CLAIM", "ALIVE", field, "final_claim is non-empty")
    return CoverageResult("FALSE_COMPLETION_CLAIM", "DEAD", field, "final_claim is empty/absent")


def _unknown_tool_call(t: Trajectory) -> CoverageResult:
    field = "allowed_tools (non-empty list)"
    if t.allowed_tools:
        return CoverageResult(
            "UNKNOWN_TOOL_CALL", "ALIVE", field, f"allowed_tools has {len(t.allowed_tools)} entry(ies)"
        )
    return CoverageResult(
        "UNKNOWN_TOOL_CALL", "DEAD", field,
        "allowed_tools is empty -- rules.py returns [] unconditionally on this branch",
    )


def _validation_bypassed(t: Trajectory) -> CoverageResult:
    field = "steps[*].args.diff (non-empty text)"
    for i, step in enumerate(t.steps):
        if str(step.args.get("diff", "")):
            return CoverageResult("VALIDATION_BYPASSED", "ALIVE", field, f"step {i} carries an args.diff field")
    return CoverageResult("VALIDATION_BYPASSED", "DEAD", field, "no step carries an args.diff field")


# Order matches relay_gate.rules.ALL_RULES exactly.
CHECK_ORDER = (
    "DESTRUCTIVE_WITHOUT_READ",
    "TEST_DISABLED",
    "SECRET_LEAK",
    "FALSE_COMPLETION_CLAIM",
    "UNKNOWN_TOOL_CALL",
    "VALIDATION_BYPASSED",
)

_CHECK_FUNCS = {
    "DESTRUCTIVE_WITHOUT_READ": _destructive_without_read,
    "TEST_DISABLED": _test_disabled,
    "SECRET_LEAK": _secret_leak,
    "FALSE_COMPLETION_CLAIM": _false_completion_claim,
    "UNKNOWN_TOOL_CALL": _unknown_tool_call,
    "VALIDATION_BYPASSED": _validation_bypassed,
}


def coverage_map(trajectory: Trajectory) -> list[CoverageResult]:
    """Run all six coverage tests against one trajectory, in CHECK_ORDER."""
    return [_CHECK_FUNCS[name](trajectory) for name in CHECK_ORDER]


# --- format adapters: trace-file -> list[Trajectory] ------------------------

_BENCH_DIR = pathlib.Path(__file__).resolve().parents[2] / "bench"


def _ensure_bench_on_path() -> None:
    p = str(_BENCH_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_native(path: str) -> list[Trajectory]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    items = raw if isinstance(raw, list) else [raw]
    return [Trajectory.from_dict(item) for item in items]


def _load_mast(path: str) -> list[Trajectory]:
    _ensure_bench_on_path()
    import external_adapter as ea  # noqa: E402

    return [ea.record_to_trajectory(rec) for rec in ea.load_records(path)]


def _load_arb(path: str) -> list[Trajectory]:
    _ensure_bench_on_path()
    import arb_adapter as aa  # noqa: E402

    with open(path, "r", encoding="utf-8") as fh:
        rec = json.load(fh)
    task_id = pathlib.Path(path).stem
    return [aa.record_to_trajectory(rec, task_id)]


def _adapt_claim_record(raw: dict) -> Trajectory:
    """Delegate to bench/run_checks.py's own adapt_record.

    This used to be a hand-copied duplicate of that mapping (comment here
    used to say so) -- a drift seam with no test behind it: nothing
    stopped the two from silently disagreeing if one was edited and not
    the other. There is now exactly one mapping definition; this is a
    lazy import (bench/ is outside this package's own dependency surface)
    so importing relay_gate.coverage never requires the bench/ tree to
    exist, only actually calling the claude-jsonl loader does."""
    _ensure_bench_on_path()
    import run_checks as _rc  # noqa: E402

    return _rc.adapt_record(raw)


def _load_claude_jsonl(path: str) -> list[Trajectory]:
    trajectories = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            trajectories.append(_adapt_claim_record(json.loads(line)))
    return trajectories


_LOADERS = {
    "native": _load_native,
    "mast": _load_mast,
    "arb": _load_arb,
    "claude-jsonl": _load_claude_jsonl,
}

FORMATS = tuple(_LOADERS)


class TraceFormatError(ValueError):
    """Raised when a trace file does not match the requested --format.
    Covers two distinct failures under one typed error, both naming the
    path, the format tried, and all four supported formats so the fix is
    obvious from the message alone:

      1. The file will not even PARSE under that format's loader (e.g.
         --format claude-jsonl, which expects one JSON object per line, on
         a pretty-printed multi-line native file). Wraps whatever
         json.JSONDecodeError the loader hit.
      2. The file parses fine but does not carry that format's signature
         fields (e.g. --format arb on a native trajectory file: both are
         valid JSON, so nothing would otherwise fail loudly -- the ARB
         adapter would silently tolerate the missing ARB-shaped keys and
         build an empty-steps, empty-claim "trajectory" with no warning).
         Raised by _check_format_signature before the adapter ever runs,
         and names which OTHER supported format the file's shape actually
         matches when one is detected.
    """


# The fields each format's adapter actually reads to build a Trajectory
# (see each loader/adapter's own module docstring for the source of this
# list) -- used only to sniff "does this file look like format X", never
# to build the Trajectory itself.
_FORMAT_SIGNATURE_FIELDS: dict[str, tuple[str, ...]] = {
    "native": ("trajectory_id", "steps"),  # relay_gate.schema.Trajectory.from_dict's own required fields
    "mast": ("trace", "mas_name", "benchmark_name"),  # bench/external_adapter.py record_to_trajectory
    "arb": ("benchmark", "experiment", "steps"),  # bench/arb_adapter.py record_to_trajectory
    "claude-jsonl": ("claim_id", "preceding_actions"),  # bench/run_checks.py adapt_record
}


def _peek_shape(path: str, fmt: str) -> tuple[str, dict | None]:
    """Read just enough of `path` to sniff its shape, without adapting it.

    Returns (kind, sample): kind is "list" (top-level JSON array, as mast
    files are), "dict" (top-level JSON object, as arb/native single-object
    files are), or "jsonl" (claude-jsonl's one-object-per-line shape).
    sample is the first record dict found (the first list element, the
    dict itself, or the first non-blank line's parsed object), or None if
    there is nothing to sniff (an empty file/list -- never blocked, since
    there is no shape to disagree with).
    """
    if fmt == "claude-jsonl":
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                return "jsonl", json.loads(line)
        return "jsonl", None
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if isinstance(raw, list):
        return "list", (raw[0] if raw else None)
    return "dict", raw


def _guess_format(sample: dict, kind: str) -> str | None:
    """Which OTHER format's signature this sample actually matches, if any."""
    for other, fields in _FORMAT_SIGNATURE_FIELDS.items():
        if other == "mast" and kind != "list":
            continue
        if other == "arb" and kind != "dict":
            continue
        if all(f in sample for f in fields):
            return other
    return None


def _check_format_signature(path: str, fmt: str) -> None:
    """Raise TraceFormatError if `path` does not carry `fmt`'s signature
    fields. A JSON-parse failure here is left for the loader's own
    try/except (below) to turn into the parse-failure flavour of
    TraceFormatError, so this function never masks that case with a
    different message."""
    try:
        kind, sample = _peek_shape(path, fmt)
    except (json.JSONDecodeError, OSError):
        return
    if sample is None:
        return

    if fmt == "mast" and kind != "list":
        ok = False
    elif fmt == "arb" and kind != "dict":
        ok = False
    else:
        ok = all(f in sample for f in _FORMAT_SIGNATURE_FIELDS[fmt])
    if ok:
        return

    found = f"top-level keys {sorted(sample)!r}" if isinstance(sample, dict) else f"a top-level JSON {kind}"
    guess = _guess_format(sample, kind)
    guess_msg = f" This file's shape matches format {guess!r} instead." if guess and guess != fmt else ""
    raise TraceFormatError(
        f"{path!r} does not look like format {fmt!r}: expected fields {_FORMAT_SIGNATURE_FIELDS[fmt]} but "
        f"found {found}.{guess_msg} Supported formats are {FORMATS}; pass --format to pick the one "
        f"matching this file's shape."
    )


def load_trajectories(path: str, fmt: str = "native") -> list[Trajectory]:
    if fmt not in _LOADERS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {FORMATS}")
    _check_format_signature(path, fmt)
    try:
        return _LOADERS[fmt](path)
    except json.JSONDecodeError as exc:
        raise TraceFormatError(
            f"could not parse {path!r} as format {fmt!r}: {exc}. "
            f"Supported formats are {FORMATS}; pass --format to pick the one matching this file's shape."
        ) from exc


# --- per-file summary: aggregate coverage_map() across every trajectory ----


def file_coverage(path: str, fmt: str = "native") -> dict:
    """Load every trajectory in `path` via the `fmt` adapter and report,
    per check, whether it is ALIVE on at least one trajectory in the file
    (and on how many), or DEAD on all of them. A check ALIVE on 0 of N
    trajectories is DEAD for the file as a whole -- it never had a chance
    to fire anywhere in what was handed to it.
    """
    trajectories = load_trajectories(path, fmt)
    n = len(trajectories)

    per_check = {
        name: {"field": "", "alive_count": 0, "alive_example": None, "dead_example": None} for name in CHECK_ORDER
    }
    for traj in trajectories:
        for res in coverage_map(traj):
            bucket = per_check[res.check]
            bucket["field"] = res.field
            if res.status == "ALIVE":
                bucket["alive_count"] += 1
                if bucket["alive_example"] is None:
                    bucket["alive_example"] = f"{traj.trajectory_id}: {res.detail}"
            elif bucket["dead_example"] is None:
                bucket["dead_example"] = f"{traj.trajectory_id}: {res.detail}"

    checks = {}
    for name in CHECK_ORDER:
        b = per_check[name]
        status = "ALIVE" if b["alive_count"] > 0 else "DEAD"
        checks[name] = {
            "status": status,
            "field": b["field"],
            "alive_of_n": f"{b['alive_count']}/{n}",
            "example": b["alive_example"] if status == "ALIVE" else (b["dead_example"] or "no trajectories in file"),
        }

    return {"path": path, "format": fmt, "n_trajectories": n, "checks": checks}


_CALIBRATION_PATH = pathlib.Path(__file__).resolve().parent / "data" / "calibration.json"


def _load_calibration() -> dict:
    """Load data/calibration.json (built by calibration.py from the two
    human-labelled results files). Returns {} if it has not been generated
    yet, so a missing file degrades to "no labelled measurement" rather
    than an error."""
    if not _CALIBRATION_PATH.exists():
        return {}
    with open(_CALIBRATION_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _measured_line(check: str, calibration: dict) -> str:
    """One human-readable line of this check's measured hit rate on the two
    labelled sets, restricted to the records where THIS check was ALIVE --
    e.g. "MAST caught 4 of 14 deceptive where the check could fire (14 in
    the set), wrongly held 3 of 5 clean where the check could fire (5 in the
    set); ARB caught 1 of 16 false-done where the check could fire (16 in the
    set), wrongly held 0 of 2 clean where the check could fire (7 in the
    set)", or "no labelled measurement" if calibration.json has nothing for
    this check.

    The bracketed number is the full labelled-set bucket size; the number
    before "where the check could fire" is the ALIVE-restricted count --
    never the same as the bracket number unless the check happens to be
    ALIVE on every record in that bucket (see calibration.py module
    docstring for the flattering-denominator defect this replaced). "Wrongly
    held" counts a clean record where the check FIRED anyway -- a
    false-positive tally, not a virtue, even though "held" reads that way
    on its own (calibration.json key ``clean_wrongly_held``)."""
    entry = calibration.get("checks", {}).get(check)
    if not entry:
        return "no labelled measurement"

    parts = []
    mast = entry.get("mast")
    if mast:
        parts.append(
            f"MAST caught {mast['caught']} of {mast['of_deceptive_alive']} deceptive where the check could "
            f"fire ({mast['of_deceptive_total']} in the set), wrongly held {mast['clean_wrongly_held']} of "
            f"{mast['of_clean_alive']} clean where the check could fire ({mast['of_clean_total']} in the set)"
        )
    arb = entry.get("arb")
    if arb:
        parts.append(
            f"ARB caught {arb['caught']} of {arb['of_false_done_alive']} false-done where the check could "
            f"fire ({arb['of_false_done_total']} in the set), wrongly held {arb['clean_wrongly_held']} of "
            f"{arb['of_clean_alive']} clean where the check could fire ({arb['of_clean_total']} in the set)"
        )
    return "; ".join(parts) if parts else "no labelled measurement"


def format_table(summary: dict) -> str:
    calibration = _load_calibration()
    lines = [
        f"{'CHECK':<26s} {'STATUS':<6s} {'ALIVE/N':<9s} FIELD",
    ]
    for name in CHECK_ORDER:
        c = summary["checks"][name]
        row = f"{name:<26s} {c['status']:<6s} {c['alive_of_n']:<9s} {c['field']}"
        if c["status"] == "ALIVE":
            row += f"; on labelled sets: {_measured_line(name, calibration)}"
        lines.append(row)
    return "\n".join(lines)
