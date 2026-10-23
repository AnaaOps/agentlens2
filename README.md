# agentlens

Tracing, replay, and regression testing for LLM agents. Works with any
OpenAI-compatible API (Ollama, Groq, Gemini, OpenAI, ...).

**The problem:** agents fail silently. A run can finish with `status=success` and still
give a wrong answer, and when you change a prompt or model you can't tell whether things
got better or worse. agentlens records every step, replays runs for free, and runs
automated regression tests.

## Quickstart

    python3 -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev,dashboard]"
    ollama pull qwen2.5:3b

    agentlens test examples/suite.py --label v1      # run 12 test cases, trace everything
    agentlens runs list                              # see recorded runs
    agentlens runs show <run_id>                     # span tree of one run
    agentlens dashboard                              # web UI

## Use it in your own agent

```python
from agentlens import TraceStore, Tracer, TracedClient, wrap_tools

tracer = Tracer(TraceStore("agentlens.db"))
client = TracedClient(my_openai_client, tracer, mode="auto")   # live | auto | replay
tools = wrap_tools(tracer, my_tools)

with tracer.run("my-task", model="qwen2.5:3b") as run:
    result = my_agent(client, tools, "What is 17 * 23?")
```

## How it works

    your agent -> TracedClient -> LLM provider
                      |   \-> wrap_tools (traces tool calls)
                      v
                 SQLite trace store  (runs, spans, cache, test results)
                      ^
        CLI | dashboard | test runner   (read-only consumers)

- **Tracing:** every LLM call and tool call is a *span* (timing, tokens, input, output,
  error). Spans form a tree under a run.
- **Replay:** each request is hashed; a repeat request is served from the cache. In
  `replay` mode a cache miss raises `ReplayMiss` and the model is never called.
- **Regression testing:** a `Case` is a task plus a checker. `agentlens test` runs the
  suite, stores pass/fail per version, and `--baseline v1` fails if anything regressed.
- **Failure classifier:** rule-based labels: `looping`, `wrong_tool`, `bad_arguments`,
  `tool_error`, `crash`, `silent_wrong_answer`.

## Tests

    pytest --cov=agentlens

## Limitations

- The failure classifier is heuristic; `silent_wrong_answer` means "checker failed and no
  structural problem was visible".
- Cache keys are exact-match hashes, so any prompt change is a cache miss (intended).
- SQLite, single process. Concurrent writers are not supported yet.
