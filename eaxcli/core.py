"""The basics every command uses: the folders, this run's log, the config file, docker compose, diagnostics."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
ENV_FILE = WORK / "eaexplorer.env"
ENV_REL = "work/eaexplorer.env"
LOG_DIR = WORK / "logs"
STAMP = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")   # local time, as the old scripts
WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"
EAX = ".\\eaxpy" if WINDOWS else "./eaxpy.sh"      # how this command is typed here (for messages)
OFF = ("off", "false", "0", "no", "disabled")


class Failure(Exception):
    """A command stops with a plain message (shown in red, written to the log)."""


# ---------------------------------------------------------------- colours and this run's log
_COLOURS = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "grey": "90"}
_log = {"file": None, "path": None}


def _colour_ok() -> bool:
    if not sys.stdout.isatty():
        return False
    if WINDOWS:
        os.system("")     # switches on colour codes in a Windows console
    return True


_USE_COLOUR = _colour_ok()


def paint(text: str, colour: str = "") -> str:
    return f"\033[{_COLOURS[colour]}m{text}\033[0m" if colour and _USE_COLOUR else text


def say(text: str = "", colour: str = "") -> None:
    """To the console (in colour) and to this run's log."""
    print(paint(text, colour), flush=True)
    log_only(text)


def log_only(text: str) -> None:
    if _log["file"]:
        _log["file"].write(text + "\n")
        _log["file"].flush()


def start_log(name: str, rest: list[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 14 * 86400          # keep two weeks of logs
    for f in LOG_DIR.glob("*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass
    path = LOG_DIR / f"eax-{STAMP}-{name}.log"
    _log["path"] = path
    _log["file"] = open(path, "a", encoding="utf-8", newline="\n")  # noqa: SIM115 - open for the whole run
    log_only(f"=== eax {name} {' '.join(rest)}   {datetime.now().astimezone().isoformat()}")
    log_only(f"=== folder {ROOT}   Python {platform.python_version()}   {platform.platform()}   (eaxpy, D331)")
    print(paint(f"Log: {path}", "grey"), flush=True)


def stop_log() -> None:
    if _log["file"]:
        log_only(f"=== end {datetime.now().astimezone().isoformat()}")
        _log["file"].close()
        _log["file"] = None


def log_path() -> str:
    return str(_log["path"] or "")


# ---------------------------------------------------------------- secrets kept out of logs
_MASKS = [(re.compile(r"((?:PASSWORD|SECRET|_KEY|URLENC)[A-Z_]*\s*[:=]\s*).*$"), r"\1****"),
          (re.compile(r"(redis://:)[^@]+@"), r"\1****@"),
          (re.compile(r'("PASSWORD"\s*:\s*")[^"]*"'), r'\1****"')]


def hide_secrets(line: str) -> str:
    for rx, rep in _MASKS:
        line = rx.sub(rep, line)
    return line


# ---------------------------------------------------------------- running programs
def run_logged(args: list[str], quiet: bool = False, mask: bool = False) -> int:
    """Runs a program; every output line goes to the console (unless quiet) and to the log; returns its exit code."""
    log_only("")
    log_only("> " + " ".join(args))
    try:
        p = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
    except FileNotFoundError:
        log_only(f"< {args[0]} not found")
        if not quiet:
            say(f"{args[0]} is not installed or not on the PATH.", "red")
        return 127
    assert p.stdout is not None
    for raw in p.stdout:
        line = raw.rstrip("\n")
        if mask:
            line = hide_secrets(line)
        if not quiet:
            print(line, flush=True)
        log_only(line)
    code = p.wait()
    log_only(f"< exit {code}")
    return code


def capture(args: list[str]) -> tuple[int, str]:
    """A program's output (standard output only), not shown; (exit code, text)."""
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except FileNotFoundError:
        return 127, ""
    return r.returncode, r.stdout


def attached(args: list[str]) -> int:
    """A program with this console attached (it can ask questions and show progress); output not logged."""
    log_only("> " + " ".join(args) + "  (interactive: output in this window, not in this log)")
    try:
        return subprocess.run(args, cwd=ROOT, check=False).returncode
    except FileNotFoundError:
        say(f"{args[0]} is not installed or not on the PATH.", "red")
        return 127


# ---------------------------------------------------------------- the config file
def setting(name: str, default: str = "") -> str:
    if not ENV_FILE.exists():
        return default
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            v = line.split("=", 1)[1].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            return v or default
    return default


def kind() -> str:
    return setting("EAX_DEPLOYMENT", "laptop")


def copy_config(why: str) -> str:
    """A dated copy of the config file before it changes (work/config-history); its name."""
    hist = WORK / "config-history"
    hist.mkdir(parents=True, exist_ok=True)
    who = re.sub(r"[^A-Za-z0-9_.-]", "-", os.environ.get("USERNAME") or os.environ.get("USER") or "eax")
    name = f"eaexplorer.env.{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.{who}.{why}"
    (hist / name).write_bytes(ENV_FILE.read_bytes())
    return name


def write_setting(name: str, value: str, drop: str = "", section: str = "") -> None:
    """Sets one value in the config file (UTF-8, LF line ends, as Compose reads it cleanly)."""
    lines = [ln for ln in ENV_FILE.read_text(encoding="utf-8").splitlines() if not (drop and re.match(rf"^\s*{drop}\s*=", ln))]
    rx = re.compile(rf"^\s*{re.escape(name)}\s*=")
    if any(rx.match(ln) for ln in lines):
        lines = [f"{name}={value}" if rx.match(ln) else ln for ln in lines]
    else:
        lines += ["", *([section] if section else []), f"{name}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- docker compose
def compose_args(args: list[str]) -> list[str]:
    if not ENV_FILE.exists():
        raise Failure(f"No {ENV_REL} yet: run {EAX} init first.")
    # plain progress and no colour codes, so the log reads cleanly
    # scale-out extra files (phase 36.3, D521): EAX_COMPOSE_EXTRA=standby,shared-storage... (deploy/compose/scale)
    extra: list[str] = []
    for x in [v for v in setting("EAX_COMPOSE_EXTRA", "").replace(",", " ").split() if v]:
        f = f"deploy/compose/scale/docker-compose.{x}.yml"
        if not (ROOT / f).exists():
            raise Failure(f"EAX_COMPOSE_EXTRA names {x}, but there is no {f}.")
        extra += ["-f", f]
    return ["docker", "compose", "--ansi", "never", "--progress", "plain", "--env-file", ENV_REL,
            "-f", "docker-compose.yml", "-f", f"deploy/compose/docker-compose.{kind()}.yml", *extra, *args]


def compose(args: list[str], no_throw: bool = False, quiet: bool = False) -> int:
    code = run_logged(compose_args(args), quiet=quiet)
    if code != 0 and not no_throw:
        say(f"docker compose failed (exit {code}). Collecting diagnostics...", "red")
        diagnostics()
        raise Failure(f"docker compose failed (exit {code}). Full log with diagnostics: {log_path()}")
    return code


def compose_out(args: list[str]) -> list[str]:
    """Lines a compose command prints (not shown, not logged); empty when it fails."""
    code, out = capture(compose_args(args))
    return [ln for ln in out.splitlines() if ln.strip()] if code == 0 else []


def docker_ok() -> bool:
    return capture(["docker", "info", "--format", "{{.ServerVersion}}"])[0] == 0


def assert_docker() -> None:
    if not docker_ok():
        raise Failure("Docker is not running (or still starting). Start Docker Desktop (or the Docker service), wait until it "
                      "shows 'Engine running', check with: docker version (it must show a Server section), then run this again.")


def version() -> str:
    m = re.search(r'^version = "(.*)"', (ROOT / "services/api/version.toml").read_text(encoding="utf-8"), re.MULTILINE)
    return m.group(1) if m else ""


def diagnostics() -> None:
    """Versions, containers, images, every container's recent log and the (masked) config, into the log."""
    say("")
    say(f"==================== DIAGNOSTICS {datetime.now().astimezone().isoformat()} ====================")
    run_logged(["docker", "version"], quiet=True)
    run_logged(["docker", "compose", "version"], quiet=True)
    run_logged(["docker", "info", "--format", "CPUs {{.NCPU}}  Memory {{.MemTotal}}  Storage {{.Driver}}  OS {{.OperatingSystem}}"], quiet=True)
    run_logged(["docker", "system", "df"], quiet=True)
    if ENV_FILE.exists():
        log_only("")
        log_only(f"> settings in {ENV_REL} (images, site, deployment)")
        for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if re.match(r"^EAX_(IMAGE_|DEPLOYMENT|HOSTNAME|HTTPS?_PORT|VERSION)|^COMPOSE_", ln):
                log_only(ln)
        run_logged(compose_args(["ps", "-a"]), quiet=True)
        run_logged(compose_args(["images"]), quiet=True)
        for s in compose_out(["config", "--services"]):
            run_logged(compose_args(["logs", "--no-color", "--timestamps", "--tail", "300", s]), quiet=True, mask=True)
        run_logged(compose_args(["config"]), quiet=True, mask=True)
    else:
        say(f"No {ENV_REL}: run {EAX} init first.")
    say("==================== END DIAGNOSTICS ====================")
    say(f"Diagnostics saved in {log_path()}", "yellow")
