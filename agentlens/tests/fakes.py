"""Fake model clients for tests: no network, no Ollama, fully deterministic."""
import json
from types import SimpleNamespace as NS


def reply(content=None, calls=None, prompt=10, completion=5):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls))],
              usage=NS(prompt_tokens=prompt, completion_tokens=completion))


def call(id_, name, args):
    return NS(id=id_, function=NS(name=name,
                                  arguments=args if isinstance(args, str) else json.dumps(args)))


class ScriptedClient:
    """Returns pre-written replies in order and counts how often it was called."""
    def __init__(self, responses):
        self._it = iter(responses)
        self.calls = 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        return next(self._it)


class ForbiddenClient:
    """Fails the test if the model is called. Proves replay makes zero model calls."""
    def __init__(self):
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        raise AssertionError("model was called, but replay must not call it")
