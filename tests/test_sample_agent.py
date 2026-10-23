import json
from types import SimpleNamespace as NS

from sample_agent import execute_tool, run_agent
from tools import default_tools


def _resp(content=None, calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls))])


def _call(id_, name, args):
    return NS(id=id_, function=NS(name=name, arguments=json.dumps(args)))


class FakeClient:
    """Replays scripted responses so the agent loop is testable without a model."""
    def __init__(self, responses):
        self._it = iter(responses)
        self.chat = NS(completions=NS(create=lambda **kw: next(self._it)))


def test_tool_then_answer():
    client = FakeClient([
        _resp(calls=[_call("1", "calculator", {"expression": "17 * 23"})]),
        _resp(content="391"),
    ])
    result = run_agent(client, "fake", "17*23?", default_tools())
    assert result.status == "success" and result.steps == 2
    assert result.answer == "391"


def test_max_steps_stops_loops():
    looping = [_resp(calls=[_call(str(i), "list_files", {})]) for i in range(5)]
    result = run_agent(FakeClient(looping), "fake", "loop", default_tools(), max_steps=3)
    assert result.status == "max_steps"


def test_bad_tool_calls_do_not_crash():
    tools = default_tools()
    assert execute_tool(tools, "nope", "{}").startswith("ERROR: unknown tool")
    assert execute_tool(tools, "calculator", "not json").startswith("ERROR")
    assert execute_tool(tools, "read_file", '{"filename": "../tools.py"}').startswith("ERROR")
    assert execute_tool(tools, "calculator", '{"expression": "__import__(1)"}').startswith("ERROR")
