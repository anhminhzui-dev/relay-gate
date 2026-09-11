#!/usr/bin/env python3
"""Adapter: AgentRewardBench web-agent trajectories -> relay_gate.schema.Trajectory.

Source: AgentRewardBench (arXiv 2504.08942, "AgentRewardBench: Evaluating
Automatic Evaluations of Web Agent Trajectories", McGill NLP). Paper page:
https://arxiv.org/abs/2504.08942 -- "We release the benchmark at:
https://agent-reward-bench.github.io". Code:
https://github.com/McGill-NLP/agent-reward-bench. Data (Hugging Face
dataset, CC BY 4.0 per the HF dataset-card license field):
https://huggingface.co/datasets/McGill-NLP/agent-reward-bench -- 1,408
expert annotation rows over 1,302 trajectories across 5 benchmark splits
(assistantbench, visualwebarena, webarena x2 variants, workarena) and 4
agent/model configurations (Qwen2.5-VL-72B, Claude-3.7-Sonnet,
GPT-4o-2024-11-20, Llama-3.3-70B). No login or gated download was hit at
any point: the annotations CSV lives in the GitHub repo (public raw file)
and the per-trajectory JSON files resolve from the public HF dataset
`resolve/main` path with no auth header.

Two on-disk pieces this adapter reads, both under the directory named by
the ``RELAY_GATE_ARB_CLEANED_DIR`` env var's parent (default
``./external_data/arb/data/``, outside this repo, per the fetch rule):

  1. annotations.csv (265,137 bytes, 1,408 data rows), downloaded from
     https://raw.githubusercontent.com/McGill-NLP/agent-reward-bench/main/agent_reward_bench/data/annotations.csv
     Columns (verbatim header row): annotator_name, benchmark, task_id,
     model_name, exp_name, trajectory_success, trajectory_side_effect,
     trajectory_optimality, trajectory_looping. This is the EXPERT SUCCESS
     JUDGEMENT: trajectory_success in {"Successful", "Unsuccessful",
     "Unsure"}. Most (task_id, exp_name) pairs carry >=2 independent
     annotator rows (annotator_name in {A,B,C,D,F, ...}, 8 distinct
     annotators total across the dataset).

  2. cleaned/*.json, one file per trajectory, downloaded individually from
     https://huggingface.co/datasets/McGill-NLP/agent-reward-bench/resolve/main/cleaned/<benchmark>/<exp_name_without_"_on_"_suffix>/<exp_name>/<benchmark>.<task_num>.json
     Every file downloaded here is for benchmark="webarena", exp_name=
     "GenericAgent-gpt-4o-2024-11-20_on_webarena" (one agent x one
     benchmark out of 16 agent x benchmark combinations in the full
     dataset), chosen because the full HF `cleaned/` tree is 38.4 GB
     (dataset-card size) and this one benchmark/agent folder alone sums to
     1,716,963,876 bytes (1.60 GB) across its 100 files, with a single
     largest file at 184,198,100 bytes (webarena.417.json) -- too large to
     download in bulk inside this task's budget, so files were fetched one
     at a time with a per-file cap (curl --max-filesize), not the whole
     split. See ARB_RESULTS.md for the exact task_id list downloaded, what
     was skipped and why (a size cap, not a login/paywall -- nothing here
     triggered bench/external/arb/MISSING.md).

Record shape (one dict per downloaded *.json file, BrowserGym/AgentLab
trajectory format, NOT the coding-agent {tool,args,output} shape Relay
Gate's schema doc uses as its worked example):

    {
      "benchmark": "webarena", "agent": "GenericAgent-gpt-4o-2024-11-20",
      "experiment": "GenericAgent-gpt-4o-2024-11-20_on_webarena",
      "goal": "<task instruction text>",
      "summary_info": {"n_steps": int, "cum_reward": float, ...},
      "steps": [
        {"num": 0, "reasoning": "<agent's stated reasoning>",
         "action": "click('147')" | "send_msg_to_user(\"...\")" |
                    "report_infeasible(\"...\")" | "goto(\"...\")" | ...,
         "screenshot_path": "trajectories/screenshots/<benchmark>/<agent>/<benchmark>.<task_num>/screenshot_step_N.png",
         "url": str, "last_action_error": str, "axtree_pruned": str, ...},
        ...
        # the LAST entry in "steps" typically has action=None and
        # reasoning=None -- it is the terminal observation snapshot taken
        # AFTER the last real action, not a new action itself.
      ]
    }

No field named "task_id" is present inside the JSON itself (checked: the
top-level key list has no such key). task_id is recovered from the
downloaded filename (e.g. "webarena.683.json" -> "webarena.683"), the
same convention the dataset's own screenshot_path values encode
(".../<benchmark>/<agent>/webarena.683/screenshot_step_0.png"). This
adapter cross-checks the filename-derived task_id against that embedded
screenshot_path folder name where a screenshot_path is present, and raises
if they disagree (see _verify_task_id) rather than silently trusting the
filename -- a "checked, not assumed" guard, not a defect found.

What "the agent's own final claim" means on THIS action space, stated
plainly because it is the single most important, most fact-checkable
mapping decision in this file: BrowserGym's action space gives an agent
exactly two ways to end an episode by choice: `send_msg_to_user(text)`
(deliver a final answer/message to the simulated user and stop) and
`report_infeasible(text)` (declare the task cannot be done and stop). Every
other action (click, fill, goto, scroll, noop, new_tab, ...) is a plain
environment interaction, not a claim about the task's outcome. So:

  - final_claim (the Trajectory field Relay Gate's own rules read) is set
    to the quoted-string argument of the trajectory's LAST non-null action
    when that action is `send_msg_to_user` OR `report_infeasible`,
    else "" (no explicit statement was ever made -- the run ended by
    step-cap or error on a bare UI action).
  - Separately (external to the Trajectory schema, used only for this
    run's own label bucketing in score_arb.py, not fed to any Relay Gate
    rule): "ended as if done" = the last action specifically was
    `send_msg_to_user`. `report_infeasible` is NOT counted as "ended as
    done" -- it is BrowserGym's dedicated "I could not do this" terminal
    action, the opposite of a completion claim, even though its text is
    also carried into final_claim for completeness/audit.

Coverage limitation, stated once here rather than re-derived per rule (the
same discipline the MAST adapter's docstring uses, see external_adapter.py):
BrowserGym actions are UI verbs (click/fill/goto/scroll/send_msg_to_user/
report_infeasible/...) over element ids ("bids"), never file paths, shell
commands, or diffs. So on this source:
    - check_destructive_without_read needs args["path"/"target"/"table"/
      "file"]; this adapter's args carry only {"raw": <action text>,
      "text": <first quoted string arg, if any>}, never those four keys,
      so this rule is a structural no-op here (0 fires expected, checked
      in ARB_RESULTS.md, not assumed).
    - check_secret_leak needs a write/commit/post/send/print/log/reply/
      publish-shaped TOOL NAME; "send_msg_to_user" contains "send", so
      this rule CAN engage in principle on send_msg_to_user steps if a
      secret-shaped string ever appeared in one -- checked in
      ARB_RESULTS.md.
    - check_test_disabled and check_validation_bypassed both need a
      line starting (true start-of-line) with "+" or "-" (diff-hunk
      shaped text). No step here ever carries a diff; both are structural
      no-ops on this source.
    - check_unknown_tool_call: allowed_tools is always () (BrowserGym
      records no declared allow-list), so this rule is a structural
      no-op by construction, 0 of N, not a finding about the data.
    - check_false_completion_claim is the one rule built to engage with
      final_claim text; whether it actually fires on THIS source's
      completion phrasing (which tends to be a direct factual answer, not
      coding-agent phrasing like "all tests pass") is measured, not
      assumed -- see ARB_RESULTS.md.
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
from collections import defaultdict

from relay_gate.schema import Step, Trajectory

MAX_STEPS_PER_TRAJECTORY = 80
MAX_STEP_CHARS = 4000
MAX_CLAIM_CHARS = 1000

_ACTION_HEAD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$", re.DOTALL)
_QUOTED_STRING_RE = re.compile(r"""(['"])(.*?)(?<!\\)\1""", re.DOTALL)


def _parse_action(action: str) -> tuple[str, dict]:
    """Parse one BrowserGym action string into (tool_name, args).

    args always carries the raw action text under "raw"; when the action
    has at least one quoted string argument (true for send_msg_to_user,
    report_infeasible, fill, and most others), that first argument's
    unescaped text is additionally carried under "text".
    """
    m = _ACTION_HEAD_RE.match(action.strip())
    if not m:
        return "unknown_action", {"raw": action}
    name, inner = m.group(1), m.group(2)
    args: dict = {"raw": action}
    sm = _QUOTED_STRING_RE.search(inner)
    if sm:
        args["text"] = sm.group(2).replace('\\"', '"').replace("\\'", "'")
    return name, args


def _step_output(raw_step: dict) -> str:
    parts: list[str] = []
    err = raw_step.get("last_action_error")
    if err:
        parts.append(f"[last_action_error] {err}")
    reasoning = raw_step.get("reasoning")
    if reasoning:
        parts.append(str(reasoning))
    axtree = raw_step.get("axtree_pruned")
    if axtree:
        parts.append(str(axtree)[:300])
    return "\n".join(parts)[:MAX_STEP_CHARS]


def _steps_from_record(rec: dict) -> list[Step]:
    raw_steps = [s for s in rec.get("steps", []) if s.get("action")]
    truncated = len(raw_steps) > MAX_STEPS_PER_TRAJECTORY
    if truncated:
        raw_steps = raw_steps[:MAX_STEPS_PER_TRAJECTORY]
    steps = []
    for raw in raw_steps:
        tool, args = _parse_action(str(raw["action"]))
        steps.append(Step(tool=tool, args=args, output=_step_output(raw)))
    return steps


def _last_action_kind(rec: dict) -> tuple[str, str]:
    """Return (kind, text) from the trajectory's LAST non-null action.

    kind is one of "SEND_MSG", "INFEASIBLE", "OTHER", "NONE". text is the
    quoted-string argument of that action ("" if none, or if kind is
    OTHER/NONE). See module docstring for why only SEND_MSG counts as
    "ended as if done".
    """
    last_action = None
    for raw in rec.get("steps", []):
        if raw.get("action"):
            last_action = str(raw["action"])
    if last_action is None:
        return "NONE", ""
    tool, args = _parse_action(last_action)
    if tool == "send_msg_to_user":
        return "SEND_MSG", args.get("text", "")
    if tool == "report_infeasible":
        return "INFEASIBLE", args.get("text", "")
    return "OTHER", ""


def _task_id_from_screenshot(rec: dict) -> str | None:
    benchmark = str(rec.get("benchmark", ""))
    for raw in rec.get("steps", []):
        sp = raw.get("screenshot_path")
        if not sp:
            continue
        for part in str(sp).split("/"):
            if part.startswith(benchmark + "."):
                return part
    return None


def _verify_task_id(rec: dict, task_id: str) -> None:
    embedded = _task_id_from_screenshot(rec)
    if embedded is not None and embedded != task_id:
        raise ValueError(
            f"filename-derived task_id {task_id!r} disagrees with screenshot_path-embedded "
            f"task_id {embedded!r} -- refusing to silently trust the filename"
        )


def record_to_trajectory(rec: dict, task_id: str) -> Trajectory:
    _verify_task_id(rec, task_id)
    exp_name = str(rec.get("experiment", "unknown"))
    trajectory_id = f"arb_{task_id}_{exp_name}"
    steps = _steps_from_record(rec)
    _, claim_text = _last_action_kind(rec)
    return Trajectory(
        trajectory_id=trajectory_id,
        allowed_tools=(),
        steps=tuple(steps),
        final_claim=claim_text[:MAX_CLAIM_CHARS],
    )


def load_cleaned_records(data_dir: str) -> list[tuple[str, dict]]:
    """Return [(task_id, record_dict), ...] for every *.json file in
    data_dir, sorted by numeric task id for stable output ordering."""

    def _num(p: pathlib.Path) -> int:
        try:
            return int(p.stem.split(".")[-1])
        except ValueError:
            return -1

    out: list[tuple[str, dict]] = []
    for p in sorted(pathlib.Path(data_dir).glob("*.json"), key=_num):
        with open(p, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        out.append((p.stem, rec))
    return out


def load_annotation_votes(annotations_csv_path: str) -> dict[tuple[str, str, str], list[str]]:
    """Return {(benchmark, task_id, exp_name): [trajectory_success, ...]}."""
    votes: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    with open(annotations_csv_path, "r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["benchmark"], row["task_id"], row["exp_name"])
            votes[key].append(row["trajectory_success"])
    return dict(votes)


def expert_label(
    votes: dict[tuple[str, str, str], list[str]], benchmark: str, task_id: str, exp_name: str
) -> str:
    """"Successful" / "Unsuccessful" iff every annotator row for this
    (benchmark, task_id, exp_name) agrees; "NO_ANNOTATION" if no row
    exists; otherwise "DISAGREE:<sorted distinct values>" (covers mixed
    Successful/Unsuccessful votes and any "Unsure" vote)."""
    values = set(votes.get((benchmark, task_id, exp_name), []))
    if not values:
        return "NO_ANNOTATION"
    if values == {"Successful"}:
        return "Successful"
    if values == {"Unsuccessful"}:
        return "Unsuccessful"
    return "DISAGREE:" + ",".join(sorted(values))


def bucket_of(expert_lbl: str, action_kind: str) -> tuple[str, str]:
    """Map (expert_label, last_action_kind) -> (bucket, reason).

    bucket is one of FALSE_DONE / CLEAN / EXCLUDED, per the brief:
    FALSE_DONE = agent ended as if done (send_msg_to_user) AND expert says
    Unsuccessful. CLEAN = expert says Successful (full stop, regardless of
    how the episode ended). Everything else is EXCLUDED, with a reason:
    an Unsuccessful trajectory that never claimed/implied completion (no
    false claim to measure), or annotator disagreement/no-annotation (no
    settled ground truth).
    """
    if expert_lbl == "Successful":
        return "CLEAN", "expert=Successful"
    if expert_lbl == "Unsuccessful":
        if action_kind == "SEND_MSG":
            return "FALSE_DONE", "expert=Unsuccessful, last action=send_msg_to_user (claimed/implied completion)"
        return "EXCLUDED", f"expert=Unsuccessful but last action kind={action_kind} (no completion claim made)"
    if expert_lbl == "NO_ANNOTATION":
        return "EXCLUDED", "no expert annotation for this (benchmark, task_id, exp_name)"
    return "EXCLUDED", f"annotator disagreement ({expert_lbl})"


def iter_labelled_trajectories(data_dir: str, annotations_csv_path: str):
    """Yield (Trajectory, bucket, detail_dict) for every downloaded record.

    bucket in {"FALSE_DONE", "CLEAN", "EXCLUDED"}. detail_dict carries
    task_id, benchmark, exp_name, expert_label, action_kind, reason and
    the record's own summary_info.n_steps for the per-record report line.
    """
    votes = load_annotation_votes(annotations_csv_path)
    for task_id, rec in load_cleaned_records(data_dir):
        benchmark = str(rec.get("benchmark", "unknown"))
        exp_name = str(rec.get("experiment", "unknown"))
        traj = record_to_trajectory(rec, task_id)
        kind, _ = _last_action_kind(rec)
        lbl = expert_label(votes, benchmark, task_id, exp_name)
        bucket, reason = bucket_of(lbl, kind)
        detail = {
            "task_id": task_id,
            "benchmark": benchmark,
            "exp_name": exp_name,
            "expert_label": lbl,
            "action_kind": kind,
            "reason": reason,
            "n_steps_recorded": rec.get("summary_info", {}).get("n_steps"),
        }
        yield traj, bucket, detail
