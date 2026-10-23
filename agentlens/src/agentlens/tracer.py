"""Tracer: records runs and spans. Uses contextvars so nesting works even with async/threads."""
from __future__ import annotations

import contextvars
import dataclasses
import functools
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from .storage import TraceStore

_current_run: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agentlens_run", default=None)
_current_span: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agentlens_span", default=None)


@dataclass
class RunHandle:
    id: str
    status: str = "success"       # caller may set "max_steps"; exceptions set "error"
    error: Optional[str] = None


@dataclass
class SpanHandle:
    id: str
    output: Any = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


class Tracer:
    def __init__(self, store: TraceStore):
        self.store = store

    @contextmanager
    def run(self, name: str, model: Optional[str] = None) -> Iterator[RunHandle]:
        """One agent execution. Creates the run row plus a root 'agent' span."""
        run_id = self.store.start_run(name, model)
        handle = RunHandle(run_id)
        run_token = _current_run.set(run_id)
        span_token = _current_span.set(None)
        started = time.perf_counter()
        try:
            with self.span("agent", name):
                yield handle
        except BaseException as exc:
            handle.status = "error"
            handle.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.store.end_run(run_id, handle.status, elapsed_ms, handle.error)
            _current_span.reset(span_token)
            _current_run.reset(run_token)

    @contextmanager
    def span(self, kind: str, name: str, input: Any = None) -> Iterator[SpanHandle]:
        """One timed step. The parent is whichever span is currently open."""
        run_id = _current_run.get()
        if run_id is None:
            raise RuntimeError("No active run. Wrap your agent call in `with tracer.run(...)`.")
        span_id = self.store.start_span(run_id, _current_span.get(), kind, name, input)
        handle = SpanHandle(span_id)
        token = _current_span.set(span_id)
        started = time.perf_counter()
        error: Optional[str] = None
        try:
            yield handle
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _current_span.reset(token)
            self.store.finish_span(
                span_id, handle.output, (time.perf_counter() - started) * 1000,
                handle.tokens_in, handle.tokens_out, error)

    def trace_tool(self, func: Optional[Callable] = None, *, name: Optional[str] = None):
        """Decorator: `@tracer.trace_tool` or `@tracer.trace_tool(name="x")`."""
        def decorate(f: Callable) -> Callable:
            tool_name = name or f.__name__

            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                with self.span("tool", tool_name, input={"args": list(args), "kwargs": kwargs}) as s:
                    result = f(*args, **kwargs)
                    s.output = result
                    return result
            return wrapper
        return decorate if func is None else decorate(func)


def wrap_tools(tracer: Tracer, tools: dict) -> dict:
    """Return a copy of a {name: Tool} dict whose functions are traced.

    Works with any dataclass that has `.name` and `.func`, so the agent code needs no changes.
    """
    return {n: dataclasses.replace(t, func=tracer.trace_tool(t.func, name=t.name))
            for n, t in tools.items()}
