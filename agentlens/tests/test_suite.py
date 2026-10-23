import pytest

from agentlens import TracedClient, Tracer, TraceStore, wrap_tools
from agentlens.testing import (Case, compare, contains, not_contains, number_equals,
                               run_suite)
from fakes import ScriptedClient, call, reply
from sample_agent import run_agent
from tools import default_tools


def test_checkers():
    assert number_equals(12600)("The total is $12,600.")[0]
    assert not number_equals(12600)("The total revenue is $7200.")[0]
    assert number_equals(391)("17 * 23 equals 391.")[0]
    assert contains("March 14")("launch is on march 14")[0]
    assert not contains("a", "b")("only a")[0]
    assert not_contains("secret")("nothing here")[0]
    assert not not_contains("secret")("The Secret")[0]


def test_silent_failure_is_caught_and_labelled(tmp_path):
    """The real bug from the 3B model: 40 instead of 400. Status says success, answer is wrong."""
    store = TraceStore(str(tmp_path / "t.db"))
    tracer = Tracer(store)
    inner = ScriptedClient([
        reply(calls=[call("1", "read_file", {"filename": "sales.csv"})]),
        reply(calls=[call("2", "calculator", {"expression": "(120*5)+(40*150)+(15*40)"})]),
        reply(content="The total revenue is $7200."),
    ])
    client = TracedClient(inner, tracer)
    tools = wrap_tools(tracer, default_tools())
    case = Case("revenue", "total revenue?", number_equals(12600))

    report = run_suite("s", [case], lambda t: run_agent(client, "m", t, tools), tracer, "v1", "m")
    r = report.results[0]
    assert not r.passed and r.label == "silent_wrong_answer"
    assert store.get_run(r.run_id)["status"] == "success"
    assert store.get_run(r.run_id)["failure_label"] == "silent_wrong_answer"
    assert report.pass_rate == 0.0


def test_crash_does_not_stop_suite(tmp_path):
    tracer = Tracer(TraceStore(str(tmp_path / "t.db")))

    def agent(task):
        if task == "bad":
            raise RuntimeError("kaboom")
        return "fine"

    cases = [Case("a", "bad", contains("x")), Case("b", "ok", contains("fine"))]
    report = run_suite("s", cases, agent, tracer, "v1")
    assert [r.passed for r in report.results] == [False, True]
    assert report.results[0].label == "crash"
    assert report.pass_rate == 0.5


def test_compare_finds_regressions_and_fixes(tmp_path):
    store = TraceStore(str(tmp_path / "t.db"))
    tracer = Tracer(store)
    cases = [Case("keep", "q", contains("ok")), Case("regress", "q", contains("ok")),
             Case("fix", "q", contains("ok"))]
    answers = {"v1": {"keep": "ok", "regress": "ok", "fix": "no"},
               "v2": {"keep": "ok", "regress": "no", "fix": "ok"}}
    for version, table in answers.items():
        order = iter(table[c.id] for c in cases)
        run_suite("s", cases, lambda t, o=order: next(o), tracer, version)
    cmp = compare(store, "s", "v1", "v2")
    assert cmp.regressions == ["regress"] and cmp.fixes == ["fix"]
    assert cmp.still_passing == ["keep"]
