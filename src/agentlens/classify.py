"""Rule-based failure classifier. Looks at a recorded run and guesses WHY it failed.

These are heuristics, not ground truth: good for triage, and for building a labeled dataset.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Optional

LABELS = ("looping", "wrong_tool", "bad_arguments", "tool_error",
          "crash", "empty_answer", "tool_call_as_text", "silent_wrong_answer")


def _load(text: Optional[str]) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def classify_run(spans: list[Any], run_status: str) -> Optional[str]:
    """Return a label from LABELS, or None if no structural problem is visible."""
    calls: list[tuple[str, str]] = []
    wrong_tool = bad_args = False

    for s in spans:
        if s["kind"] != "llm":
            continue
        known = set(_load(s["input_json"]).get("tool_names", []))
        for c in _load(s["output_json"]).get("tool_calls", []):
            calls.append((c["name"], c["arguments"]))
            if known and c["name"] not in known:
                wrong_tool = True
            try:
                json.loads(c["arguments"] or "{}")
            except ValueError:
                bad_args = True

    if run_status == "max_steps" or max(Counter(calls).values(), default=0) >= 3:
        return "looping"
    if wrong_tool:
        return "wrong_tool"

    tool_errors = [s["error"] for s in spans if s["kind"] == "tool" and s["error"]]
    if bad_args or any(e.startswith(("TypeError", "KeyError")) for e in tool_errors):
        return "bad_arguments"
    if tool_errors:
        return "tool_error"
    llm_spans = [s for s in spans if s["kind"] == "llm" and s["output_json"]]
    if llm_spans:
        last = _load(llm_spans[-1]["output_json"])
        text = (last.get("content") or "").strip()
        if not last.get("tool_calls"):
            if not text:
                return "empty_answer"
            if text.startswith(("{", "[")) and '"name"' in text:
                return "tool_call_as_text"
    return None