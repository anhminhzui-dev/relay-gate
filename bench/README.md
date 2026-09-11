# bench/extract_trajectories.py

Streaming extractor that turns real Claude Code and Codex agent transcripts
into bench fixtures for Relay Gate's "fake done" detector: one record per
completion-shaped claim an agent made to a human, with the tool actions that
led up to it.

Inputs (read-only, never modified):

- Claude Code sessions: `~/.claude/projects/*/*.jsonl` (override with `RELAY_GATE_CLAUDE_GLOB`)
- Codex rollouts: `~/.codex/sessions/**/*.jsonl` (override with `RELAY_GATE_CODEX_GLOB`)

Output (write-only target of this script):

- `./data/trajectories/claude.jsonl`
- `./data/trajectories/codex.jsonl`

Each run overwrites both output files from scratch (they are not append
logs) — the files always reflect the most recent invocation only.

## Usage

```
python extract_trajectories.py --limit-files 5 --max-seconds 3600
python extract_trajectories.py --limit-files 50 --max-seconds 3600
python extract_trajectories.py --max-seconds 480
```

| Flag | Meaning |
|---|---|
| `--limit-files N` | Cap files read **per source, independently** — the first N Claude files (sorted by filename) and, separately, the first N Codex files (sorted by full path). Omit for no cap. |
| `--max-seconds S` | Total wall-clock budget across both sources combined (default 3600). If the budget runs out mid-list, remaining files are simply never opened; the run ends and reports `capped_total=True` on its summary line. |
| `--claude-glob` / `--codex-glob` | Override the input glob (defaults above). |
| `--out-dir` | Override the output directory (default `./data/trajectories`). |

File-selection order matters for reproducibility and to dodge the
"actively-being-written file looks newest by mtime" trap: Codex files are
sorted by path (the rollout filename embeds an ISO timestamp, so this is
roughly chronological); Claude files are sorted by filename (session UUIDs,
not chronological, but stable across runs).

## Caps this script enforces on itself

- **200 KB max line size.** Any single physical line over 200 KB is read
  (in fixed-size chunks, never buffered whole) and discarded, not parsed.
  Counted implicitly — oversized lines simply yield no record.
- **5 second hard cap per input file.** A pathological file stops being
  read after 5 wall-clock seconds even if it is not finished; this shows
  up in the summary as `files_capped`.
- **`--max-seconds` total cap.** Checked before opening each new file (both
  inside a source's list and between the two sources). If hit, the run
  stops immediately and reports what it already wrote — nothing already
  streamed to disk is rolled back.
- Streaming only: files are read line-by-line in binary mode
  (`readline(size_hint)`), never `f.read()` or `readlines()`. No file's
  full content is ever resident in memory at once.

## Record schema (one JSON object per line, in `<source>.jsonl`)

```json
{
  "claim_id": "32-hex-char uuid4, unique per record",
  "source": "claude | codex",
  "file": "absolute path of the transcript this claim came from",
  "line_no": "1-based physical line number inside that file",
  "timestamp": "ISO8601 string from the transcript line, or \"MISSING\"",
  "claim_text": "first 200 chars of the claim sentence, after redaction",
  "preceding_actions": [
    {"tool": "tool/function name", "target": "path or command, redacted, or \"MISSING\"", "timestamp": "..."}
  ],
  "session_id": "the transcript's session/thread id, or \"MISSING\""
}
```

`preceding_actions` holds up to the 40 most recent tool actions seen
**earlier in the same file**, oldest first, immediately before the claim
line. It is a rolling window per file — it does not carry over between
files, and for Codex it does not follow `parent_thread_id` into a
different rollout file (a genuine scope limit: Codex subagent history
sometimes spans files; this extractor does not reconstruct that chain).

## What counts as a "completion claim"

Only visible, agent-authored text is scanned — never a whole raw JSON
line. This estate has already been burned by unscoped keyword scans: an
unscoped grep for done/complete/pass/verified against a raw Codex line hit
25/25 times on injected system-prompt/memory-summary boilerplate, not on a
real assistant claim. So:

- **Claude**: only `type:"assistant"` lines, only `content[].type:"text"`
  blocks, and only when the line is not `isMeta`. `thinking` blocks and
  `tool_use` blocks are never scanned for claim text.
- **Codex**: only `payload.type:"message"` with `payload.role:"assistant"`,
  and only `content[].type:"output_text"` blocks.

A claim is any such text containing one of a fixed phrase list (case
insensitive): the generic set `done, complete, completed, passed, all
tests pass, pass`, plus phrasings this estate's own CLAUDE.md/CHANGELOG.md
actually use — `built, wired end to end, cured, tests N of N, green,
stable at zero, cold-proven, byte-verified, head-verified, proven, ack,
ack_with_fixes, closed, closes, done_contract, go decision, verified`.

This is a **recall-favouring** filter, by design: it is meant to surface
candidate claim sentences for Relay Gate's downstream checks to judge, not
to itself decide true/false completion. Words like "proven" or "green"
will over-match relative to a strict definition; that is intentional here
and should not be mistaken for the finished detector.

## What is deliberately never extracted (privacy law)

Only tool names, path/command-shaped argument values, and short claim
snippets ever leave this script. Specifically excluded, always:

- Tool **results** / `function_call_output` / `tool_result` content —
  never read for extraction purposes.
- Full tool **inputs** — only a small allow-list of path/command-shaped
  keys is pulled out of a tool call's arguments
  (`file_path, path, command, pattern, url, notebook_path, cmd, script`
  for Claude; `command, path, file_path, cmd, pattern, url, script` for
  Codex). A field like `content`, `old_string`, `new_string` or a prompt
  body is never read, even if present in the same object — this is how
  essay text and full file bodies are kept out of the bench store.
- Codex inter-agent `send_message`/`agent_message` payloads whose
  arguments are Fernet-style ciphertext (`gAAAAA...`) are recorded as the
  literal string `<ENCRYPTED>`, never decoded or pattern-matched.
- Claim text is truncated to 200 chars and action targets to 300 chars,
  always **after** redaction (never before — slicing first could cut a
  secret pattern in half and leak the visible remainder).

### Redaction

Every string that becomes `claim_text` or an action `target` is passed
through one regex substitution before truncation:

```
(sk-[A-Za-z0-9_-]{10,} | key\s*=\s*\S+ | token\s*=\s*\S+ | Bearer\s+\S+ | [A-Za-z0-9+/_-]{32,})
  -> <REDACTED>
```

This also happens to catch the `gAAAAA...` ciphertext blobs (32+ base64
chars) even in the rare case they slip past the explicit `<ENCRYPTED>`
check above.

## Anti-fabrication

Any field this script cannot honestly populate — a tool call with no
path/command-shaped argument, a Codex file with no `session_meta` line yet
seen, a missing timestamp — is written as the literal string `"MISSING"`,
never guessed or substituted from an unrelated field.

## Summary line (last line of stdout on every run)

```
SUMMARY files_seen=<n> files_skipped=<n> files_capped=<n> claims_found=<n> actions_kept=<n> claude_files_selected=<n> codex_files_selected=<n> capped_total=<True|False> elapsed_sec=<f>
```

- `files_seen` — files this run actually opened (from both sources).
- `files_skipped` — of those, files that yielded zero lines (zero-byte,
  unreadable, or an OSError on open).
- `files_capped` — of those, files that hit the 5-second per-file cap
  before reaching end of file.
- `claims_found` — total claim records written across both output files.
- `actions_kept` — sum of `len(preceding_actions)` over every claim
  written (i.e. how many action records actually ended up on disk, not
  how many tool calls were merely seen in passing).
- `claude_files_selected` / `codex_files_selected` — how many files from
  each source's sorted list this run intended to process, after
  `--limit-files` slicing (may exceed `files_seen` if `--max-seconds` cut
  the run short).
- `capped_total` — `True` only if `--max-seconds` forced an early stop.
