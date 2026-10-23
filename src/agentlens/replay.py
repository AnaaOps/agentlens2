"""Replay helpers: fingerprint a request, and (de)serialize model responses for the cache."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace as NS


class ReplayMiss(RuntimeError):
    """Raised in strict replay mode when a request has no cached response.

    It means the agent behaved differently from the recorded run.
    """


def request_hash(request: dict) -> str:
    """Same request -> same hash. Any change to model, messages, tools or params changes it."""
    canonical = json.dumps(request, sort_keys=True, default=str,
                           ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def serialize_response(resp) -> dict:
    """Turn an OpenAI-style response object into plain JSON-able data."""
    msg = resp.choices[0].message
    calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
             for c in (msg.tool_calls or [])]
    usage = getattr(resp, "usage", None)
    return {
        "content": msg.content,
        "tool_calls": calls,
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", None) or 0,
        },
    }


def deserialize_response(data: dict) -> NS:
    """Rebuild an object shaped like an OpenAI response, so the agent can't tell the difference."""
    calls = [NS(id=c["id"], function=NS(name=c["name"], arguments=c["arguments"]))
             for c in data.get("tool_calls", [])]
    usage = data.get("usage", {})
    return NS(
        choices=[NS(message=NS(content=data.get("content"), tool_calls=calls or None))],
        usage=NS(prompt_tokens=usage.get("prompt_tokens", 0),
                 completion_tokens=usage.get("completion_tokens", 0)))
