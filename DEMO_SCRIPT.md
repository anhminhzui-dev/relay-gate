# Demo script: 2 minutes, shot list

Target length: 2:00. Devpost's cap for this hackathon is 3:00, so this
leaves buffer for a slower take. Record with the CLI/terminal at a large
font size; no slides needed, the terminal output is the visual.

| Time | Shot | Narration |
|---|---|---|
| 0:00-0:15 | Terminal, empty prompt. Type nothing yet, just show the repo folder listing (`ls`). | "Coding agents make destructive calls, disable tests, and claim they finished when they did not. Relay Gate checks their tool-call trajectories before you trust the result." |
| 0:15-0:30 | Run `python run_demo.py`. Let the first block ("1. clean trajectory") print. | "Six deterministic rules run first, for free, no model call. A clean trajectory: GO, zero judge calls." |
| 0:30-0:45 | Let the second block ("2. rule violation") print, pause on the JSON output. | "This one deletes a file it never read. The rule catches it directly: HOLD, `DESTRUCTIVE_WITHOUT_READ`. Still no judge call. A definite finding needs no second opinion." |
| 0:45-1:05 | Let the third block ("3. ambiguous case") print, pause on `judge_calls: 1` and the `ESCALATED_PASS` reason. | "This case is genuinely ambiguous: a deleted path matches an earlier read only after normalising case. The rules cannot decide, so, and only so, it escalates once to a judge." |
| 1:05-1:25 | Switch to a second terminal pane. Run the same ambiguous fixture with `--provider nebius` against a live Nebius Token Factory key, showing the real HTTP call and the NVIDIA-model JSON verdict come back. | "With a real key, that one call goes to an NVIDIA open-source model running on Nebius Token Factory over their OpenAI-compatible API. Everything the rules already settled never reaches it." |
| 1:25-1:40 | Show `README.md`'s architecture Mermaid block (scroll to it, or render it). | "Five small modules: schema, rules, judge, gate, CLI. Two providers behind one interface, mock for every test, Nebius for the real call." |
| 1:40-1:55 | Run `pytest -q` in the first pane, let the summary line print. | "Thirty-seven tests, all offline, including a regression test for a false positive an earlier version of this exact rule had: a guard moved between files, not bypassed." |
| 1:55-2:00 | Cut to the repo's README title / GitHub page. | "Relay Gate. One command to run, one call only when the rules cannot decide on their own." |

## Recording notes

- The clean, rule-violation, and mock-escalation shots (0:15-1:05) all come
  from one run of `python run_demo.py` and need no API key; record this
  part first and it is guaranteed to work every take.
- The live Nebius call (1:05-1:25) is the only part needing a real key and
  a set `NEBIUS_MODEL_ID` looked up from the live model catalogue (see
  README "Running against the real API"). Record this segment separately
  and splice it in; do not depend on network conditions during the main
  take.
- No claim about accuracy, precision, or error rate appears anywhere in
  this script or should appear in the recording. What the tool does is
  demonstrated by its own printed output (GO, HOLD, reason codes, test
  count), not by an unmeasured number.
