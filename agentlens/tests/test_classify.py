import json

from agentlens.classify import classify_run


def llm(calls, tools=("calculator", "read_file")):
    return {"kind": "llm", "input_json": json.dumps({"tool_names": list(tools)}),
            "output_json": json.dumps({"tool_calls": [{"id": "1", "name": n, "arguments": a}
                                                       for n, a in calls]}),
            "error": None}


def tool(error=None):
    return {"kind": "tool", "input_json": None, "output_json": None, "error": error}


def test_clean_run_has_no_label():
    assert classify_run([llm([("calculator", '{"expression": "1+1"}')]), tool()], "success") is None


def test_looping_by_repetition_and_by_status():
    same = llm([("calculator", '{"expression": "1"}')])
    assert classify_run([same, same, same], "success") == "looping"
    assert classify_run([], "max_steps") == "looping"


def test_wrong_tool():
    assert classify_run([llm([("teleport", "{}")])], "success") == "wrong_tool"


def test_bad_arguments_from_invalid_json_and_from_typeerror():
    assert classify_run([llm([("calculator", "{not json")])], "success") == "bad_arguments"
    assert classify_run([tool("TypeError: unexpected keyword")], "success") == "bad_arguments"


def test_tool_error():
    assert classify_run([tool("FileNotFoundError: missing.txt")], "success") == "tool_error"


def test_garbage_json_in_span_is_tolerated():
    assert classify_run([{"kind": "llm", "input_json": "{{", "output_json": None, "error": None}],
                        "success") is None
