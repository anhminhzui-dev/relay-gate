#!/usr/bin/env python3
"""Streaming completion-claim extractor for Relay Gate bench fixtures.

Reads two agent-transcript stores (Claude Code session JSONL, Codex rollout
JSONL) and emits one JSON-Lines record per detected "completion claim" --
a sentence an agent said to a human, that looks like a done/pass/verified
statement -- together with the tool actions that immediately preceded it.

Schema, redaction rules and scope notes: see bench/README.md next to this
file. Do not read that as a substitute for reading this docstring; keep
both in sync when either changes.

Memory/privacy contract this script must hold:
  - stream every file line by line; never read a whole file into memory.
  - skip (not crash on) any single line over MAX_LINE_BYTES.
  - a hard per-file wall-clock cap (PER_FILE_SECONDS) and a total cap
    (--max-seconds) that the script enforces on itself.
  - only tool names, path/command-shaped argument values, and a short
    (<=200 char) slice of claim text ever leave this script -- never raw
    tool_result/output content, never full command argument blobs, never
    essay/document text.
  - a best-effort secret redaction pass runs on every string before it is
    written out or truncated.
"""
import argparse
import glob
import json
import os
import re
import time
import uuid
from collections import deque

MAX_LINE_BYTES = 200 * 1024          # skip any line bigger than this
PER_FILE_SECONDS = 5.0               # hard wall-clock cap per input file
MAX_PRECEDING_ACTIONS = 40           # rolling window size
CLAIM_TEXT_CHARS = 200               # claim_text is truncated to this many chars
TARGET_CHARS = 300                   # action target (path/command) truncation

DEFAULT_CLAUDE_GLOB = os.environ.get(
    "RELAY_GATE_CLAUDE_GLOB", os.path.expanduser("~/.claude/projects/*/*.jsonl")
)
DEFAULT_CODEX_GLOB = os.environ.get(
    "RELAY_GATE_CODEX_GLOB", os.path.expanduser("~/.codex/sessions/**/*.jsonl")
)
DEFAULT_OUT_DIR = os.environ.get("RELAY_GATE_TRAJECTORIES_DIR", "./data/trajectories")

# --- privacy: secret redaction ---------------------------------------------
# sk- keys, key=/token=/Bearer headers, and any run of 32+ base64/hex chars
# (also happens to catch Codex's Fernet-style "gAAAAA..." ciphertext blobs).
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{10,}"
    r"|key\s*=\s*\S+"
    r"|token\s*=\s*\S+"
    r"|Bearer\s+\S+"
    r"|[A-Za-z0-9+/_\-]{32,})",
    re.IGNORECASE,
)


def redact(text):
    if not text:
        return text
    return SECRET_RE.sub("<REDACTED>", text)


# --- claim detection --------------------------------------------------------
# Scoped to assistant-authored visible text only (never a bare-word scan over
# a whole line -- boilerplate/system-prompt text collides with these words
# constantly and would swamp genuine claims). Generic set the task asked for,
# plus the estate's own observed real phrasings (CLAUDE.md / CHANGELOG.md).
DONE_PHRASES = [
    r"\bdone\b", r"\bcomplete\b", r"\bcompleted\b", r"\bpassed\b",
    r"\ball tests pass\b", r"\bPASS\b",
    r"\bbuilt\b", r"\bwired end to end\b", r"\bcured\b",
    r"\btests\s+\d+\s+of\s+\d+\b", r"\bgreen\b", r"\bstable at zero\b",
    r"\bcold-proven\b", r"\bbyte-verified\b", r"\bhead-verified\b",
    r"\bproven\b", r"\back\b", r"\back_with_fixes\b",
    r"\bclosed\b", r"\bcloses\b", r"\bdone_contract\b",
    r"\bgo decision\b", r"\bverified\b",
]
DONE_RE = re.compile("|".join(DONE_PHRASES), re.IGNORECASE)


# --- streaming line reader ---------------------------------------------------
def iter_lines(path, deadline, max_line_bytes=MAX_LINE_BYTES):
    """Yield (line_no, text_or_None) reading in binary mode, byte-capped.

    text is None for any physical line whose byte length exceeds
    max_line_bytes (the rest of that oversized line is discarded, not
    buffered). Stops early once time.monotonic() >= deadline.
    """
    with open(path, "rb") as f:
        line_no = 0
        while True:
            if time.monotonic() >= deadline:
                return
            raw = f.readline(max_line_bytes + 1)
            if raw == b"":
                return
            line_no += 1
            if len(raw) > max_line_bytes:
                if not raw.endswith(b"\n"):
                    while True:
                        more = f.readline(65536)
                        if more == b"" or more.endswith(b"\n"):
                            break
                yield line_no, None
                continue
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            yield line_no, text


# --- action-argument extraction (path/command only, never content) ---------
def _first_pathlike(d, keys):
    for key in keys:
        if key in d and d[key] is not None:
            val = d[key]
            if isinstance(val, list):
                val = " ".join(str(x) for x in val)
            return redact(str(val))[:TARGET_CHARS]
    return "MISSING"


CLAUDE_PATH_KEYS = ("file_path", "path", "command", "pattern", "url", "notebook_path", "cmd", "script")
CODEX_PATH_KEYS = ("command", "path", "file_path", "cmd", "pattern", "url", "script")


def extract_claude_target(input_obj):
    if not isinstance(input_obj, dict):
        return "MISSING"
    return _first_pathlike(input_obj, CLAUDE_PATH_KEYS)


def extract_codex_target(arguments_raw):
    if not arguments_raw:
        return "MISSING"
    if isinstance(arguments_raw, str) and arguments_raw.startswith("gAAAAA"):
        return "<ENCRYPTED>"
    try:
        parsed = json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
    except (ValueError, TypeError):
        return "MISSING"
    if isinstance(parsed, dict):
        return _first_pathlike(parsed, CODEX_PATH_KEYS)
    return "MISSING"


def make_record(source, path, line_no, ts, text, actions, session_id):
    return {
        "claim_id": uuid.uuid4().hex,
        "source": source,
        "file": path,
        "line_no": line_no,
        "timestamp": ts if ts is not None else "MISSING",
        "claim_text": redact(text)[:CLAIM_TEXT_CHARS],
        "preceding_actions": list(actions),
        "session_id": session_id if session_id else "MISSING",
    }


# --- per-file processors -----------------------------------------------------
def process_claude_file(path, out_f, global_deadline, counters):
    try:
        size = os.path.getsize(path)
    except OSError:
        counters["files_skipped"] += 1
        return
    if size == 0:
        counters["files_skipped"] += 1
        return

    file_deadline = min(time.monotonic() + PER_FILE_SECONDS, global_deadline)
    actions = deque(maxlen=MAX_PRECEDING_ACTIONS)
    saw_line = False
    try:
        for line_no, text in iter_lines(path, file_deadline):
            saw_line = True
            if text is None:
                continue
            try:
                obj = json.loads(text)
            except (ValueError, TypeError):
                continue
            if obj.get("type") != "assistant":
                continue
            message = obj.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if not isinstance(content, list):
                continue
            session_id = obj.get("sessionId") or message.get("session_id") or "MISSING"
            ts = obj.get("timestamp")
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    tool = block.get("name") or "MISSING"
                    target = extract_claude_target(block.get("input"))
                    actions.append({"tool": tool, "target": target, "timestamp": ts if ts is not None else "MISSING"})
                elif btype == "text" and not obj.get("isMeta"):
                    txt = block.get("text") or ""
                    if txt and DONE_RE.search(txt):
                        record = make_record("claude", path, line_no, ts, txt, actions, session_id)
                        out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        counters["claims_found"] += 1
                        counters["actions_kept"] += len(record["preceding_actions"])
    except OSError:
        counters["files_skipped"] += 1
        return
    if not saw_line:
        counters["files_skipped"] += 1
    if time.monotonic() >= file_deadline:
        counters["files_capped"] += 1


def process_codex_file(path, out_f, global_deadline, counters):
    try:
        size = os.path.getsize(path)
    except OSError:
        counters["files_skipped"] += 1
        return
    if size == 0:
        counters["files_skipped"] += 1
        return

    file_deadline = min(time.monotonic() + PER_FILE_SECONDS, global_deadline)
    actions = deque(maxlen=MAX_PRECEDING_ACTIONS)
    session_id = "MISSING"
    saw_line = False
    try:
        for line_no, text in iter_lines(path, file_deadline):
            saw_line = True
            if text is None:
                continue
            try:
                obj = json.loads(text)
            except (ValueError, TypeError):
                continue
            ttype = obj.get("type")
            ts = obj.get("timestamp")
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            if ttype == "session_meta":
                session_id = payload.get("session_id") or payload.get("id") or session_id
                continue
            if ttype != "response_item":
                continue
            ptype = payload.get("type")
            if ptype == "function_call":
                tool = payload.get("name") or "MISSING"
                target = extract_codex_target(payload.get("arguments"))
                actions.append({"tool": tool, "target": target, "timestamp": ts if ts is not None else "MISSING"})
            elif ptype == "message" and payload.get("role") == "assistant":
                content = payload.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "output_text":
                        txt = block.get("text") or ""
                        if txt and DONE_RE.search(txt):
                            record = make_record("codex", path, line_no, ts, txt, actions, session_id)
                            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                            counters["claims_found"] += 1
                            counters["actions_kept"] += len(record["preceding_actions"])
    except OSError:
        counters["files_skipped"] += 1
        return
    if not saw_line:
        counters["files_skipped"] += 1
    if time.monotonic() >= file_deadline:
        counters["files_capped"] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-files", type=int, default=None,
                         help="max files to read PER SOURCE (claude and codex each capped independently)")
    parser.add_argument("--max-seconds", type=float, default=3600.0,
                         help="total wall-clock budget across both sources combined")
    parser.add_argument("--claude-glob", default=DEFAULT_CLAUDE_GLOB)
    parser.add_argument("--codex-glob", default=DEFAULT_CODEX_GLOB)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    claude_files = sorted(glob.glob(args.claude_glob))
    codex_files = sorted(glob.glob(args.codex_glob, recursive=True))
    if args.limit_files is not None:
        claude_files = claude_files[: args.limit_files]
        codex_files = codex_files[: args.limit_files]

    counters = {
        "files_seen": 0, "files_skipped": 0, "files_capped": 0,
        "claims_found": 0, "actions_kept": 0,
    }

    start = time.monotonic()
    global_deadline = start + args.max_seconds
    capped_total = False

    claude_out_path = os.path.join(args.out_dir, "claude.jsonl")
    codex_out_path = os.path.join(args.out_dir, "codex.jsonl")

    with open(claude_out_path, "w", encoding="utf-8") as claude_out:
        for path in claude_files:
            if time.monotonic() >= global_deadline:
                capped_total = True
                break
            counters["files_seen"] += 1
            process_claude_file(path, claude_out, global_deadline, counters)
            claude_out.flush()

    with open(codex_out_path, "w", encoding="utf-8") as codex_out:
        for path in codex_files:
            if time.monotonic() >= global_deadline:
                capped_total = True
                break
            counters["files_seen"] += 1
            process_codex_file(path, codex_out, global_deadline, counters)
            codex_out.flush()

    elapsed = time.monotonic() - start
    print(
        "SUMMARY files_seen={files_seen} files_skipped={files_skipped} files_capped={files_capped} "
        "claims_found={claims_found} actions_kept={actions_kept} claude_files_selected={cf} "
        "codex_files_selected={xf} capped_total={capped_total} elapsed_sec={elapsed:.1f}".format(
            files_seen=counters["files_seen"],
            files_skipped=counters["files_skipped"],
            files_capped=counters["files_capped"],
            claims_found=counters["claims_found"],
            actions_kept=counters["actions_kept"],
            cf=len(claude_files),
            xf=len(codex_files),
            capped_total=capped_total,
            elapsed=elapsed,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
