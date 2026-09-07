"""Named reason codes.

Every HOLD, ABSTAIN, or ESCALATE outcome carries one of these codes so a
caller (or a person) can act on it without re-reading free text. Each code
below has one job; do not overload one code with two meanings.
"""

from enum import Enum


class ReasonCode(str, Enum):
    # --- deterministic HOLD reasons (no judge call needed) ---
    DESTRUCTIVE_WITHOUT_READ = "DESTRUCTIVE_WITHOUT_READ"
    TEST_DISABLED = "TEST_DISABLED"
    SECRET_LEAK = "SECRET_LEAK"
    FALSE_COMPLETION_CLAIM = "FALSE_COMPLETION_CLAIM"
    UNKNOWN_TOOL_CALL = "UNKNOWN_TOOL_CALL"
    VALIDATION_BYPASSED = "VALIDATION_BYPASSED"

    # --- ambiguous: rules cannot decide alone, escalate to the judge ---
    AMBIGUOUS_PATH_MATCH = "AMBIGUOUS_PATH_MATCH"
    AMBIGUOUS_COMPLETION_EVIDENCE = "AMBIGUOUS_COMPLETION_EVIDENCE"

    # --- escalation outcomes (only appear after a judge call was attempted) ---
    ESCALATED_PASS = "ESCALATED_PASS"
    ESCALATED_FAIL = "ESCALATED_FAIL"
    JUDGE_UNAVAILABLE = "JUDGE_UNAVAILABLE"

    # --- clean ---
    CLEAN = "CLEAN"
