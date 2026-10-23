"""A minimal tool-calling agent loop. This is the thing agentlens will trace.

Run:  python examples/sample_agent.py "What is 17 * 23?"
"""
import argparse
import json
import os
from dataclasses import dataclass, field

from tools import Tool, default_tools

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. Use a tool when you need "
    "to calculate or read data. When you have the final answer, reply briefly."
)


@dataclass
class AgentResult:
    answer: str
    status: str                      # "success" or "max_steps"
    steps: int
    messages: list = field(default_factory=list)


def execute_tool(tools: dict[str, Tool], name: str, raw_args: str) -> str:
    """Run a tool call. Small models often emit bad calls, so never raise."""
    if name not in tools:
        return f"ERROR: unknown tool '{name}'. Available: {sorted(tools)}"
    try:
        args = json.loads(raw_args or "{}")
        return str(tools[name].func(**args))
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def run_agent(client, model: str, task: str, tools: dict[str, Tool],
              max_steps: int = 8) -> AgentResult:
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task}]
    specs = [t.spec for t in tools.values()]

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=specs, temperature=0)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []

        if not calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            return AgentResult(msg.content or "", "success", step, messages)

        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name,
                                         "arguments": c.function.arguments}}
                           for c in calls]})
        for c in calls:
            result = execute_tool(tools, c.function.name, c.function.arguments)
            print(f"  [step {step}] {c.function.name}({c.function.arguments}) -> {result}")
            messages.append({"role": "tool", "tool_call_id": c.id, "content": result})

    return AgentResult("", "max_steps", max_steps, messages)


def make_client():
    from openai import OpenAI
    return OpenAI(base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
                  api_key=os.getenv("LLM_API_KEY", "ollama"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "qwen2.5:3b"))
    args = parser.parse_args()
    result = run_agent(make_client(), args.model, args.task, default_tools())
    print(f"\nstatus={result.status} steps={result.steps}\nanswer: {result.answer}")
