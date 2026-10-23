"""Regression testing: cases with automatic checkers, a suite runner, and version comparison."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

from .classify import classify_run
from .tracer import Tracer

Check = Callable[[str], tuple[bool, str]]


# ---- checkers: each takes the agent's answer and returns (passed, explanation) ----
def contains(*needles: str, case: bool = False) -> Check:
    def check(answer: str):
        hay = answer if case else answer.lower()
        missing = [n for n in needles if (n if case else n.lower()) not in hay]
        return (not missing, "ok" if not missing else f"missing {missing}")
    return check


def not_contains(*needles: str) -> Check:
    def check(answer: str):
        found = [n for n in needles if n.lower() in answer.lower()]
        return (not found, "ok" if not found else f"should not contain {found}")
    return check


def number_equals(expected: float, tol: float = 1e-6) -> Check:
    """Passes if ANY number in the answer equals `expected` (commas and $ are ignored)."""
    def check(answer: str):
        nums = []
        for m in re.findall(r"-?\d[\d,]*\.?\d*", answer):
            try:
                nums.append(float(m.replace(",", "")))
            except ValueError:
                pass
        ok = any(abs(n - expected) <= tol for n in nums)
        return (ok, "ok" if ok else f"expected {expected}, found numbers {nums}")
    return check


@dataclass
class Case:
    id: str
    task: str
    check: Check


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    detail: str
    answer: str
    run_id: Optional[str]
    label: Optional[str] = None


@dataclass
class SuiteReport:
    suite: str
    version: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 0.0


def current_version() -> str:
    """Short git commit hash, or 'local' outside a git repo."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "local"
    except (OSError, subprocess.SubprocessError):
        return "local"


def run_suite(suite: str, cases: list[Case], agent_fn: Callable[[str], object],
              tracer: Tracer, version: str, model: Optional[str] = None) -> SuiteReport:
    """Run every case under its own traced run, check the answer, store the result."""
    store = tracer.store
    report = SuiteReport(suite, version)

    for case in cases:
        run_id, answer, status, crashed = None, "", "success", None
        try:
            with tracer.run(f"{suite}:{case.id}", model) as run:
                run_id = run.id
                result = agent_fn(case.task)
                answer = result if isinstance(result, str) else getattr(result, "answer", str(result))
                status = getattr(result, "status", "success")
                run.status = status if status in ("success", "max_steps") else "success"
        except Exception as exc:                        # one bad case must not stop the suite
            crashed = f"{type(exc).__name__}: {exc}"

        if crashed:
            passed, detail, label = False, f"agent crashed: {crashed}", "crash"
        else:
            passed, detail = case.check(answer)
            label = None
            if not passed:
                label = classify_run(store.get_spans(run_id), status) or "silent_wrong_answer"

        if label:
            store.set_failure_label(run_id, label)
        store.add_test_result(suite, case.id, run_id, passed, detail, version)
        report.results.append(CaseResult(case.id, passed, detail, answer, run_id, label))
    return report


@dataclass
class Comparison:
    regressions: list[str]       # passed before, fails now
    fixes: list[str]             # failed before, passes now
    still_failing: list[str]
    still_passing: list[str]
    new_cases: list[str]


def compare(store, suite: str, base: str, new: str) -> Comparison:
    a, b = store.results_for(suite, base), store.results_for(suite, new)
    out = Comparison([], [], [], [], [])
    for cid, row in b.items():
        if cid not in a:
            out.new_cases.append(cid)
        elif a[cid]["passed"] and not row["passed"]:
            out.regressions.append(cid)
        elif not a[cid]["passed"] and row["passed"]:
            out.fixes.append(cid)
        elif row["passed"]:
            out.still_passing.append(cid)
        else:
            out.still_failing.append(cid)
    return out
