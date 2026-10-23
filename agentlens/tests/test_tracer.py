import pytest

from agentlens import Tracer, TraceStore


@pytest.fixture
def store(tmp_path):
    return TraceStore(str(tmp_path / "t.db"))


def test_run_creates_root_span_and_nesting(store):
    tracer = Tracer(store)
    with tracer.run("demo", "m") as run:
        with tracer.span("llm", "m") as llm:
            llm.tokens_in, llm.tokens_out = 10, 5
            llm.output = {"x": 1}
            with tracer.span("tool", "calc"):
                pass
    spans = store.get_spans(run.id)
    assert [s["kind"] for s in spans] == ["agent", "llm", "tool"]
    assert spans[0]["parent_id"] is None
    assert spans[1]["parent_id"] == spans[0]["id"]
    assert spans[2]["parent_id"] == spans[1]["id"]
    row = store.get_run(run.id)
    assert row["status"] == "success" and row["total_tokens"] == 15
    assert row["total_latency_ms"] > 0


def test_exception_marks_run_and_span_as_error(store):
    tracer = Tracer(store)
    with pytest.raises(ValueError):
        with tracer.run("boom") as run:
            with tracer.span("tool", "bad"):
                raise ValueError("nope")
    row = store.get_run(run.id)
    assert row["status"] == "error" and "ValueError" in row["error"]
    assert any("ValueError: nope" == s["error"] for s in store.get_spans(run.id))


def test_span_outside_run_raises(store):
    with pytest.raises(RuntimeError, match="No active run"):
        with Tracer(store).span("llm", "m"):
            pass


def test_trace_tool_decorator_records_input_output_error(store):
    tracer = Tracer(store)

    @tracer.trace_tool
    def add(a, b):
        return a + b

    @tracer.trace_tool(name="fail")
    def broken():
        raise KeyError("x")

    with tracer.run("t") as run:
        assert add(2, b=3) == 5
        with pytest.raises(KeyError):
            broken()
    tool_spans = [s for s in store.get_spans(run.id) if s["kind"] == "tool"]
    assert tool_spans[0]["name"] == "add" and tool_spans[0]["output_json"] == "5"
    assert tool_spans[1]["name"] == "fail" and tool_spans[1]["error"].startswith("KeyError")


def test_run_status_can_be_set_by_caller(store):
    tracer = Tracer(store)
    with tracer.run("t") as run:
        run.status = "max_steps"
    assert store.get_run(run.id)["status"] == "max_steps"


def test_prefix_lookup_and_listing(store):
    tracer = Tracer(store)
    with tracer.run("a") as r1:
        pass
    with tracer.run("b"):
        pass
    assert store.get_run(r1.id[:6])["name"] == "a"
    assert store.get_run("zzzz") is None
    assert [r["name"] for r in store.list_runs()] == ["b", "a"]
    assert len(store.list_runs(status="error")) == 0
