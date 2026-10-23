import pytest

from agentlens import ReplayMiss, TracedClient, Tracer, TraceStore, wrap_tools
from agentlens.replay import deserialize_response, request_hash, serialize_response
from fakes import ForbiddenClient, ScriptedClient, call, reply
from sample_agent import run_agent
from tools import default_tools


def test_hash_is_stable_and_sensitive():
    a = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0}
    assert request_hash(a) == request_hash(dict(reversed(list(a.items()))))
    assert request_hash(a) != request_hash({**a, "temperature": 1})
    assert request_hash(a) != request_hash({**a, "messages": [{"role": "user", "content": "hi!"}]})


def test_serialize_roundtrip():
    resp = reply(calls=[call("1", "calculator", {"expression": "1+1"})])
    back = deserialize_response(serialize_response(resp))
    msg = back.choices[0].message
    assert msg.tool_calls[0].function.name == "calculator"
    assert back.usage.prompt_tokens == 10
    assert deserialize_response(serialize_response(reply(content="hi"))).choices[0].message.tool_calls is None


def _script():
    return [reply(calls=[call("c1", "calculator", {"expression": "17 * 23"})]),
            reply(content="391")]


def test_replay_makes_zero_model_calls_and_matches(tmp_path):
    store = TraceStore(str(tmp_path / "t.db"))
    tracer = Tracer(store)

    live = ScriptedClient(_script())
    with tracer.run("record") as r1:
        first = run_agent(TracedClient(live, tracer, mode="live"), "m", "17*23?",
                          wrap_tools(tracer, default_tools()))
    assert live.calls == 2

    replay_client = TracedClient(ForbiddenClient(), tracer, mode="replay")
    with tracer.run("replay") as r2:
        second = run_agent(replay_client, "m", "17*23?", wrap_tools(tracer, default_tools()))
    assert second.answer == first.answer == "391"
    assert replay_client.cache_hits == 2 and replay_client.live_calls == 0
    llm_outputs = [s["output_json"] for s in store.get_spans(r2.id) if s["kind"] == "llm"]
    assert all('"cached": true' in o for o in llm_outputs)


def test_replay_miss_when_behaviour_changes(tmp_path):
    store = TraceStore(str(tmp_path / "t.db"))
    tracer = Tracer(store)
    client = TracedClient(ForbiddenClient(), tracer, mode="replay")
    with pytest.raises(ReplayMiss):
        with tracer.run("x"):
            run_agent(client, "m", "never recorded", default_tools())


def test_auto_mode_uses_cache_then_falls_back_to_live(tmp_path):
    store = TraceStore(str(tmp_path / "t.db"))
    tracer = Tracer(store)
    inner = ScriptedClient([reply(content="one"), reply(content="two")])
    client = TracedClient(inner, tracer, mode="auto")
    kwargs = dict(model="m", messages=[{"role": "user", "content": "q"}])
    with tracer.run("a"):
        assert client.chat.completions.create(**kwargs).choices[0].message.content == "one"
        assert client.chat.completions.create(**kwargs).choices[0].message.content == "one"
        client.chat.completions.create(model="m", messages=[{"role": "user", "content": "other"}])
    assert inner.calls == 2 and client.cache_hits == 1


def test_invalid_mode_rejected(tmp_path):
    tracer = Tracer(TraceStore(str(tmp_path / "t.db")))
    with pytest.raises(ValueError):
        TracedClient(ForbiddenClient(), tracer, mode="bogus")
