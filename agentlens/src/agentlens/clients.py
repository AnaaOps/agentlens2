"""TracedClient: wraps any OpenAI-compatible client to add tracing, caching and replay."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from .replay import (ReplayMiss, deserialize_response, request_hash,
                     serialize_response)
from .tracer import Tracer

MODES = ("live", "auto", "replay")
# live   : always call the model (still saves responses to the cache)
# auto   : use the cache when possible, otherwise call the model
# replay : cache only; a miss raises ReplayMiss (strict, zero model calls)


class TracedClient:
    def __init__(self, inner: Any, tracer: Tracer, mode: str = "auto"):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self._inner = inner
        self._tracer = tracer
        self.mode = mode
        self.live_calls = 0
        self.cache_hits = 0
        # Same shape as the OpenAI client, so run_agent() works unchanged.
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        model = kwargs.get("model", "unknown")
        key = request_hash(kwargs)
        store = self._tracer.store
        tool_names = [t.get("function", {}).get("name") for t in kwargs.get("tools") or []]
        span_input = {"model": model, "messages": kwargs.get("messages"),
                      "tool_names": tool_names, "request_hash": key}

        with self._tracer.span("llm", model, input=span_input) as span:
            cached = None if self.mode == "live" else store.cache_get(key)
            if cached is not None:
                data, from_cache = json.loads(cached), True
                self.cache_hits += 1
            elif self.mode == "replay":
                raise ReplayMiss(f"No cached response for request {key[:12]} (mode=replay)")
            else:
                data = serialize_response(self._inner.chat.completions.create(**kwargs))
                store.cache_put(key, model, json.dumps(data))
                from_cache = False
                self.live_calls += 1

            span.output = {**data, "cached": from_cache}
            span.tokens_in = data["usage"]["prompt_tokens"]
            span.tokens_out = data["usage"]["completion_tokens"]
            return deserialize_response(data)
