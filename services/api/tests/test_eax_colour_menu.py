"""eax in colour (R2.10) and the tidy command line (R2.29): groups, did you mean, the numbered menu; every form of eax.

Colour: each `docker compose ps` line in its state's colour, errors, warnings and headings coloured; --no-color,
NO_COLOR and CI turn it off, and output that is piped or redirected is always plain, so logs and scripts read as before.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from eaxcli import core, menu  # noqa: E402
from eaxcli import help as eax_help  # noqa: E402
from eaxcli import main as eax_main  # noqa: E402

PS = [
    "NAME          IMAGE   COMMAND   SERVICE   CREATED   STATUS",
    "eax-api-1     api     x         api       1 min     Up 2 minutes (healthy)",
    "eax-web-1     web     x         web       1 min     Up 5 seconds (health: starting)",
    "eax-setup-1   setup   x         setup     1 min     Exited (0) 2 minutes ago",
    "eax-db-1      db      x         db        1 min     Exited (1) 1 minute ago",
    "eax-ops-1     ops     x         ops       1 min     Up 1 minute (unhealthy)",
    "eax-redis-1   redis   x         redis     1 min     Restarting (1) 3 seconds ago",
    "eax-docs-1    docs    x         docs      1 min     Created",
    "eax-once-1    once    x         once      1 min     Exited (0) 1 minute ago",
]
EXPECT = ["", "green", "yellow", "grey", "red", "red", "red", "yellow", "grey"]
BASH = shutil.which("bash")
PWSH = os.environ.get("EAX_PWSH") or shutil.which("pwsh") or shutil.which("powershell")


# ---------------------------------------------------------------- colour (R2.10)
def test_each_container_line_has_its_states_colour():
    assert [core.state_colour(x) if i else "" for i, x in enumerate(PS)] == EXPECT


def test_output_is_plain_when_piped_or_turned_off(monkeypatch):
    monkeypatch.setattr(core, "_USE_COLOUR", False)
    assert core.paint("x", "red") == "x"                 # piped (pytest captures): no codes at all
    monkeypatch.setattr(core, "_USE_COLOUR", True)
    assert core.paint("x", "red") == "\033[31mx\033[0m"
    core.no_colour()
    assert core.paint("x", "red") == "x"
    for var in ("NO_COLOR", "CI", "EAX_NO_COLOR"):
        with monkeypatch.context() as m:
            m.setenv(var, "1")
            assert core._colour_ok() is False, var


def test_say_status_lines_prints_the_lines_unchanged_when_plain(capsys, monkeypatch):
    monkeypatch.setattr(core, "_USE_COLOUR", False)
    core.say_status_lines(PS)
    assert capsys.readouterr().out.splitlines() == PS


def test_no_color_is_taken_out_of_the_arguments(capsys):
    assert eax_main.main(["help", "stop", "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "(also: down)" in out and "\033[" not in out


@pytest.mark.skipif(not BASH, reason="no bash")
def test_eax_sh_colours_the_same_way():
    fn = (REPO / "eax.sh").read_text(encoding="utf-8")
    body = fn[fn.index("colour_status() {"):fn.index("\n}\n", fn.index("colour_status() {")) + 3]
    script = ("C_RED=R; C_GREEN=G; C_YELLOW=Y; C_CYAN=C; C_GREY=D; C_OFF=/\n" + body + "colour_status")
    r = subprocess.run([BASH, "-c", script], input="\n".join(PS) + "\n", capture_output=True, text=True, timeout=30)
    code = {"": "", "green": "G", "yellow": "Y", "red": "R", "grey": "D"}
    got = r.stdout.splitlines()
    for line, want, colour in zip(PS, got, EXPECT, strict=True):
        assert want == (f"{code[colour]}{line}/" if colour else line), line


@pytest.mark.skipif(not BASH, reason="no bash")
def test_eax_sh_is_plain_when_piped():
    r = subprocess.run([BASH, str(REPO / "eax.sh"), "help", "stop"], capture_output=True, text=True, timeout=60)
    assert "\033[" not in r.stdout
    r = subprocess.run([BASH, str(REPO / "eax.sh"), "--no-color", "help", "stop"], capture_output=True, text=True,
                       timeout=60)
    assert r.stdout.rstrip("\n") == eax_help.render("sh", "./eax.sh", False, "stop")[0]


def test_every_form_turns_colour_off_the_same_ways():
    sh = (REPO / "eax.sh").read_text(encoding="utf-8")
    ps = (REPO / "eax.ps1").read_text(encoding="ascii")
    for word in ("--no-color", "NO_COLOR", "EAX_NO_COLOR", "CI"):
        assert word in sh and word in ps, word
    assert "[ -t 1 ]" in sh and "IsOutputRedirected" in ps
    assert "gsub(/\\033\\[[0-9;]*m/" in sh                # the log of eax.sh never holds colour codes
    for state in ("unhealthy", "restarting", "oomkilled", "health: starting", "reports-init"):
        assert state in sh and state in ps, state


# ---------------------------------------------------------------- groups and did you mean (R2.29)
def test_the_help_is_grouped_as_agreed():
    doc = eax_help.parse(eax_help.SOURCE.read_text(encoding="ascii"), eax_help.TAGS)
    names = {s["title"]: [c["names"][0] for c in s["commands"]] for s in doc["sections"]}
    assert names["Start and stop"][:3] == ["up", "stop", "restart"]
    assert "status" in names["Status and logs"] and "backup" in names["Backups and restores"]
    assert "update" in names["Updates"] and "test" in names["Test"] and "deploy" in names["Site and deploy"]
    assert "debug" in names["Developer"] and "menu" in names["Help and documentation"]


@pytest.mark.parametrize("word,near", [("stauts", ["status"]), ("bakup", ["backup", "backups"]), ("x", []),
                                       ("clean", ["clean-debug", "clean-restart", "clean-run"]), ("tset", ["test"])])
def test_did_you_mean(word, near):
    assert eax_help.suggest(word) == near
    msg = eax_help.unknown(word, "./eax.sh")
    assert msg.startswith(f"unknown command '{word}'.") and (("Did you mean: " + ", ".join(near)) in msg) == bool(near)


def test_eaxpy_says_did_you_mean(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(core, "LOG_DIR", tmp_path)
    assert eax_main.main(["stauts"]) == 1
    assert "Did you mean: status?" in capsys.readouterr().out


WORDS = ("stauts", "bakup", "restor", "x", "clean", "Stat", "menu")


@pytest.mark.skipif(not BASH, reason="no bash")
def test_eax_sh_says_the_same(tmp_path):
    src = (REPO / "eax.sh").read_text(encoding="utf-8")
    fn = src[src.index("unknown_command() {"):src.index("\n}\n", src.index("unknown_command() {")) + 3]
    for w in WORDS:
        r = subprocess.run([BASH, "-c", fn + f'unknown_command "{w}"'], cwd=REPO, capture_output=True, text=True,
                           timeout=30)
        assert r.stdout == eax_help.unknown(w, "./eax.sh"), w


@pytest.mark.skipif(not PWSH, reason="no PowerShell here (set EAX_PWSH to a pwsh to run it)")
def test_eax_ps1_says_the_same(tmp_path):
    for w in WORDS[:3]:
        r = subprocess.run([PWSH, "-NoProfile", "-File", str(REPO / "eax.ps1"), w], capture_output=True, text=True,
                           timeout=120)
        assert eax_help.unknown(w, ".\\eax") in r.stdout + r.stderr, w


# ---------------------------------------------------------------- the menu (R2.29)
def test_options_are_split_and_asked_for_one_by_one():
    assert menu.split_args("[name|tag|latest] [--what full|app|db] [--yes]") == ["[name|tag|latest]", "[--what full|app|db]",
                                                                                "[--yes]"]
    assert menu.question("[--yes]")["kind"] == "flag"
    assert menu.question("on|off") == {"kind": "choice", "choices": ["on", "off"], "optional": False}
    assert menu.question("[--older-than N]")["kind"] == "option"
    assert menu.question("<id>")["kind"] == "value" and not menu.question("<id>")["optional"]
    assert menu.question("[list|add <name> [when]]")["kind"] == "text"
    answers = iter(["3", "2", "y"])
    assert menu.ask_options("[name|tag|latest] [--what full|app|db] [--yes]", lambda _: next(answers)) == \
        ["latest", "--what", "app", "--yes"]
    answers = iter(["", "", ""])
    assert menu.ask_options("[name|tag|latest] [--what full|app|db] [--yes]", lambda _: next(answers)) == []
    assert menu.ask_options("<id>", lambda _: "") is None          # a needed value left empty: nothing runs
    answers = iter(["3", "nightly"])
    assert menu.ask_options("on|off", lambda _: next(answers)) == ["nightly"]


def test_the_menu_lists_every_group_and_shows_the_command_before_it_runs(capsys):
    groups = menu.groups("sh", False)
    assert [g["title"] for g in groups][0] == "Start and stop"
    restore = next(i for i, g in enumerate(groups, 1) if g["title"] == "Backups and restores")
    cmd = next(i for i, c in enumerate(groups[restore - 1]["commands"], 1) if c["names"][0] == "restore")
    answers = iter([str(restore), str(cmd), "3", "", "y", "y"])
    line = menu.choose(lambda _: next(answers), "sh", "./eax.sh", False)
    assert line == ["restore", "latest", "--yes"]
    assert "Will run:  ./eax.sh restore latest --yes" in capsys.readouterr().out
    answers = iter([str(restore), str(cmd), "4", "before-upgrade", "", "", "n", "q"])   # said no: back, then quit
    assert menu.choose(lambda _: next(answers), "sh", "./eax.sh", False) is None
    out = capsys.readouterr().out
    assert "Will run:  ./eax.sh restore before-upgrade" in out and "Not run." in out


def test_no_command_prints_the_help_when_not_on_a_terminal(capsys):
    assert eax_main.main([]) == 0                                   # pytest's stdin is not a terminal
    assert "Start and stop" in capsys.readouterr().out


def test_every_form_hands_menu_to_the_python_program():
    assert 'EAX_FORM=sh exec "$BASH" ./eaxpy.sh menu' in (REPO / "eax.sh").read_text(encoding="utf-8")
    ps = (REPO / "eax.ps1").read_text(encoding="ascii")
    assert '$env:EAX_FORM = "ps1"' in ps and '"eaxpy.ps1") menu' in ps


def test_the_menu_runs_the_command_in_the_form_that_opened_it(monkeypatch):
    calls = []
    monkeypatch.setattr(menu.subprocess, "call", lambda argv: calls.append(argv) or 0)
    monkeypatch.setenv("EAX_FORM", "sh")
    menu.run(["status"])
    monkeypatch.setenv("EAX_FORM", "ps1")
    monkeypatch.setenv("EAX_FORM_EXE", "pwsh")
    menu.run(["status"])
    assert calls[0][1:] == [str(REPO / "eax.sh"), "status"]
    assert calls[1][0] == "pwsh" and calls[1][-2:] == [str(REPO / "eax.ps1"), "status"]
