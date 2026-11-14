"""eax screen, the full screen in the style of Turbo Pascal (R3.1): the menus from help.txt, the dialogs and the command
lines they make, what runs in a window, the dashboard, the fall-back to the numbered menu, the wiring in every form, and
the screen itself driven headless with Textual's own harness (when Textual is here: CI installs it)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from eaxcli import screen  # noqa: E402
from eaxcli import screen_model as sm  # noqa: E402


# ---------------------------------------------------------------- the menus and dialogs, from help.txt
def test_the_menu_bar_has_the_groups_with_unique_alt_letters():
    ms = sm.menus("ps1", True)
    assert [m["short"] for m in ms] == ["Start", "Status", "Backups", "Updates", "Test", "Settings", "Site", "Developer", "Help"]
    keys = [m["key"] for m in ms]
    assert all(keys) and len(set(keys)) == len(keys) and "x" not in keys          # Alt+X is Exit
    names = {c["name"] for m in ms for c in m["commands"]}
    assert {"up", "status", "backup", "restore", "update", "test", "services", "deploy", "help"} <= names
    assert "screen" not in names and "menu" not in names                          # not offered inside the screen
    assert all(c["summary"] for m in ms for c in m["commands"])


def test_a_dialog_has_lists_tick_boxes_and_fields():
    f = sm.fields("[name|tag|latest] [--what full|app|app+data|db|files] [--yes]")
    assert [(x["kind"], x["optional"]) for x in f] == [("choice", True), ("choice", True), ("flag", True)]
    assert f[1]["flag"] == "--what" and f[1]["choices"] == ["full", "app", "app+data", "db", "files"]
    g = sm.fields("<id>")
    assert g[0]["kind"] == "value" and not g[0]["optional"]
    h = sm.fields("[--older-than N] [service...]")
    assert h[0]["kind"] == "value" and h[0]["flag"] == "--older-than" and h[1]["many"]
    assert sm.fields("") == []


def test_the_command_line_as_it_is_filled():
    f = sm.fields("[name|tag|latest] [--what full|app|app+data|db|files] [--yes]")
    assert sm.line_for("restore", f, {}) == (["restore"], "")
    line, missing = sm.line_for("restore", f, {"f0": "latest", "f1": "db", "f2": True})
    assert line == ["restore", "latest", "--what", "db", "--yes"] and not missing
    assert sm.line_for("restore", f, {"f0": "latest", "f0_typed": "20261113T2000"})[0] == ["restore", "20261113T2000"]
    g = sm.fields("<id>")
    assert sm.line_for("restore-log", g, {}) == (["restore-log"], "Needed: id")
    h = sm.fields("[service...]")
    assert sm.line_for("up", h, {"f0": "api web"})[0] == ["up", "api", "web"]
    assert sm.shown(["backup", "my tag"], ".\\eax") == '.\\eax backup "my tag"'


def test_what_runs_in_a_window_and_what_takes_the_terminal():
    assert sm.in_window(["status"]) and sm.in_window(["backups"]) and sm.in_window(["services"])
    for line in (["logs"], ["restore", "latest"], ["up"], ["console"], ["test", "full"], ["document", "--web"], []):
        assert not sm.in_window(line), line


def test_the_dashboard_rows():
    lines = ['{"Service":"web","State":"exited","Status":"Exited (1)"}',
             '{"Service":"api","State":"running","Health":"healthy","Status":"Up"}',
             '{"Service":"db","State":"running","Health":"starting","Status":"Up (starting)"}', "not json", ""]
    rows = sm.containers(lines)
    assert [(r["service"], r["colour"]) for r in rows] == [("web", "red"), ("db", "yellow"), ("api", "green")]
    arr = sm.containers([json.dumps([{"Name": "x", "State": "paused"}])])
    assert arr[0]["service"] == "x" and arr[0]["colour"] == "yellow"


def test_disks(tmp_path):
    d = sm.disks([tmp_path, tmp_path / "missing", tmp_path])
    assert len(d) == 1 and d[0]["total"] > 0 and d[0]["colour"] in ("green", "yellow", "red") and 0 <= d[0]["used"] <= 100
    assert sm.gb(2_500_000_000) == "2.5 GB"


# ---------------------------------------------------------------- running, and the fall-back
def test_commands_run_in_the_form_that_opened_the_screen(monkeypatch):
    assert screen.argv_for(["status"], "sh")[:2] == ["bash", str(REPO / "eax.sh")]
    monkeypatch.setenv("EAX_FORM_EXE", "pwsh")
    ps = screen.argv_for(["backup", "x"], "ps1")
    assert ps[0] == "pwsh" and ps[-3:] == [str(REPO / "eax.ps1"), "backup", "x"]
    assert screen.argv_for(["status"], "py")[1:] == [str(REPO / "eaxpy.py"), "status"]


def test_when_the_full_screen_cannot_open(monkeypatch):
    monkeypatch.delenv("EAX_SCREEN", raising=False)
    assert screen.why_not(stdin_tty=True, term="xterm-256color") == ""
    assert "not a terminal" in screen.why_not(stdin_tty=False, term="xterm")
    assert "TERM=dumb" in screen.why_not(stdin_tty=True, term="dumb")
    monkeypatch.setenv("EAX_SCREEN", "off")
    assert screen.why_not(stdin_tty=True, term="xterm") == "EAX_SCREEN=off"


def test_the_numbered_menu_opens_instead(monkeypatch, capsys):
    from eaxcli import menu
    monkeypatch.setattr(screen, "why_not", lambda: "not a terminal (piped or in a script)")
    monkeypatch.setattr(menu, "main", lambda argv: 7)
    assert screen.main([]) == 7 and "the numbered menu instead" in capsys.readouterr().out
    monkeypatch.setattr(screen, "why_not", lambda: "")
    monkeypatch.setattr(screen, "load_textual", lambda: False)
    assert screen.main([]) == 7 and "could not be fetched" in capsys.readouterr().out


def test_textual_is_fetched_once_into_work_tools(monkeypatch, tmp_path):
    import builtins
    real = builtins.__import__

    def no_textual(name, *a, **k):
        if name == "textual":
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_textual)
    asked = []
    assert screen.load_textual(fetch=lambda cmd: asked.append(cmd) or 1) is False
    cmd = asked[0]
    assert cmd[1:3] == ["pip", "install"] and str(screen.PYLIB) in cmd and f"textual=={screen.TEXTUAL}" in cmd


def test_wired_in_every_form_and_in_the_help():
    ps1 = (REPO / "eax.ps1").read_text()
    assert 'else { "screen" }' in ps1 and '& (Join-Path $PSScriptRoot "eaxpy.ps1") screen' in ps1
    sh = (REPO / "eax.sh").read_text()
    assert "set -- screen" in sh and 'screen) EAX_FORM=sh exec "$BASH" ./eaxpy.sh screen' in sh
    main = (REPO / "eaxcli/main.py").read_text()
    assert 'if command == "screen" or (not command and sys.stdin.isatty())' in main and 'if command == "menu":' in main
    h = (REPO / "eaxcli/help.txt").read_text()
    assert "### screen\n" in h and "### menu\n" in h and "$ {eax} screen" in h
    assert "textual==" + screen.TEXTUAL in (REPO / "services/api/requirements-dev.txt").read_text()


# ---------------------------------------------------------------- the screen itself, headless
def test_the_screen_driven_headless(monkeypatch):
    pytest.importorskip("textual")
    from eaxcli import core
    monkeypatch.setattr(core, "compose_out", lambda args: ['{"Service":"api","State":"running","Health":"healthy","Status":"Up"}',
                                                           '{"Service":"web","State":"exited","Status":"Exited (1)"}'])
    monkeypatch.setattr(screen, "argv_for", lambda line, form=None: [sys.executable, "-c", f"print('ran', {line!r})"])
    seen = {}

    async def drive():
        app = screen.build_app("py", False, "./eaxpy.sh")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            seen["rows"] = app.query_one("#containers").row_count
            await pilot.press("f10")
            await pilot.pause(0.2)
            seen["first"] = type(app.screen).__name__
            await pilot.press("right")                    # Start -> Status
            await pilot.pause(0.2)
            seen["status_first"] = app.screen.query_one("#pulldown").get_option_at_index(0).id
            await pilot.press("enter")
            await pilot.pause(0.3)
            seen["dialog"] = str(app.screen.query_one("#dialog-line").renderable)
            await pilot.click("#run")
            await pilot.pause(1.0)
            log = app.screen.query_one("#output-log")
            seen["output"] = " ".join(str(getattr(x, "text", x)) for x in log.lines)
            await pilot.press("escape")
            await pilot.pause(0.2)
            await pilot.press("alt+b")                    # Backups
            await pilot.pause(0.2)
            ol = app.screen.query_one("#pulldown")
            ids = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            ol.highlighted = ids.index("restore")
            await pilot.press("enter")
            await pilot.pause(0.3)
            d = app.screen
            d.query_one("#f0_typed").value = "latest"
            d.query_one("#f2").value = True
            await pilot.pause(0.2)
            seen["restore"] = str(d.query_one("#dialog-line").renderable)
            seen["labels"] = [str(x.renderable) for x in d.query("Label")]
            await pilot.press("escape")
            await pilot.pause(0.1)
            await pilot.press("alt+x")
    asyncio.run(drive())
    assert seen["rows"] == 2 and seen["first"] == "PullDown" and seen["status_first"] == "status"
    assert seen["dialog"] == "Will run:  ./eaxpy.sh status"
    assert "ran ['status']" in seen["output"]
    assert seen["restore"] == "Will run:  ./eaxpy.sh restore latest --yes"
    assert any("[name|tag|latest]" in x for x in seen["labels"])          # brackets shown, not read as markup


def test_the_alt_letter_is_shown_on_the_bar():
    assert sm.bar_label("Start", "s") == ("Start", 0)
    assert sm.bar_label("Status", "t") == ("Status", 1)
    assert sm.bar_label("Site", "a") == ("Site (a)", 6)
    assert sm.bar_label("Help", "") == ("Help", -1)
