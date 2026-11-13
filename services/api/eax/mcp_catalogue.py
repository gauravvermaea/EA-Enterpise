"""The list of every MCP tool and what it does, for the MCP page (R2.54; owner, 13 Nov 2026: "list all MCP tools and
what they do on the MCP page and nothing else"). Read from the tools' own code (each @mcp.tool() function, its
parameters and its description), so the page always matches what the server offers and nothing is kept by hand. The
MCP server itself is not started for it."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
AREAS = {  # the file a tool is in: what the tools there are about
    "mcp_server": "Reading the repository", "mcp_build": "Building models and projects", "mcp_ops": "Model operations",
    "mcp_analysis": "Analysis and clean-up", "mcp_more": "Reports, projects and the rest", "mcp_scenarios": "Scenario planning",
    "mcp_iterations": "A project's ADM iteration", "mcp_tests": "The platform's test results",
}


def _is_tool(fn: ast.AST) -> bool:
    return isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and any(
        (isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool") or getattr(d, "attr", "") == "tool"
        for d in fn.decorator_list)


def _changes(fn: ast.AST) -> bool:
    """Whether the tool changes something: it runs with begin=True or write=True, or asks for a confirm token (D458)."""
    for n in ast.walk(fn):
        if isinstance(n, ast.keyword) and n.arg in ("begin", "write") and getattr(n.value, "value", False) is True:
            return True
        if isinstance(n, ast.arg) and n.arg in ("confirm", "confirm_token"):
            return True
    return False


def _params(fn) -> list[dict]:
    a = fn.args
    names = a.args + a.kwonlyargs
    defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults) + list(a.kw_defaults)
    out = []
    for arg, d in zip(names, defaults, strict=False):
        if arg.arg in ("self", "ctx"):
            continue
        out.append({"name": arg.arg, "type": ast.unparse(arg.annotation) if arg.annotation else "",
                    "required": d is None, "default": None if d is None else ast.unparse(d)})
    return out


@lru_cache(maxsize=1)
def tools() -> list[dict]:
    """Every MCP tool: area, name, what it does (its description), its parameters, and whether it changes anything."""
    out = []
    for f in sorted(HERE.glob("mcp_*.py")):
        if f.stem not in AREAS:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for fn in tree.body:
            if _is_tool(fn):
                doc = " ".join((ast.get_docstring(fn) or "").split())
                out.append({"area": AREAS[f.stem], "name": fn.name, "what": doc, "params": _params(fn),
                            "changes": _changes(fn)})
    return out
