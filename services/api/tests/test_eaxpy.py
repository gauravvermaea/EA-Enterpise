"""eaxpy (phase 13.9, D331): the eax command in Python must do what eax.ps1 and eax.sh do, command by command."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from eaxcli import core, main  # noqa: E402


def _ps1_commands() -> set[str]:
    text = (REPO / "eax.ps1").read_text(encoding="utf-8")
    switch = text[text.index("    switch ($Command) {"):]
    return set(re.findall(r'^\s{8}"([a-z-]+)"\s*\{', switch, re.M))


def test_every_command_of_eax_ps1_is_in_eaxpy():
    src = (REPO / "eaxcli" / "main.py").read_text(encoding="utf-8")
    handled = set(re.findall(r'command == "([a-z-]+)"', src)) | set(re.findall(r'"([a-z-]+)"', src.split("def dispatch")[1]))
    missing = _ps1_commands() - handled
    assert not missing, f"eaxpy does not handle: {missing}"
    for c in ("cleanup", "clean-run", "clean-debug", "clean-restart", "console", "help"):
        assert f'"{c}"' in src


def test_help_for_one_command(capsys):
    main.show_help("restore")
    out = capsys.readouterr().out
    assert out.startswith("  restore [name|tag|latest]") and "RESTORE to confirm" in out and "  restores" not in out


def test_secrets_are_masked():
    assert core.hide_secrets("EAX_DB_PASSWORD=abc") == "EAX_DB_PASSWORD=****"
    assert core.hide_secrets("redis://:secret@dms-broker") == "redis://:****@dms-broker"
    assert core.hide_secrets('{"PASSWORD":"x"}') == '{"PASSWORD":"****"}'


@pytest.fixture
def copy(tmp_path):
    """A copy of what eaxpy needs, to run commands that need no Docker."""
    for p in ("eaxcli", "eaxpy.py", "deploy/templates", "services/api/version.toml", "docker-compose.yml"):
        src, dst = REPO / p, tmp_path / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if src.is_dir() else shutil.copy)(src, dst)
    def run(*args, stdin=""):
        return subprocess.run([sys.executable, str(tmp_path / "eaxpy.py"), *args], cwd=tmp_path, capture_output=True,
                              text=True, input=stdin, timeout=60)
    return tmp_path, run


def test_init_cleanup_keep_tools_and_certificate(copy):
    root, run = copy
    r = run("init", "laptop")
    assert r.returncode == 0, r.stdout + r.stderr
    env = root / "work" / "eaexplorer.env"
    assert env.exists() and "\r" not in env.read_text(encoding="utf-8") and "DEVELOPMENT LOGINS" in r.stdout
    assert run("init", "laptop").returncode == 1                      # never overwritten
    (root / "work" / "tools").mkdir()
    (root / "work" / "tools" / "uv").write_text("x")
    (root / "work" / "data" / "tls" / "ca.crt").write_text("x")
    r = run("cleanup", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not env.exists() and (root / "work" / "tools" / "uv").exists() and (root / "work" / "data" / "tls" / "ca.crt").exists()
    assert not (root / "work" / "logs").exists()


def test_cleanup_asks_for_yes(copy):
    root, run = copy
    run("init", "laptop")
    r = run("cleanup", stdin="no\n")
    assert "Nothing deleted" in r.stdout and (root / "work" / "eaexplorer.env").exists()


def test_maintenance_and_unknown_and_logs(copy):
    root, run = copy
    run("init", "laptop")
    assert run("maintenance", "on").returncode == 0 and (root / "work" / "proxy" / "maintenance").exists()
    assert run("maintenance", "off").returncode == 0 and not (root / "work" / "proxy" / "maintenance").exists()
    r = run("nonsense")
    assert r.returncode == 1 and "unknown command 'nonsense'" in r.stdout
    logs = list((root / "work" / "logs").glob("eax-*-maintenance.log"))
    assert logs and "maintenance page" in logs[0].read_text(encoding="utf-8")


def test_launchers_pin_uv_and_keep_it_in_work_tools():
    for f in ("eaxpy.ps1", "eaxpy.sh"):
        t = (REPO / f).read_text(encoding="utf-8")
        assert "0.9.5" in t and "work" in t and "tools" in t and "UV_PYTHON_INSTALL_DIR" in t and "--python 3.12" in t
