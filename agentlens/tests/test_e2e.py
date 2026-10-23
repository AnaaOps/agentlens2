"""The whole stack: sample agent + wrapped tools + traced client -> span tree in SQLite."""
from agentlens import TracedClient, Tracer, TraceStore, wrap_tools
from fakes import ScriptedClient, call, reply
from sample_agent import run_agent
from tools import default_tools


def test_agent_run_produces_expected_span_tree(tmp_path):
    store = TraceStore(str(tmp_path / "t.db"))
    tracer = Tracer(store)
    inner = ScriptedClient([reply(calls=[call("c1", "calculator", {"expression": "17 * 23"})]),
                            reply(content="391")])
    client = TracedClient(inner, tracer)
    with tracer.run("e2e", "m") as run:
        result = run_agent(client, "m", "17*23?", wrap_tools(tracer, default_tools()))
        run.status = result.status

    spans = store.get_spans(run.id)
    assert [(s["kind"], s["name"]) for s in spans] == [
        ("agent", "e2e"), ("llm", "m"), ("tool", "calculator"), ("llm", "m")]
    assert all(s["parent_id"] == spans[0]["id"] for s in spans[1:])
    assert spans[2]["output_json"] == '"391"'
    row = store.get_run(run.id)
    assert row["total_tokens"] == 30 and row["status"] == "success"
