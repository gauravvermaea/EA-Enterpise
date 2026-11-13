"""The eax commands as a catalogue, for running them from a web page (D554): the Command centre in EA Explorer
(System admin > Command centre, through the operations helper) and the Commands and Console tabs of eax deploy's local
page. One module both import, so the catalogue, the option checks and the strong confirm are never two copies.

* The catalogue is read from eaxcli/help.txt (the one source of the help, D331): every command, grouped as in the help,
  with its summary, its full help and its examples, and a form built from its syntax line ("[--channel prod|rc|latest]").
* Only known commands run, with options checked against that syntax: no shell, no free text. A value may hold letters,
  digits and . _ - : / @ + , = % only, so ; | & $ ` < > ( ) quotes, spaces and new lines never get through.
* Each command has a kind: run (runs, the page stays up), offline (stops or restarts EA Explorer), wipe (deletes
  everything: cleanup and the clean-* commands, behind the strong confirm and a backup first), interactive (the
  console's menu: in the Console tab only) and host (needs the machine itself: init, check, trust, deploy, secrets,
  document; shown with the command to type there, unless the page runs on that machine, as eax deploy's does).
* Rights: IT Admins and Super Admins; the wipe commands Super Admins only.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from . import help as help_

PREFIXES = ("eax", "./eax", ".\\eax", "eax.sh", "./eax.sh", "eax.cmd", ".\\eax.cmd", "eax.ps1", ".\\eax.ps1", "eaxpy",
            "./eaxpy.sh", ".\\eaxpy", "eaxpy.sh", "python3 eaxpy.py", "python eaxpy.py")
TOKEN = re.compile(r"^[A-Za-z0-9_.:/@+,=%-]{1,300}$")
NOT_ALLOWED = set(";|&$`<>()\\\"'\n\r\t*?![]{}~#")

OFFLINE = {"stop", "restart", "up", "update", "rollback", "restore", "restore-app", "maintenance", "standby"}
WIPE = {"cleanup", "clean-run", "clean-restart", "clean-debug"}
HOST = {"init", "check", "trust", "deploy", "secrets", "document", "schedule", "persist"}
INTERACTIVE = {"console", "restore-model"}     # ask as they go: in the Console only
FOLLOWS = {"logs", "debug"}                       # keep going until stopped: the page offers Stop
STOPPABLE = FOLLOWS | {"status", "diag", "test", "backups", "restores", "databases", "footprint", "url", "logins", "services", "help", "import",
                       "restore-log", "servers"}
YES = {"cleanup", "restore", "restore-app", "update", "rollback", "test"}   # take --yes: the page confirmed already
HOST_WHY = {
    "init": "It writes the config file on the machine itself, before EA Explorer runs.",
    "check": "It checks that Docker runs on the machine itself.",
    "trust": "It adds the certificate to the trusted certificates of the computer you browse from.",
    "deploy": "The deployment wizard runs on the machine you deploy from (it has its own Commands and Console tabs).",
    "secrets": "It reads and writes cloud key vaults with the cloud credentials of the machine itself.",
    "document": "It opens a page in the browser of the machine itself; the Documentation page has the same.",
    "schedule": "On this page use the Schedules tab instead: the same schedules, with a form and the checks of who may make which.",
    "persist": "On the web use System Admin > Persist: the same list, with Delete beside each item (R2.26).",
}


class Refused(ValueError):
    """A command or an option that may not run from the page (the reason is the message)."""


def _first(names: list[str]) -> str:
    return names[0]


def _alias_map(cat: dict) -> dict[str, str]:
    out = {}
    for g in cat["groups"]:
        for c in g["commands"]:
            for n in c["names"]:
                out[n] = c["name"]
    return out


def kind_of(name: str) -> str:
    if name in WIPE:
        return "wipe"
    if name in INTERACTIVE:
        return "interactive"
    if name in HOST:
        return "host"
    if name in OFFLINE:
        return "offline"
    return "run"


def kind_of_argv(argv: list[str]) -> str:
    """As kind_of, but `test --reset-survival` deletes everything too (it runs a real clean-restart, D561)."""
    if argv and argv[0] == "test" and "--reset-survival" in argv:
        return "wipe"
    return kind_of(argv[0]) if argv else "run"


def allowed_argv(argv: list[str], roles: list[str] | tuple[str, ...]) -> None:
    """allowed() for a whole command line: the reset-survival test needs a Super Admin, like the wipe commands."""
    allowed("clean-restart" if kind_of_argv(argv) == "wipe" else argv[0], roles)


def _params(args: str) -> list[dict]:
    """The form for a syntax line: each [...] or bare part becomes a field.

    [--x]                a tick box               [--a|--b]          one of these flags (or none)
    [--x <v>] / --x a|b  a flag with a value      [a|b] / a|b        a word chosen from a list
    <name> / [tag]       a word (required / not)  [service...]       several words
    """
    out: list[dict] = []
    parts = re.findall(r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]|<[^>]+>|\S+", args)
    for raw in parts:
        opt = raw.startswith("[") and raw.endswith("]")
        body = raw[1:-1].strip() if opt else raw
        body = body.removesuffix("...")
        many = raw.endswith(("...]", "..."))
        if re.match(r"^--[\w-]+(\|--[\w-]+)+$", body):              # [--a|--b]
            out.append({"key": "/".join(body.split("|")), "type": "flags", "choices": body.split("|"), "required": not opt})
        elif re.match(r"^--[\w-]+$", body):                         # [--x]
            out.append({"key": body, "type": "flag", "required": False})
        elif m := re.match(r"^(--[\w-]+)(?:\|(--[\w-]+))?\s+(.+)$", body):   # [--x <v>] [--x a|b] [--to|--from p:n]
            flags = [f for f in (m.group(1), m.group(2)) if f]
            val = m.group(3).strip()
            inner = re.match(r"^(.*?)(\s*\[--yes\])?$", val)
            val = inner.group(1).strip()
            p = {"key": flags[0], "type": "flag-value", "flags": flags, "required": False,
                 "placeholder": val.strip("<>")}
            if "|" in val and not val.startswith("<"):
                p["choices"] = val.split("|")
            out.append(p)
            if inner.group(2):
                out.append({"key": "--yes", "type": "flag", "required": False})
        elif "|" in body and not body.startswith("<"):               # [a|b] or a|b (a flag among them: its own field)
            words = body.split("|")
            flags = [w for w in words if w.startswith("--")]
            if flags:
                out.append({"key": "/".join(flags), "type": "flags", "choices": flags, "required": False})
            words = [w for w in words if not w.startswith("--")]
            choices = [c.strip("<>") for c in words]
            free = any(c.startswith("<") or c.strip("<>") in PLACEHOLDERS for c in words)
            out.append({"key": f"arg{len(out)}", "type": "word" if free else "choice", "choices": choices,
                        "required": not opt and not flags, "placeholder": "|".join(choices)})
        else:                                                        # <name> [tag] [service...]
            out.append({"key": f"arg{len(out)}", "type": "words" if many else "word", "required": not opt and body != "",
                        "placeholder": body.strip("<>")})
    return out


PLACEHOLDERS = {"name", "tag", "run", "command", "source", "id", "words", "service", "n", "version"}
# syntax lines too rich for the reader above: their fields written out
OVERRIDES = {
    "test": [{"key": "what", "type": "choice", "choices": ["smoke", "full", "backup", "ui-review", "failed", "delete", "clean"], "required": False,
              "placeholder": "smoke|full|backup|ui-review|failed|delete|clean"},
             {"key": "run", "type": "word", "required": False, "placeholder": "run (with failed: which run; the last if none)"},
             {"key": "--warnings", "type": "flag", "required": False},     # with failed: its warnings too (R2.36)
             {"key": "--older-than", "type": "flag-value", "flags": ["--older-than"], "required": False,
              "placeholder": "days"},                                     # with delete: runs older than DAYS (R2.43)
             {"key": "--smoke/--detailed", "type": "flags", "choices": ["--smoke", "--detailed"], "required": False},
             {"key": "--suite", "type": "flag-value", "flags": ["--suite"], "required": False,
              "placeholder": "api|ui|db|security|backup|all", "choices": ["api", "ui", "db", "security", "backup", "all"]},
             {"key": "--role", "type": "flag-value", "flags": ["--role"], "required": False, "placeholder": "role"},
             {"key": "--area", "type": "flag-value", "flags": ["--area"], "required": False, "placeholder": "area"},
             {"key": "--status/--last/--report/--fixtures/--build", "type": "flags",
              "choices": ["--status", "--last", "--report", "--fixtures", "--build"], "required": False},
             {"key": "--clean", "type": "flag-value", "flags": ["--clean"], "required": False, "placeholder": "run|all"},
             {"key": "--yes", "type": "flag", "required": False},
             {"key": "--reset-survival", "type": "flag", "required": False},
             {"key": "--confirm", "type": "flag-value", "flags": ["--confirm"], "required": False, "placeholder": "installation name"}],
}


def catalogue(text: str | None = None) -> dict:
    """Every command from help.txt, grouped as in the help, with its form and its kind."""
    doc = help_.parse(text if text is not None else help_.SOURCE.read_text(encoding="utf-8"), {"unix", "sh"})
    groups = []
    for s in doc["sections"]:
        cmds = []
        for c in s["commands"]:
            name = _first(c["names"])
            k = kind_of(name)
            cmds.append({
                "name": name, "names": c["names"], "args": c["args"], "summary": c["summary"],
                "detail": [x.replace("{eax}", "eax") for x in c["detail"]],
                "examples": [x.replace("{eax}", "eax") for x in c["examples"]],
                "params": OVERRIDES.get(name) or _params(c["args"]), "kind": k, "stoppable": name in STOPPABLE,
                "role": "super-admin" if k == "wipe" else "it-admin",
                "host_why": HOST_WHY.get(name, ""),
            })
        groups.append({"title": s["title"], "notes": s["notes"], "commands": cmds})
    return {"groups": groups}


def find(name: str, cat: dict | None = None) -> dict:
    cat = cat or catalogue()
    real = _alias_map(cat).get(name)
    if not real:
        raise Refused(f"'{name}' is not an eax command. Type help for the list.")
    for g in cat["groups"]:
        for c in g["commands"]:
            if c["name"] == real:
                return c
    raise Refused(f"'{name}' is not an eax command.")


def _token(v: str) -> str:
    v = str(v).strip()
    if not v:
        raise Refused("An empty value.")
    if any(ch in NOT_ALLOWED for ch in v) or not TOKEN.match(v):
        raise Refused(f"'{v[:40]}' is not allowed: only letters, digits and . _ - : / @ + , = % (no spaces, quotes "
                      "or shell characters).")
    return v


def check_argv(argv: list[str], cat: dict | None = None) -> list[str]:
    """argv (the command and its options) checked against the command's syntax; the cleaned argv, or Refused."""
    if not argv:
        raise Refused("No command.")
    cat = cat or catalogue()
    cmd = find(argv[0], cat)
    rest = [_token(a) for a in argv[1:]]
    flags_known: dict[str, dict] = {}
    for p in cmd["params"]:
        if p["type"] == "flag":
            flags_known[p["key"]] = p
        elif p["type"] == "flags":
            for f in p["choices"]:
                flags_known[f] = p
        elif p["type"] == "flag-value":
            for f in p["flags"]:
                flags_known[f] = p
    if cmd["name"] in YES:
        flags_known.setdefault("--yes", {"type": "flag"})
    positional = [p for p in cmd["params"] if p["type"] in ("choice", "word", "words")]
    pos_i, i = 0, 0
    while i < len(rest):
        a = rest[i]
        if a.startswith("--"):
            p = flags_known.get(a)
            if a in ("--help", "-h"):
                i += 1
                continue
            if not p:
                raise Refused(f"{cmd['name']} has no option {a}. Its syntax: {cmd['name']} {cmd['args']}".rstrip())
            if p["type"] == "flag-value":
                if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
                    raise Refused(f"{a} needs a value ({p.get('placeholder', 'a value')}).")
                v = rest[i + 1]
                if p.get("choices") and v not in p["choices"]:
                    raise Refused(f"{a} takes one of: {', '.join(p['choices'])}.")
                i += 2
                continue
            i += 1
            continue
        if pos_i >= len(positional):
            raise Refused(f"{cmd['name']} takes no more words ('{a}'). Its syntax: {cmd['name']} {cmd['args']}".rstrip())
        p = positional[pos_i]
        if p["type"] == "choice" and a not in p["choices"]:
            raise Refused(f"{cmd['name']}: '{a}' is not one of {', '.join(p['choices'])}.")
        if p["type"] != "words":
            pos_i += 1
        i += 1
    for p in positional[pos_i:]:
        if p["required"]:
            raise Refused(f"{cmd['name']} needs {p.get('placeholder', 'a value')}. Its syntax: {cmd['name']} {cmd['args']}")
    return [cmd["name"], *rest]


def build_argv(name: str, values: dict, cat: dict | None = None) -> list[str]:
    """The guided form's answers (key -> value) as argv, checked. Ticks are true/false; several words a list or text."""
    cat = cat or catalogue()
    cmd = find(name, cat)
    argv = [cmd["name"]]
    for p in cmd["params"]:
        v = values.get(p["key"])
        if v in (None, "", False, []):
            continue
        if p["type"] == "flag":
            argv.append(p["key"])
        elif p["type"] == "flags":
            argv.append(str(v))
        elif p["type"] == "flag-value":
            flag = values.get(p["key"] + ":flag") or p["flags"][0]
            argv += [str(flag), str(v)]
        elif p["type"] == "words":
            argv += [w for w in (v if isinstance(v, list) else str(v).split()) if w]
        else:
            argv.append(str(v))
    return check_argv(argv, cat)


def parse_line(line: str, cat: dict | None = None) -> list[str]:
    """A line typed in the Console ("eax backup nightly", "backup nightly", "./eax.sh status"), checked. Anything that
    is not an eax command, or holds a shell character, is Refused."""
    line = (line or "").strip()
    if not line:
        return []
    if any(ch in line for ch in ";|&$`<>\n\r") or "$(" in line:
        raise Refused("Only eax commands run here: no shell characters (; | & $ ` < >).")
    for p in sorted(PREFIXES, key=len, reverse=True):
        if line == p:
            return ["help"]
        if line.startswith(p + " "):
            line = line[len(p) + 1:].strip()
            break
    try:
        words = shlex.split(line, posix=True)
    except ValueError as exc:
        raise Refused(f"That line could not be read: {exc}.") from exc
    return check_argv(words, cat)


def allowed(name: str, roles: list[str] | tuple[str, ...]) -> None:
    """Refused unless the person may run this command: IT and Super Admins; the wipe commands Super Admins only."""
    roles = set(roles or ())
    if kind_of(name) == "wipe":
        if "super-admin" not in roles:
            raise Refused("Only Super Admins may run the commands that delete everything.")
    elif not roles & {"super-admin", "it-admin"}:
        raise Refused("Only IT Admins and Super Admins may run eax commands.")


def wipe_plan(argv: list[str]) -> dict:
    """What a wipe command deletes, in plain words, and whether the backups go too (the backup first is then kept
    outside the work folder, in persist/safety-backups/, D558)."""
    name, opts = argv[0], set(argv[1:])
    deletes = ["the config file (work/eaexplorer.env)", "every log", "the laptop data folders",
               "every backup and restore log in work/backups"]
    everything = name != "cleanup" or "--all" in opts
    if everything:
        deletes.insert(0, "every database (the models, projects, people, settings, reports, documents' records)")
        deletes.insert(1, "the document files and every Docker volume")
    if "--certificate" in opts:
        deletes.append("the local certificate (you trust it again with eax trust)")
    then = {"cleanup": "Nothing starts again: run eax init and eax up on the machine afterwards.",
            "clean-run": "Then it makes a new config file and starts EA Explorer empty.",
            "clean-restart": "It stops EA Explorer, then makes a new config file and starts it empty.",
            "clean-debug": "Then it starts EA Explorer empty and keeps recording the containers' output."}[name]
    return {"command": " ".join(["eax", *argv]), "deletes": deletes, "backups_deleted": True, "then": then,
            "backup_first": "A fresh infrastructure backup is taken first and copied to persist/safety-backups/ "
                            "beside the work folder, which no cleanup deletes; download it before you go on if you want "
                            "a copy elsewhere.", "goes_offline": True}


def check_confirm(argv: list[str], typed: str, expected: str, understood: bool) -> None:
    """The strong confirm of the wipe commands: the installation's name typed exactly, and the 'I understand' tick."""
    if kind_of_argv(argv) != "wipe":
        return
    if not understood:
        raise Refused("Tick 'I understand that this deletes everything' to go on.")
    if not expected or (typed or "").strip() != expected:
        raise Refused(f"Type the installation's name exactly ({expected}) to confirm.")


def with_yes(argv: list[str]) -> list[str]:
    """Commands that ask before acting get --yes once the page has asked (and cleanup always: it was confirmed)."""
    if argv[0] in YES and "--yes" not in argv:
        return [*argv, "--yes"]
    return argv


def installation_name(root: Path | str = ".") -> str:
    """The name the strong confirm asks for: EAX_INSTALLATION_NAME from the config file, else the host name in
    EAX_HOSTNAME, else the folder's name."""
    root = Path(root)
    vals: dict[str, str] = {}
    try:
        for line in (root / "work" / "eaexplorer.env").read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=(.*)$", line)
            if m:
                vals[m.group(1)] = m.group(2).strip().strip("'\"")
    except OSError:
        pass
    return vals.get("EAX_INSTALLATION_NAME") or vals.get("EAX_HOSTNAME") or root.resolve().name


def safety_backup(root: Path, run_id: str, write, keep: int = 0, group: str = "") -> int:
    """Before a wipe command: an infrastructure backup now (eaxpy backup safety-<run>), then a copy of it in
    persist/safety-backups/ beside the work folder, which no cleanup deletes (D558). write(text) reports; 0 when both
    worked. keep > 0 with a group (a schedule's id): only the newest `keep` of that group are kept, so a nightly demo
    reset does not fill the disk (D559)."""
    import shutil
    import subprocess
    import sys

    write(f"Taking an infrastructure backup first (tag safety-{run_id}) ...")
    proc = subprocess.run([sys.executable, str(Path(root) / "eaxpy.py"), "backup", f"safety-{run_id}"], cwd=root,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)
    for line in (proc.stdout + proc.stderr).splitlines():
        write(line)
    if proc.returncode:
        return proc.returncode
    infra = Path(root) / "work" / "backups" / "infrastructure"
    found = sorted((d for d in infra.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime) if infra.is_dir() else []
    if not found:
        write("The backup was not found in work/backups/infrastructure.")
        return 1
    from . import persist
    base = persist.folder(root) / "safety-backups"
    dest = base / found[-1].name
    shutil.copytree(found[-1], dest, dirs_exist_ok=True)
    write(f"The backup is kept in persist/safety-backups/{found[-1].name} (beside the work folder; no cleanup deletes it).")
    if keep and group:
        mine = sorted((d for d in base.iterdir() if d.is_dir() and group in d.name), key=lambda d: d.stat().st_mtime)
        for old in mine[:-keep]:
            shutil.rmtree(old, ignore_errors=True)
            write(f"Removed the older safety backup {old.name} (this schedule keeps the newest {keep}).")
    return 0
