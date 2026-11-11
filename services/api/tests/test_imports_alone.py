"""Every module imports on its own, in a fresh interpreter (owner's laptop, 11 Nov 2026: the self-test imported
mcp_build first and hit an import cycle that the API, which loads mcp_server first, never showed)."""

import subprocess
import sys
from pathlib import Path

import pytest

EAX = Path(__file__).resolve().parents[1] / "eax"
MODULES = sorted("eax." + ".".join(p.relative_to(EAX).with_suffix("").parts)
                 for p in EAX.rglob("*.py") if p.name != "__init__.py" and "__pycache__" not in p.parts
                 and p.name != "__main__.py")
# the MCP modules are the ones that import each other; check those (and the self-test that imports them) in a fresh process
CHECK = [m for m in MODULES if m.startswith("eax.mcp") or m.startswith("eax.testing.")]


@pytest.mark.parametrize("module", CHECK)
def test_module_imports_alone(module):
    r = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True, timeout=120,
                       cwd=EAX.parent)
    assert "circular import" not in r.stderr and "partially initialized" not in r.stderr, r.stderr[-800:]
