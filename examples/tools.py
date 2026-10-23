"""Tools for the sample agent. Kept deliberately small and sandboxed."""
import ast
import json
import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SANDBOX = Path(__file__).parent / "sandbox"

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def calculator(expression: str) -> str:
    return str(_eval(ast.parse(expression, mode="eval").body))


def list_files() -> str:
    return json.dumps(sorted(p.name for p in SANDBOX.iterdir() if p.is_file()))


def read_file(filename: str) -> str:
    path = (SANDBOX / filename).resolve()
    if SANDBOX.resolve() not in path.parents:
        raise PermissionError("access outside sandbox is not allowed")
    return path.read_text()


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., str]

    @property
    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters}}


def default_tools() -> dict[str, Tool]:
    tools = [
        Tool("calculator", "Evaluate an arithmetic expression, e.g. '17 * 23'.",
             {"type": "object", "properties": {"expression": {"type": "string"}},
              "required": ["expression"]}, calculator),
        Tool("list_files", "List the files available to read.",
             {"type": "object", "properties": {}}, list_files),
        Tool("read_file", "Read a text file by name.",
             {"type": "object", "properties": {"filename": {"type": "string"}},
              "required": ["filename"]}, read_file),
    ]
    return {t.name: t for t in tools}
