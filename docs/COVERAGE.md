# Coverage map

`relay-gate coverage <trace-file> [--format native|mast|arb|claude-jsonl]`
answers one question a user should be able to ask before trusting a HOLD
or a GO: for THIS file, which of the six checks in `rules.py` can
physically fire, and which single field's absence disables each of the
rest. It never re-runs the rules or asks "did it find something" -- it
reads the same field each rule reads (see `src/relay_gate/coverage.py`
module docstring for the exact rules.py line behind each mapping) and
reports ALIVE (the check has the data to possibly produce a finding) or
DEAD (the named field is missing, so the check cannot).

A check ALIVE on 0 of N trajectories in a file is reported DEAD for the
file: it never had a chance to fire anywhere in what was handed to it.

## The calibration line: ALIVE-restricted, never the full-set size

Every ALIVE row also carries that check's measured hit rate on the two
human-labelled external sets (MAST-Data, AgentRewardBench), read from
`src/relay_gate/data/calibration.json`. That file is a generated artefact,
never hand-typed: `python -m relay_gate.calibration` (see
`src/relay_gate/calibration.py`) rebuilds it straight from the two bench
results files (`./external_data/mast/results.json`
and `.../arb/results.json`) and their raw source trees. ALIVE means the
check *could* fire on this file; the calibration line is a separate,
independent number, how often that same check actually caught something on
two real labelled datasets. A check absent from `calibration.json` prints
"no labelled measurement" instead. DEAD rows are unaffected and unchanged.

**The denominator in that line is restricted to the records where the
check was actually ALIVE, never the full labelled-set size.** A defect
review (2026-09-08) found that a prior version of this line printed rates
against the FULL clean/deceptive/false-done bucket size regardless of
whether the check ever had the data to fire on every record in it. Concrete
example: on AgentRewardBench, 5 of the 7 CLEAN records carry an empty
`final_claim` (no `send_msg_to_user` ending -- see `bench/arb_adapter.py`),
so `FALSE_COMPLETION_CLAIM` is structurally DEAD on them by this module's
own rule; printing "0 of 7 clean held" implied all 7 were live trials, and
the counter it names is a false-positive tally (the check FIRED on a clean
record), not a virtue, despite reading like one next to "caught". The key
is `clean_wrongly_held`, and the line now reads "wrongly held 0 of 2 clean
where the check could fire (7 in the set)": 2 is the honest denominator
(how many clean records this check could even have fired on), 7 in
brackets is the full clean bucket size, for context. This is computed for all six checks against both sources, not
just this one worked example -- see `src/relay_gate/calibration.py`'s
module docstring for the full data flow, and `tests/test_calibration.py`
for the regression tests that guard it (including an independent
re-derivation pass that would fail if a printed denominator ever again
exceeded the real ALIVE count).

Every table and JSON block below is the real, unedited stdout of the
command shown above it (`PYTHONPATH=src python -m relay_gate.cli coverage
...`, run from the repo root, 2026-09-08), one run per supported format.

## native

```
$ python -m relay_gate.cli coverage tests/fixtures/false_completion.json --format native

CHECK                      STATUS ALIVE/N   FIELD
DESTRUCTIVE_WITHOUT_READ   DEAD   0/1       steps[*].args.(path|target|table|file) on a destructive-tool step
TEST_DISABLED              ALIVE  1/1       steps[*].args.diff or steps[*].output (a line starting with + or -); on labelled sets: MAST caught 0 of 3 deceptive where the check could fire (14 in the set), wrongly held 0 of 3 clean where the check could fire (5 in the set); ARB caught 0 of 0 false-done where the check could fire (16 in the set), wrongly held 0 of 0 clean where the check could fire (7 in the set)
SECRET_LEAK                ALIVE  1/1       steps[*].output (non-empty text); on labelled sets: MAST caught 0 of 14 deceptive where the check could fire (14 in the set), wrongly held 0 of 5 clean where the check could fire (5 in the set); ARB caught 0 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 7 clean where the check could fire (7 in the set)
FALSE_COMPLETION_CLAIM     ALIVE  1/1       final_claim (non-empty text); on labelled sets: MAST caught 4 of 14 deceptive where the check could fire (14 in the set), wrongly held 3 of 5 clean where the check could fire (5 in the set); ARB caught 1 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 2 clean where the check could fire (7 in the set)
UNKNOWN_TOOL_CALL          ALIVE  1/1       allowed_tools (non-empty list); on labelled sets: MAST caught 0 of 0 deceptive where the check could fire (14 in the set), wrongly held 0 of 0 clean where the check could fire (5 in the set); ARB caught 0 of 0 false-done where the check could fire (16 in the set), wrongly held 0 of 0 clean where the check could fire (7 in the set)
VALIDATION_BYPASSED        ALIVE  1/1       steps[*].args.diff (non-empty text); on labelled sets: MAST caught 0 of 6 deceptive where the check could fire (14 in the set), wrongly held 0 of 3 clean where the check could fire (5 in the set); ARB caught 0 of 0 false-done where the check could fire (16 in the set), wrongly held 0 of 0 clean where the check could fire (7 in the set)
{"path": "tests/fixtures/false_completion.json", "format": "native", "n_trajectories": 1, "checks": {"DESTRUCTIVE_WITHOUT_READ": {"status": "DEAD", "field": "steps[*].args.(path|target|table|file) on a destructive-tool step", "alive_of_n": "0/1", "example": "false-completion-001: no step names a destructive-shaped tool (rules.py _DESTRUCTIVE_MARKERS / _DESTRUCTIVE_SUFFIX_MARKERS)"}, "TEST_DISABLED": {"status": "ALIVE", "field": "steps[*].args.diff or steps[*].output (a line starting with + or -)", "alive_of_n": "1/1", "example": "false-completion-001: step 1 carries diff-shaped text"}, "SECRET_LEAK": {"status": "ALIVE", "field": "steps[*].output (non-empty text)", "alive_of_n": "1/1", "example": "false-completion-001: step 0 has output text"}, "FALSE_COMPLETION_CLAIM": {"status": "ALIVE", "field": "final_claim (non-empty text)", "alive_of_n": "1/1", "example": "false-completion-001: final_claim is non-empty"}, "UNKNOWN_TOOL_CALL": {"status": "ALIVE", "field": "allowed_tools (non-empty list)", "alive_of_n": "1/1", "example": "false-completion-001: allowed_tools has 3 entry(ies)"}, "VALIDATION_BYPASSED": {"status": "ALIVE", "field": "steps[*].args.diff (non-empty text)", "alive_of_n": "1/1", "example": "false-completion-001: step 1 carries an args.diff field"}}}
```

Read: this one fixture carries a write_file step with an `args.diff`
field, so both diff-shaped checks (`TEST_DISABLED`, `VALIDATION_BYPASSED`)
are ALIVE. `DESTRUCTIVE_WITHOUT_READ` is DEAD because no step names a
destructive-shaped tool at all -- native trajectories can carry any mix,
this one just does not have one. Note the calibration line's own honesty:
`TEST_DISABLED` was ALIVE on only 3 of MAST's 14 deceptive records and 3 of
its 5 clean records (not 14 and 5) -- most MAST records simply never carry
diff-shaped text at all, so most of the bucket was never a live trial for
this check.

## mast

```
$ python -m relay_gate.cli coverage ./external_data/mast/data/MAD_human_labelled_dataset.json --format mast

CHECK                      STATUS ALIVE/N   FIELD
DESTRUCTIVE_WITHOUT_READ   DEAD   0/19      steps[*].args.(path|target|table|file) on a destructive-tool step
TEST_DISABLED              ALIVE  6/19      steps[*].args.diff or steps[*].output (a line starting with + or -); on labelled sets: MAST caught 0 of 3 deceptive where the check could fire (14 in the set), wrongly held 0 of 3 clean where the check could fire (5 in the set); ARB caught 0 of 0 false-done where the check could fire (16 in the set), wrongly held 0 of 0 clean where the check could fire (7 in the set)
SECRET_LEAK                ALIVE  19/19     steps[*].output (non-empty text); on labelled sets: MAST caught 0 of 14 deceptive where the check could fire (14 in the set), wrongly held 0 of 5 clean where the check could fire (5 in the set); ARB caught 0 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 7 clean where the check could fire (7 in the set)
FALSE_COMPLETION_CLAIM     ALIVE  19/19     final_claim (non-empty text); on labelled sets: MAST caught 4 of 14 deceptive where the check could fire (14 in the set), wrongly held 3 of 5 clean where the check could fire (5 in the set); ARB caught 1 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 2 clean where the check could fire (7 in the set)
UNKNOWN_TOOL_CALL          DEAD   0/19      allowed_tools (non-empty list)
VALIDATION_BYPASSED        ALIVE  9/19      steps[*].args.diff (non-empty text); on labelled sets: MAST caught 0 of 6 deceptive where the check could fire (14 in the set), wrongly held 0 of 3 clean where the check could fire (5 in the set); ARB caught 0 of 0 false-done where the check could fire (16 in the set), wrongly held 0 of 0 clean where the check could fire (7 in the set)
{"path": "./external_data/mast/data/MAD_human_labelled_dataset.json", "format": "mast", "n_trajectories": 19, "checks": {"DESTRUCTIVE_WITHOUT_READ": {"status": "DEAD", "field": "steps[*].args.(path|target|table|file) on a destructive-tool step", "alive_of_n": "0/19", "example": "mast_AppWorld_Test-C_0_round_1: no step names a destructive-shaped tool (rules.py _DESTRUCTIVE_MARKERS / _DESTRUCTIVE_SUFFIX_MARKERS)"}, "TEST_DISABLED": {"status": "ALIVE", "field": "steps[*].args.diff or steps[*].output (a line starting with + or -)", "alive_of_n": "6/19", "example": "mast_ChatDev_ProgramDev_3_round_1: step 19 carries diff-shaped text"}, "SECRET_LEAK": {"status": "ALIVE", "field": "steps[*].output (non-empty text)", "alive_of_n": "19/19", "example": "mast_AppWorld_Test-C_0_round_1: step 0 has output text"}, "FALSE_COMPLETION_CLAIM": {"status": "ALIVE", "field": "final_claim (non-empty text)", "alive_of_n": "19/19", "example": "mast_AppWorld_Test-C_0_round_1: final_claim is non-empty"}, "UNKNOWN_TOOL_CALL": {"status": "DEAD", "field": "allowed_tools (non-empty list)", "alive_of_n": "0/19", "example": "mast_AppWorld_Test-C_0_round_1: allowed_tools is empty -- rules.py returns [] unconditionally on this branch"}, "VALIDATION_BYPASSED": {"status": "ALIVE", "field": "steps[*].args.diff (non-empty text)", "alive_of_n": "9/19", "example": "mast_HyperAgent_SWE-Bench-Lite_1_round_1: step 1 carries an args.diff field"}}}
```

Read: `UNKNOWN_TOOL_CALL` is DEAD on all 19 of 19 records -- MAST never
records a declared tool allow-list, so this check is a structural no-op
on this whole source, matching `bench/external_adapter.py`'s own module
docstring (and its calibration line reads 0 of 0 in both buckets on both
sources, not 0 of 14/0 of 5 -- it was never ALIVE on a single labelled
record anywhere). `DESTRUCTIVE_WITHOUT_READ` is DEAD on all 19 for the same
adapter-shape reason (the adapter's steps carry raw segment text, never a
parsed path/target/table/file key). `TEST_DISABLED` and
`VALIDATION_BYPASSED` are ALIVE on the subset of records whose trace
embeds a real `diff --git` block (6 and 9 of 19 respectively -- not the
same count, because `TEST_DISABLED` also fires on a bare skip/xfail
marker or assert-removal line without a full diff span).

## arb

```
$ python -m relay_gate.cli coverage ./external_data/arb/data/cleaned/webarena.555.json --format arb

CHECK                      STATUS ALIVE/N   FIELD
DESTRUCTIVE_WITHOUT_READ   DEAD   0/1       steps[*].args.(path|target|table|file) on a destructive-tool step
TEST_DISABLED              DEAD   0/1       steps[*].args.diff or steps[*].output (a line starting with + or -)
SECRET_LEAK                ALIVE  1/1       steps[*].output (non-empty text); on labelled sets: MAST caught 0 of 14 deceptive where the check could fire (14 in the set), wrongly held 0 of 5 clean where the check could fire (5 in the set); ARB caught 0 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 7 clean where the check could fire (7 in the set)
FALSE_COMPLETION_CLAIM     ALIVE  1/1       final_claim (non-empty text); on labelled sets: MAST caught 4 of 14 deceptive where the check could fire (14 in the set), wrongly held 3 of 5 clean where the check could fire (5 in the set); ARB caught 1 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 2 clean where the check could fire (7 in the set)
UNKNOWN_TOOL_CALL          DEAD   0/1       allowed_tools (non-empty list)
VALIDATION_BYPASSED        DEAD   0/1       steps[*].args.diff (non-empty text)
{"path": "./external_data/arb/data/cleaned/webarena.555.json", "format": "arb", "n_trajectories": 1, "checks": {"DESTRUCTIVE_WITHOUT_READ": {"status": "DEAD", "field": "steps[*].args.(path|target|table|file) on a destructive-tool step", "alive_of_n": "0/1", "example": "arb_webarena.555_GenericAgent-gpt-4o-2024-11-20_on_webarena: no step names a destructive-shaped tool (rules.py _DESTRUCTIVE_MARKERS / _DESTRUCTIVE_SUFFIX_MARKERS)"}, "TEST_DISABLED": {"status": "DEAD", "field": "steps[*].args.diff or steps[*].output (a line starting with + or -)", "alive_of_n": "0/1", "example": "arb_webarena.555_GenericAgent-gpt-4o-2024-11-20_on_webarena: no step has a diff/output line starting with + or -"}, "SECRET_LEAK": {"status": "ALIVE", "field": "steps[*].output (non-empty text)", "alive_of_n": "1/1", "example": "arb_webarena.555_GenericAgent-gpt-4o-2024-11-20_on_webarena: step 0 has output text"}, "FALSE_COMPLETION_CLAIM": {"status": "ALIVE", "field": "final_claim (non-empty text)", "alive_of_n": "1/1", "example": "arb_webarena.555_GenericAgent-gpt-4o-2024-11-20_on_webarena: final_claim is non-empty"}, "UNKNOWN_TOOL_CALL": {"status": "DEAD", "field": "allowed_tools (non-empty list)", "alive_of_n": "0/1", "example": "arb_webarena.555_GenericAgent-gpt-4o-2024-11-20_on_webarena: allowed_tools is empty -- rules.py returns [] unconditionally on this branch"}, "VALIDATION_BYPASSED": {"status": "DEAD", "field": "steps[*].args.diff (non-empty text)", "alive_of_n": "0/1", "example": "arb_webarena.555_GenericAgent-gpt-4o-2024-11-20_on_webarena: no step carries an args.diff field"}}}
```

`webarena.555` is the one ARB record Relay Gate actually HOLDs on (see
`bench/external/ARB_RESULTS.md`). Only two of six checks are ALIVE:
`SECRET_LEAK` (a step has output text) and `FALSE_COMPLETION_CLAIM` (the
`send_msg_to_user` ending gives a non-empty `final_claim`). The other
four are DEAD on the whole BrowserGym action shape, exactly as
`bench/arb_adapter.py`'s own module docstring already says. Note
`FALSE_COMPLETION_CLAIM`'s own calibration line here: ARB's clean-bucket
denominator reads "0 of 2 clean where the check could fire (7 in the
set)" -- 2, not 7, because 5 of ARB's 7 clean records never send a final
message at all (empty `final_claim`, structurally DEAD for this check).

## claude-jsonl

```
$ python -m relay_gate.cli coverage ./data/trajectories/claude.jsonl --format claude-jsonl

CHECK                      STATUS ALIVE/N   FIELD
DESTRUCTIVE_WITHOUT_READ   DEAD   0/4010    steps[*].args.(path|target|table|file) on a destructive-tool step
TEST_DISABLED              DEAD   0/4010    steps[*].args.diff or steps[*].output (a line starting with + or -)
SECRET_LEAK                DEAD   0/4010    steps[*].output (non-empty text)
FALSE_COMPLETION_CLAIM     ALIVE  4010/4010 final_claim (non-empty text); on labelled sets: MAST caught 4 of 14 deceptive where the check could fire (14 in the set), wrongly held 3 of 5 clean where the check could fire (5 in the set); ARB caught 1 of 16 false-done where the check could fire (16 in the set), wrongly held 0 of 2 clean where the check could fire (7 in the set)
UNKNOWN_TOOL_CALL          DEAD   0/4010    allowed_tools (non-empty list)
VALIDATION_BYPASSED        DEAD   0/4010    steps[*].args.diff (non-empty text)
{"path": "./data/trajectories/claude.jsonl", "format": "claude-jsonl", "n_trajectories": 4010, "checks": {"DESTRUCTIVE_WITHOUT_READ": {"status": "DEAD", "field": "steps[*].args.(path|target|table|file) on a destructive-tool step", "alive_of_n": "0/4010", "example": "c3ccc17856e54aa98781bb0a4d6e35d4: no step names a destructive-shaped tool (rules.py _DESTRUCTIVE_MARKERS / _DESTRUCTIVE_SUFFIX_MARKERS)"}, "TEST_DISABLED": {"status": "DEAD", "field": "steps[*].args.diff or steps[*].output (a line starting with + or -)", "alive_of_n": "0/4010", "example": "c3ccc17856e54aa98781bb0a4d6e35d4: no step has a diff/output line starting with + or -"}, "SECRET_LEAK": {"status": "DEAD", "field": "steps[*].output (non-empty text)", "alive_of_n": "0/4010", "example": "c3ccc17856e54aa98781bb0a4d6e35d4: no step carries any output text"}, "FALSE_COMPLETION_CLAIM": {"status": "ALIVE", "field": "final_claim (non-empty text)", "alive_of_n": "4010/4010", "example": "c3ccc17856e54aa98781bb0a4d6e35d4: final_claim is non-empty"}, "UNKNOWN_TOOL_CALL": {"status": "DEAD", "field": "allowed_tools (non-empty list)", "alive_of_n": "0/4010", "example": "c3ccc17856e54aa98781bb0a4d6e35d4: allowed_tools is empty -- rules.py returns [] unconditionally on this branch"}, "VALIDATION_BYPASSED": {"status": "DEAD", "field": "steps[*].args.diff (non-empty text)", "alive_of_n": "0/4010", "example": "c3ccc17856e54aa98781bb0a4d6e35d4: no step carries an args.diff field"}}}
```

Read plainly, this is the starkest result of the four: across all 4,010
claude-sourced claim records in the pool, `FALSE_COMPLETION_CLAIM` is the
ONLY check that is ever ALIVE (4,010 of 4,010 -- every record has a
non-empty `claim_text`). The other five are DEAD on 0 of 4,010, for a
reason that is a property of the EXTRACTOR, not the underlying agent
sessions: `bench/extract_trajectories.py` records `output = ""` always
(privacy law: raw tool output is never captured) and no declared
allow-list or diff field either, and `bench/run_checks.py`'s own
`adapt_record` docstring already states this (as of 2026-09-08,
`coverage._adapt_claim_record` delegates to that exact function -- see
"Drift guards" below -- so there is no separate mapping to drift out of
step with it). This is the one figure this coverage tool adds beyond what
those docstrings already said in prose: a runnable command anyone can
point at any trace file, in any of the four formats, and get the same
table back, instead of re-deriving it from reading three separate module
docstrings.

## Format notes

- `native`: a `relay_gate.schema.Trajectory`-shaped JSON file (one object,
  or a JSON list of them, exactly like `relay-gate check`'s own trace
  argument). Signature fields: `trajectory_id`, `steps`.
- `mast`: a MAST-Data JSON list (`bench/external_adapter.py`
  `record_to_trajectory`); every record in the file is loaded and a check
  is reported ALIVE for the file if it is ALIVE on at least one record.
  Signature: a top-level JSON list whose records carry `trace`,
  `mas_name`, `benchmark_name`.
- `arb`: one AgentRewardBench `cleaned/<benchmark>.<task_num>.json`
  BrowserGym record (`bench/arb_adapter.py` `record_to_trajectory`); the
  task id is taken from the filename, the same convention the adapter
  itself uses. `annotations.csv` is not read -- coverage is a structural
  question about the trajectory shape, not the expert label. Signature: a
  top-level JSON object carrying `benchmark`, `experiment`, `steps`.
- `claude-jsonl`: one claim record per line, the shape
  `bench/extract_trajectories.py` writes to `trajectories/claude.jsonl` /
  `trajectories/codex.jsonl` (same mapping as `bench/run_checks.py`'s
  `adapt_record`; `coverage._adapt_claim_record` now imports and calls
  that exact function rather than duplicating it). Signature: each
  non-blank line parses as a JSON object carrying `claim_id`,
  `preceding_actions`.

## Wrong-format errors

Pointing `--format` at a file it does not actually shape used to fail in
two different, both bad, ways:

1. If the wrong-format loader could not even parse the file (for example
   `--format claude-jsonl`, which expects one JSON object per line, on a
   pretty-printed single-object native file) it surfaced a raw
   `json.JSONDecodeError` traceback.
2. If the wrong-format loader COULD parse the file -- because both shapes
   are valid JSON, just structurally different -- it silently built a junk
   `Trajectory` and printed a confident all-DEAD table with no warning at
   all. Concretely: `--format arb` on a native trajectory file parses fine
   (native files are valid JSON), and `bench/arb_adapter.py`'s
   `record_to_trajectory` tolerates the missing ARB-shaped keys instead of
   raising -- `steps` ends up `[]` (no native step dict carries an
   `"action"` key, which is what the ARB step filter looks for) and
   `final_claim` ends up `""` (no step's action is `send_msg_to_user` /
   `report_infeasible`), so every check reports DEAD with no hint that the
   format itself was wrong.

Both now raise `relay_gate.coverage.TraceFormatError`, a typed `ValueError`
subclass whose message names the path, the format that was tried, the
fields that format expects, what was actually found in the file, and all
four supported formats -- and, for the second failure mode, which OTHER
supported format the file's shape actually matches, when one is detected.
Real output, captured live (2026-09-08):

```
$ python -m relay_gate.cli coverage tests/fixtures/false_completion.json --format arb
relay-gate: 'tests/fixtures/false_completion.json' does not look like format 'arb': expected fields ('benchmark', 'experiment', 'steps') but found top-level keys ['allowed_tools', 'final_claim', 'steps', 'trajectory_id']. This file's shape matches format 'native' instead. Supported formats are ('native', 'mast', 'arb', 'claude-jsonl'); pass --format to pick the one matching this file's shape.
exit code: 2
```

`relay-gate check` and `relay-gate coverage` both print this as one line to
stderr and exit 2 -- no traceback ever reaches the terminal.

Covered by `tests/test_coverage.py`'s
`test_wrong_format_raises_typed_error_naming_the_four_formats`,
`test_wrong_format_error_is_not_a_bare_json_decode_error`,
`test_wrong_format_arb_on_native_file_raises_not_a_junk_all_dead_table`,
and `test_wrong_format_mast_on_native_file_raises_and_names_native`; the
CLI-level exit-code/stderr contract is covered by `tests/test_cli.py`'s
`test_cli_coverage_wrong_format_exits_two_with_one_line_stderr_no_traceback`.

## Drift guards

Four seams where two pieces of logic must stay in exact agreement, each
now closed by a test that would fail the moment they drifted apart
(`tests/test_coverage.py` unless noted):

- **Destructive-tool markers.** `coverage._DESTRUCTIVE_MARKERS` /
  `_DESTRUCTIVE_SUFFIX_MARKERS` are a read-only copy of `rules.py`'s own
  tuples of the same name. `test_coverage_destructive_markers_match_rules_verbatim`
  asserts literal equality.
- **Target-key names.** `coverage._TARGET_KEYS` names the same
  `args` keys `rules.py`'s own `_target_of()` reads. `rules.py` now names
  its own copy as the constant `rules._TARGET_KEYS` too (promoted from an
  inline tuple literal, 2026-09-08), so `test_target_keys_literally_match_rules`
  compares the two tuples literally instead of probing `_target_of()` with
  a fixed candidate list of plausible key names -- a list a newly added key
  could previously slip past without being added to it.
- **The diff-line anchor.** `coverage._DIFF_LINE_RE` (any line starting
  with `+` or `-`) is a deliberately broader superset of `rules.py`'s own
  exact-shaped anchors (`_SKIP_MARK_RE`, `_ASSERT_REMOVED_RE`,
  `_ASSERT_ADDED_RE`, `_GUARD_REMOVED_RE`, `_GUARD_ADDED_RE`).
  `test_diff_line_regex_agrees_with_rules_anchors_on_a_stripped_diff`
  builds one fixture with a real skip-marker/assert/guard-removal diff and
  one with that diff stripped to empty text, and asserts both `rules.py`'s
  own finding AND `coverage.py`'s ALIVE verdict flip together, for both
  `TEST_DISABLED` and `VALIDATION_BYPASSED`.
- **The claude-jsonl adapter mapping.** `coverage._adapt_claim_record` used
  to be a hand-copied duplicate of `bench/run_checks.py`'s `adapt_record`.
  It now imports and calls that function directly -- one mapping, not two
  that can drift -- and
  `test_adapt_claim_record_matches_bench_run_checks_adapt_record` proves
  the delegation is wired by comparing both on three real records from
  `bench/fake_done/trajectories/claude.jsonl`.
- **Calibration's printed denominators.** `tests/test_calibration.py`'s
  `test_printed_denominators_never_exceed_the_independently_recomputed_alive_count`
  (parametrised over all six checks) independently re-parses both
  results files and re-runs `coverage.coverage_map()` in a fresh pass
  written only in the test, and asserts `calibration.json`'s own
  ALIVE-restricted denominators and hit counts match -- the regression
  test for the flattering-denominator defect itself.
