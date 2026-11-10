"""The help of the eax command (D331): one source (eaxcli/help.txt) for eax.ps1, eax.sh and eaxpy. Every command each
script accepts is in the help, the help lists nothing they don't accept, and the three print the same text."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from eaxcli import help as eax_help  # noqa: E402

ASKS = ([], ["--all"], ["stop"], ["down"], ["run"], ["restart"], ["restore"], ["trust"], ["start-later"], ["no-such"])


def ps1_commands() -> set[str]:
    ps = (REPO / "eax.ps1").read_text(encoding="utf-8")
    found = set(re.findall(r'^\s{8}"([a-z-]+)"\s*\{', ps[ps.index("    switch ($Command) {"):], re.M))
    found |= set(re.findall(r'\$Command -eq "([a-z-]+)"', ps))
    for group in re.findall(r'\$Command -in @\(([^)]*)\)', ps):
        found |= set(re.findall(r'"([a-z][a-z-]*)"', group))
    return found


def sh_commands() -> set[str]:
    sh = (REPO / "eax.sh").read_text(encoding="utf-8")
    found = set(re.findall(r'\[ "\$CMD" = ([a-z-]+) \]', sh))
    for block in re.findall(r'^case "\$CMD" in\n(.*?)^esac', sh, re.S | re.M):
        for pattern in re.findall(r"^  ([^ )]+)\)", block, re.M):
            found |= {p for p in pattern.split("|") if re.fullmatch(r"[a-z][a-z-]*", p)}
    return found


def py_commands() -> set[str]:
    src = (REPO / "eaxcli" / "main.py").read_text(encoding="utf-8")
    found = set(re.findall(r'command == "([a-z][a-z-]*)"', src))
    for group in re.findall(r"command in (?:\(|\{)([^)}]*)[)}]", src):
        found |= set(re.findall(r'"([a-z][a-z-]*)"', group))
    found |= set(re.findall(r'"([a-z][a-z-]*)"', src[src.index("DOCKER_COMMANDS = {"):src.index("}", src.index("DOCKER_COMMANDS = {"))]))
    return found


@pytest.mark.parametrize("form", ["ps1", "sh", "py"])
def test_every_command_a_script_accepts_is_in_the_help(form):
    accepted = {"ps1": ps1_commands, "sh": sh_commands, "py": py_commands}[form]()
    assert {"stop", "restart", "down", "up", "run", "help"} <= accepted, form
    missing = accepted - eax_help.commands()
    assert not missing, f"{form} accepts commands the help does not list: {missing}"


def test_the_help_lists_nothing_the_scripts_do_not_accept():
    listed = eax_help.commands()
    for form, accepted in (("ps1", ps1_commands()), ("sh", sh_commands()), ("py", py_commands())):
        assert not listed - accepted, f"the help lists commands {form} does not accept: {listed - accepted}"


def test_the_source_is_plain_and_complete():
    raw = eax_help.SOURCE.read_bytes()
    raw.decode("ascii")                                   # Windows PowerShell 5.1 reads it too
    doc = eax_help.parse(raw.decode("ascii"), eax_help.TAGS)
    assert doc["sections"][0]["title"] == "Starting and stopping"
    first = [c["names"][0] for c in doc["sections"][0]["commands"]]
    assert first[:3] == ["up", "stop", "restart"]
    for s in doc["sections"]:
        for c in s["commands"]:
            assert c["summary"], c["names"]
            assert len(c["summary"]) <= 102, c["names"]


def test_stop_says_the_data_is_kept_and_the_wiping_commands_say_they_delete():
    stop, _ = eax_help.render("sh", "./eax.sh", False, "stop")
    assert "(also: down)" in stop and "Keeps all data" in stop and "./eax.sh stop" in stop
    for name in ("cleanup", "clean-restart", "clean-run"):
        assert "DELETES" in eax_help.render("sh", "./eax.sh", False, name)[0], name
    overview, _ = eax_help.render("ps1", ".\\eax", True)
    assert overview.index("Starting and stopping") < overview.index("Getting started")
    assert "work\\eaexplorer.env" in overview and "work/" not in overview
    assert eax_help.render("py", "./eaxpy.sh", False, "no-such")[1] == 1


@pytest.mark.parametrize("ask", ASKS)
def test_eax_sh_prints_the_same_help(ask):
    if not shutil.which("bash"):
        pytest.skip("no bash")
    r = subprocess.run(["bash", str(REPO / "eax.sh"), "help", *ask], capture_output=True, text=True, timeout=60)
    text, code = eax_help.render("sh", "./eax.sh", False, ask[0] if ask else "")
    assert (r.stdout.rstrip("\n"), r.returncode) == (text, code)


def test_command_dash_dash_help_in_eax_sh():
    if not shutil.which("bash"):
        pytest.skip("no bash")
    for args in (["stop", "--help"], ["run", "-h"], ["clean-restart", "/?"]):
        r = subprocess.run(["bash", str(REPO / "eax.sh"), *args], capture_output=True, text=True, timeout=60)
        assert r.stdout.rstrip("\n") == eax_help.render("sh", "./eax.sh", False, args[0])[0], args


PWSH = os.environ.get("EAX_PWSH") or shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(not PWSH, reason="no PowerShell here (set EAX_PWSH to a pwsh to run it)")
@pytest.mark.parametrize("ask", ASKS + (["stop", "--help"],))
def test_eax_ps1_prints_the_same_help(ask):
    args = ["help", *ask] if ask[-1:] != ["--help"] else ask
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(REPO / "eax.ps1"), *args], capture_output=True, text=True,
                       timeout=120)
    name = ask[0] if ask else ""
    text, code = eax_help.render("ps1", ".\\eax", True, name)
    assert (r.stdout.rstrip("\n"), r.returncode) == (text, code)


def test_eaxpy_prints_the_same_help(capsys):
    from eaxcli import core, main
    assert main.main(["help", "stop"]) == 0
    assert capsys.readouterr().out.rstrip("\n") == eax_help.render("py", core.EAX, core.WINDOWS, "stop")[0]
    assert main.main(["stop", "--help"]) == 0
    assert "(also: down)" in capsys.readouterr().out
    assert main.main(["help", "no-such"]) == 1


# ---------------------------------------------------------------- eax document (owner, 10 Nov 2026)
MODES = (["--groups"], ["--group", "1"], ["--group", "6"], ["--group", "99"], ["--search", "restart"], ["--search", "zzz"])


def test_document_is_in_the_help_and_every_script_accepts_it():
    assert "document" in eax_help.commands()
    for form, accepted in (("ps1", ps1_commands()), ("sh", sh_commands()), ("py", py_commands())):
        assert "document" in accepted, form
    text, _ = eax_help.render("sh", "./eax.sh", False)
    assert "document [--console|--web]" in text


def test_the_page_has_every_command_and_nothing_from_outside():
    html = eax_help.document_html("ps1", ".\\eax", True)
    src = eax_help.SOURCE.read_text(encoding="utf-8")
    assert "</script" not in src.lower() and "\n".join(src.splitlines()) in html     # help.txt copied in, unchanged
    for cmd in eax_help.commands():                            # every command, from the help copied in
        assert re.search(rf"^(###|@internal) (\S+\|)?{re.escape(cmd)}\b|\|{re.escape(cmd)}\b", html, re.M), cmd
    for marker in ("__FORM__", "__EAX__", "__WINDOWS__", "__HELP__"):
        assert marker not in html.split('<script type="text/plain" id="help-src">')[0] + html.split("</script>")[-1]
    assert not re.search(r'(src|href)="(https?:)?//', html), "nothing loaded from outside"
    assert "prefers-color-scheme: dark" in html and 'id="search"' in html and "Deletes data" in html


@pytest.mark.parametrize("mode", MODES)
def test_document_console_modes_agree(mode):
    if shutil.which("bash"):
        r = subprocess.run(["bash", str(REPO / "eax.sh"), "help", *mode], capture_output=True, text=True, timeout=60)
        assert (r.stdout.rstrip("\n"), r.returncode) == eax_help.render("sh", "./eax.sh", False, *mode)
    if PWSH:
        r = subprocess.run([PWSH, "-NoProfile", "-File", str(REPO / "eax.ps1"), "help", *mode], capture_output=True,
                           text=True, timeout=120)
        assert (r.stdout.rstrip("\n"), r.returncode) == eax_help.render("ps1", ".\\eax", True, *mode)


@pytest.fixture
def scripts(tmp_path):
    for f in ("eax.sh", "eax.ps1"):
        shutil.copy(REPO / f, tmp_path / f)
    shutil.copytree(REPO / "eaxcli", tmp_path / "eaxcli", ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def test_eax_sh_and_ps1_make_the_same_page(scripts):
    env = {**os.environ, "EAX_NO_BROWSER": "1"}
    page = scripts / "work" / "docs" / "eax-commands.html"
    if shutil.which("bash"):
        r = subprocess.run(["bash", str(scripts / "eax.sh"), "document", "--web"], capture_output=True, text=True,
                           timeout=60, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert page.read_text(encoding="utf-8") == eax_help.document_html("sh", "./eax.sh", False)
        page.unlink()
    if PWSH:
        r = subprocess.run([PWSH, "-NoProfile", "-File", str(scripts / "eax.ps1"), "document", "--web"], capture_output=True,
                           text=True, timeout=120, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert page.read_text(encoding="utf-8") == eax_help.document_html("ps1", ".\\eax", True)


def test_eax_sh_document_console_menu(scripts):
    if not shutil.which("bash"):
        pytest.skip("no bash")
    r = subprocess.run(["bash", str(scripts / "eax.sh"), "document", "--console"], input="6\ns\nbackup\nq\n",
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "Deleting everything and starting again" in r.stdout and "clean-restart" in r.stdout
    assert "  backup [tag]" in r.stdout


def test_eaxpy_document(tmp_path, monkeypatch, capsys):
    from eaxcli import main
    monkeypatch.setattr(main, "WORK", tmp_path)
    monkeypatch.setenv("EAX_NO_BROWSER", "1")
    monkeypatch.setenv("LINES", "500")                    # one page: no "more" questions
    assert main.main(["document", "--web"]) == 0
    from eaxcli import core
    assert (tmp_path / "docs" / "eax-commands.html").read_text(encoding="utf-8") == \
        eax_help.document_html("py", core.EAX, core.WINDOWS)
    answers = iter(["1", "s", "trust", "q"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    main.main(["document", "--console"])
    out = capsys.readouterr().out
    assert "Starting and stopping" in out and "stop   (also: down)" in out and "trust [--remove]" in out
