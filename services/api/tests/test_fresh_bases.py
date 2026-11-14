"""A clean rebuild fetches the current base images (R3.12, D673): without it Docker kept building on the base image it
first downloaded, so the image scan's findings (47 Debian packages in the API, library and views images) stayed even
though each image applies its distribution's fixes. The same in every form of eax (D331)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def test_the_clean_commands_ask_for_fresh_bases_in_every_form():
    assert 'os.environ["EAX_BUILD_PULL"] = "1"' in (REPO / "eaxcli/main.py").read_text()
    assert '$env:EAX_BUILD_PULL = "1"' in (REPO / "eax.ps1").read_text()
    assert "export EAX_BUILD_PULL=1" in (REPO / "eax.sh").read_text()


def test_up_then_pulls_and_builds_on_them_in_every_form():
    py = (REPO / "eaxcli/stack.py").read_text()
    assert 'compose(["pull", "--ignore-buildable", "--quiet"], no_throw=True)' in py and 'compose(["build", "--pull"]' in py
    ps1 = (REPO / "eax.ps1").read_text()
    assert '@("pull", "--ignore-buildable", "--quiet")' in ps1 and '@("build", "--pull")' in ps1
    sh = (REPO / "eax.sh").read_text()
    assert "compose pull --ignore-buildable --quiet || true" in sh and "compose build --pull || return 1" in sh


def test_up_in_python_pulls_only_when_asked(monkeypatch):
    from eaxcli import stack
    calls = []
    monkeypatch.setattr(stack, "compose", lambda args, **k: calls.append(args) or 0)
    monkeypatch.setattr(stack, "write_services_file", lambda: None)
    monkeypatch.setattr(stack, "api_servers", lambda: 1)
    monkeypatch.setattr(stack, "tiers", lambda: (_ for _ in ()).throw(StopIteration))
    monkeypatch.delenv("EAX_BUILD_PULL", raising=False)
    try:
        stack.up([], False)
    except StopIteration:
        pass
    assert calls == []
    monkeypatch.setenv("EAX_BUILD_PULL", "1")
    try:
        stack.up([], False)
    except StopIteration:
        pass
    assert calls == [["pull", "--ignore-buildable", "--quiet"], ["build", "--pull"]]


def test_a_failed_build_stops_there(monkeypatch):
    from eaxcli import stack
    monkeypatch.setattr(stack, "compose", lambda args, **k: 3 if args[0] == "build" else 0)
    monkeypatch.setattr(stack, "write_services_file", lambda: None)
    monkeypatch.setattr(stack, "api_servers", lambda: 1)
    monkeypatch.setenv("EAX_BUILD_PULL", "1")
    assert stack.up([], False) == 3


def test_the_help_says_so():
    h = (REPO / "eaxcli/help.txt").read_text()
    assert "Fetches the current base images first" in h and "it fetches the current base images first" in h
