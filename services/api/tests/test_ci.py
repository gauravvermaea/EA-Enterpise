"""R3.15 (13 Nov 2026): every GitHub CI run since 5 Nov 2026 failed in "API - lint and tests" with "No module named 'eax'":
CI runs plain `pytest` in services/api, which (unlike `python -m pytest`) does not put the current folder on the path.
pytest now adds it itself (pyproject.toml, pythonpath), and no test imports another through a "tests." package, which
another installed package of that name can hide."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

API = Path(__file__).resolve().parents[1]
REPO = API.parents[1]


def test_pytest_finds_the_eax_package_however_it_is_started():
    cfg = tomllib.loads((API / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert cfg["pythonpath"] == ["."] and cfg["testpaths"] == ["tests"]
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "working-directory: services/api" in ci and "- run: pytest -q" in ci   # what this protects


def test_no_test_imports_another_through_a_tests_package():
    bad = [p.name for p in (API / "tests").glob("test_*.py")
           if re.search(r"^\s*(from|import) tests\.", p.read_text(encoding="utf-8"), re.M)]
    assert not bad, bad
