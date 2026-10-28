# agentlens

Trace, replay and test LLM agents. Works with any OpenAI-compatible API (Ollama, Groq,
Gemini, OpenAI and others).

LLM agents fail quietly. A run can finish with `status=success` and still give a wrong
answer, and when you change a prompt or a model you cannot tell whether things got better or
worse. agentlens records every step an agent takes, lets you replay a run without calling the
model, and runs automated regression tests.

![Dashboard](docs/images/dashboard.png)

## What you get

- **Tracing.** Every model call and tool call is recorded as a span (time, tokens, input,
  output, error). Spans form a tree under each run.
- **Replay.** Each request is hashed. A repeated request is answered from the cache, so a
  whole test suite can be re-scored with zero model calls.
- **Regression tests.** A test case is a task plus an automatic checker. Run a suite,
  compare it against an earlier version, and see which cases got fixed or broke.
- **Failure labels.** A rule-based classifier tags failed runs (`looping`, `tool_error`,
  `wrong_tool`, `bad_arguments`, `crash`, `silent_wrong_answer`).
- **A prompt-injection guard.** Code that blocks tool output containing instructions aimed at
  the model. It is a phrase filter, so see the limitations below.
- **A CLI and a dashboard** to look at all of it.

![A failed run, step by step](docs/images/run-timeline.png)

## Quickstart

You need Python 3.10 or newer. For the example agent you also need
[Ollama](https://ollama.com) with a small model.

```bash
git clone <your-repo-url> && cd agentlens
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,dashboard]"
ollama pull qwen2.5:3b

pytest                                              # run the unit tests
agentlens test examples/suite.py --label v1         # run 22 test cases and trace them all
agentlens runs list                                 # recent runs
agentlens runs show <run_id>                        # one run as a tree of steps
agentlens dashboard                                 # web page at http://localhost:8501
```

A live run on a CPU-only laptop is slow. Add `--mode replay` to re-score cached runs in
seconds without calling the model.

![A finished test run](docs/images/test-run.png)

## Use it with your own agent

```python
from agentlens import TraceStore, Tracer, TracedClient, wrap_tools
from agentlens.guards import guard_tools           # optional: block injected instructions

tracer = Tracer(TraceStore("agentlens.db"))
client = TracedClient(my_openai_client, tracer, mode="auto")   # live | auto | replay
tools = wrap_tools(tracer, guard_tools(my_tools))

with tracer.run("my-task", model="qwen2.5:3b") as run:
    result = my_agent(client, tools, "What is 17 * 23?")
```

`TracedClient` has the same shape as the OpenAI client, so your agent code does not change.
`my_tools` is a dict of objects with `.name` and `.func`, like the ones in
`examples/tools.py`.

To test your own agent, copy `examples/suite.py`: set `SUITE`, write your `CASES`, and make
`build()` return a function that takes a task and returns the agent's result.

![agentlens runs show](docs/images/runs-show.png)

## What I found with it

I used agentlens on a small agent (qwen2.5:3b, running locally on an 8 GB laptop) and a
22-case test suite. The full write-up, with run ids for every claim, is in
[docs/findings.md](docs/findings.md).

| Setup | Pass rate |
|---|---|
| Original prompt (baseline) | 14/22 (64%) |
| Stronger prompt | 17/22 (77%) |
| Nudge: re-run once with a hint when the model asks instead of acting | 15/22 (68%) |
| Guard: block injected instructions in tool output | 15/22 (68%) |
| Nudge and guard together | 17/22 (77%) |

- In 7 of the 8 real failures, the model ended by asking the user for information it could
  have looked up with its own tools.
- The stronger prompt did not help on 6 new cases it had not been written for (4/6 with
  both prompts).
- Making the agent more autonomous (the nudge) exposed a prompt injection: two nudged runs
  were hijacked by a file unrelated to the question. A guard in code fixed that, and the
  nudge and guard together did better than either alone.

These are small numbers from one model, so read them as observations, not proof.

## How it works

```
your agent -> TracedClient -> LLM provider
                  |    \-> wrap_tools (traces tool calls) -> guard_tools (screens output)
                  v
             SQLite trace store (runs, spans, cache, test results)
                  ^
     CLI | dashboard | test runner   (they only read from the store)
```

```
src/agentlens/   tracer.py, clients.py, replay.py, storage.py, schema.py,
                 testing.py, classify.py, guards.py, cli.py, dashboard.py
examples/        sample_agent.py, tools.py, suite.py, suite_heldout.py
tests/           unit tests that use fake models, so no Ollama is needed
docs/            findings.md
```

`examples/suite.py` has three switches for the experiments above:
`PROMPT=v2`, `NUDGE=1` and `GUARD=1`.

## Limitations

- The guard is a phrase filter. In my tests it caught 5 of 10 attack wordings and wrongly
  blocked 3 of 12 harmless texts. Treat it as one layer of defence, not the whole answer.
- The failure classifier uses simple rules, and I have not yet measured how often it is
  right.
- Checkers match phrases and numbers, so some correct answers can be marked wrong.
- The dashboard's token and latency totals include cached replays, so they do not show the
  compute actually spent.
- One SQLite file and one process at a time.

## Built with AI help

I built this with help from an AI assistant. I ran every experiment, read the traces, and
checked the results myself.