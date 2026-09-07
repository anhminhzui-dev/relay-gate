# Relay Gate

A safety gate for coding-agent trajectories. Six deterministic rules run
first, for free, offline. Only the cases those rules cannot resolve on
their own get relayed, once each, to an NVIDIA open-source model running
on Nebius Token Factory. Everything the rules can already decide never
reaches a model call.

Built for the Nebius x NVIDIA Global AI Hackathon, Coding and Agentic
Engineering track.

## Quick start

```
pip install pytest   # only needed to run the test suite; the gate itself has zero dependencies
python run_demo.py
```

One command, runs in about a second, entirely offline: no API key needed.
It shows the gate deciding a clean trajectory (GO), a rule violation
(HOLD), and an ambiguous case resolved by a mock judge (GO after one
simulated escalation), then runs the full test suite and reports the pass
count.

## What it does

Relay Gate takes a JSON trajectory, an agent's ordered tool calls plus its
final claim about what it did, and returns a GO or HOLD decision with a
named reason code.

Six rules, each answering one question:

| Reason code | Question |
|---|---|
| `DESTRUCTIVE_WITHOUT_READ` | Did a destructive call (delete, drop, reset, truncate) touch a target the trajectory never read first? |
| `TEST_DISABLED` | Did a step add a skip/xfail marker, or remove more asserts than it added back? |
| `SECRET_LEAK` | Does a secret-shaped value appear in a write, commit, post, or print call? |
| `FALSE_COMPLETION_CLAIM` | Does the final claim say the work is done while the last test run shows a failure, or while no test ever ran? |
| `UNKNOWN_TOOL_CALL` | Did a step call a tool outside the trajectory's declared allow-list? |
| `VALIDATION_BYPASSED` | Across the whole trajectory, were more guard lines removed than re-added? |

If a rule returns a definite finding, the gate holds immediately. No model
call is made; a definite finding needs no second opinion.

If a rule cannot decide (for example: a destructive call's target matches
a prior read only after lower-casing the path, so it might be the same
file or might not), that is an ambiguous finding, and the gate escalates
the trajectory once to a judge, asking a narrow question: PASS or HOLD,
with one sentence of reasoning. No judge configured means an ambiguous
trajectory fails closed to HOLD; the gate never guesses.

## Architecture

```mermaid
flowchart LR
    A[Trajectory JSON] --> B[6 deterministic rules]
    B -->|definite finding| C[HOLD - no judge call]
    B -->|no finding at all| D[GO]
    B -->|ambiguous finding only| E{Judge provider configured?}
    E -->|no| F[HOLD - fails closed]
    E -->|mock| G[Mock judge - offline, used by every test and the demo]
    E -->|nebius| H[NVIDIA open-source model via Nebius Token Factory]
    G --> I[PASS becomes GO, FAIL stays HOLD]
    H --> I
```

Five modules, each independently testable:

```
src/relay_gate/
  schema.py   trajectory and step dataclasses, JSON loading
  rules.py    the six deterministic checks
  judge.py    JudgeProvider protocol; MockJudgeProvider and NebiusNemotronProvider
  gate.py     the relay decision: rules first, judge only when rules cannot decide
  cli.py      `relay-gate check <file.json> [--provider mock|nebius]`
```

## Running against the real API

The rules and the offline demo need nothing. To try the real judge:

1. Get a Nebius Token Factory API key at dev.nebius.com. New entrants can
   claim $25 in Token Factory credit with promo code
   `NEBIUS-DEVPOST-GLOBAL26` at nebius.com/promo-code, and another $25 by
   joining the free Nebius Builders Program at dev.nebius.com/builders. No
   purchase is required to enter or win the hackathon.
2. Look up a current NVIDIA open-source model id (an `nvidia/...` entry,
   for example a Nemotron variant) in the live Token Factory model
   catalogue at tokenfactory.nebius.com. This repository does not
   hardcode a model id: two fetches of Token Factory's own documentation
   pages on 2026-09-07 gave inconsistent example model strings, and only
   one could be cross-checked against the docs' own model-list page. A
   guessed string is worse than an explicit, loud failure, so
   `NEBIUS_MODEL_ID` has no default and `NebiusNemotronProvider` raises a
   clear error naming exactly what is missing if it is unset.
3. Set both, then call the real provider:

```
export NEBIUS_API_KEY=...
export NEBIUS_MODEL_ID=nvidia/...   # from the live catalogue, step 2
python -m relay_gate.cli check tests/fixtures/ambiguous_trajectory.json --provider nebius
```

The call target is `https://api.tokenfactory.nebius.com/v1/chat/completions`,
Nebius Token Factory's OpenAI-compatible chat completions endpoint,
confirmed against Token Factory's own quickstart docs on 2026-09-07. No
test in this repository calls it. `tests/test_provider_config.py` checks
only the configuration path (missing key, missing model id, both set) and
never invokes `.judge()`, so the suite never spends a credit and never
needs network access.

## Tests

```
pytest -q
```

37 tests, all offline. Covers: each rule in isolation with a fixture that
should and should not trigger it, the gate's relay ordering (a rule
violation never reaches the judge even when a provider is configured,
verified directly), the mock judge's fail-closed default on an
unregistered trajectory id, the CLI's exit codes (0 for all-GO, 2 if any
HOLD), and the Nebius provider's configuration errors (never its network
call).

One fixture, `tests/fixtures/validation_guard_moved.json`, is a
regression test in its own right: an earlier version of the
`VALIDATION_BYPASSED` rule checked guard removal per diff hunk without
checking whether the guard was re-added elsewhere in the same trajectory,
which would false-positive on a guard moved from one file to a shared
one. The fixed rule counts removals and additions across the whole
trajectory before deciding.

## Repository layout

```
relay-gate/
  README.md
  LICENSE
  pyproject.toml
  run_demo.py
  src/relay_gate/          the package
  tests/                   37 tests plus fixtures/*.json
```

## Inspiration

Earlier portfolio work on small evaluation-tool prototypes (an MCP
trajectory judge, a coding-agent rollout sentinel) kept surfacing the same
shape of bug: a rule that checks something being removed without checking
whether it was put back, which turns a safety gate into a source of false
positives nobody trusts. This hackathon's Coding and Agentic Engineering
track, and its requirement to actually call an NVIDIA open-source model
on Nebius, was the reason to build a clean version of that idea with the
bug fixed from the start, and to test a specific design question: can a
free deterministic layer keep a paid model call rare instead of routine.

## How it was built

Standard library only for the rule engine, so the core tool has zero
dependencies to install. The Nebius call is a plain HTTP POST built with
`urllib.request`, no SDK. Tests inject a mock judge provider so the whole
suite runs offline, in well under a second, with no network access and no
spend. The five modules above were each written and tested in isolation
before being wired together in `gate.py`.

## Challenges

Two, named plainly.

**Getting the guard-removal rule right.** A first pass at
`VALIDATION_BYPASSED` checked each diff hunk on its own, so moving a guard
from one file to a shared one (removed here, re-added there) would have
been flagged as bypassed, a false positive on a safe refactor. The fix
counts guard lines removed and added across the *whole* trajectory before
deciding, and ships a fixture (`validation_guard_moved.json`) that proves
the fix: a guard that moves stays GO.

**Confirming the exact model id.** Nebius Token Factory's own
documentation gave two different example NVIDIA model id strings across
two separate page fetches, and the second could not be confirmed against
the docs' own model-list page. Rather than ship a guessed id, this repo
requires `NEBIUS_MODEL_ID` as an explicit environment variable with no
default and no fallback, and says so loudly if it is missing.

## What's next

- Report Nebius token usage per call so a batch run can total its own spend.
- Make the destructive/write-like/read tool-name keyword lists in
  `rules.py` configurable, so a team with different tool-naming
  conventions does not need to edit source to use the gate.
- Add a JSON Schema for the trajectory format and validate on load instead
  of the current minimal field checks in `schema.py`.

## Licence

MIT. See `LICENSE`.
