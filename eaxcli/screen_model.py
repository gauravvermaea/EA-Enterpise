"""What `eax screen` shows and does, without the screen itself (R3.1): the menus from help.txt (D331), each command's
dialog fields and the command line they make, which commands run in a window and which take the terminal, and the
dashboard's rows. eaxcli/screen.py draws it with Textual; the tests run this part on its own."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import menu as menu_

# the menu bar's short names for help.txt's groups (owner, 13 Nov 2026: "Start, Status, Backups, Updates, Test, Settings,
# Site, Developer, Help"); a group the help adds later shows under its own first word
SHORT = {"Start and stop": "Start", "Status and logs": "Status", "Backups and restores": "Backups", "Updates": "Updates",
         "Test": "Test", "Settings and services": "Settings", "Site and deploy": "Site", "Developer": "Developer",
         "Help and documentation": "Help"}

# commands that only print and never ask: their output is shown in a window inside the screen; everything else switches
# to the plain terminal (Turbo Pascal's user screen) and comes back with Enter, so questions, following logs and
# consoles work as they do at the prompt
IN_WINDOW = {"status", "url", "logins", "databases", "backups", "restores", "restore-log", "services", "help", "check",
             "footprint", "diag", "document"}
NEVER = {"screen", "menu"}          # the screen and the numbered menu are not offered inside the screen


def menus(form: str = "py", windows: bool = False) -> list[dict]:
    """[{title, short, key, notes, commands: [{name, names, summary, args, detail}]}]: the help's groups and commands,
    each group with its Alt+letter (unique: the first free letter of its short name, else of its title, else any; never
    x, which is Exit)."""
    out, used = [], set()
    for g in menu_.groups(form, windows):
        short = SHORT.get(g["title"], g["title"].split()[0])
        key = next((ch.lower() for ch in short + g["title"] + "abcdefghijklmnopqrstuvwyz"
                    if ch.isalpha() and ch.lower() not in used and ch.lower() != "x"), "")
        used.add(key)
        cmds = [{"name": c["names"][0], "names": c["names"], "summary": c["summary"], "args": c["args"],
                 "detail": c.get("detail", [])} for c in g["commands"] if c["names"][0] not in NEVER]
        out.append({"title": g["title"], "short": short, "key": key, "notes": g["notes"], "commands": cmds})
    return out


def bar_label(short: str, key: str) -> tuple[str, int]:
    """The menu bar's text for a group and where its Alt letter is in it (-1: added after it, as "Site (a)")."""
    i = short.lower().find(key) if key else -1
    return (short, i) if i >= 0 or not key else (f"{short} ({key})", len(short) + 2)


def fields(spec: str) -> list[dict]:
    """The dialog's fields for a command's options: a choice is a list, a flag a tick box, a value a field. Each field:
    {id, kind (choice|flag|value|text), label, choices, flag, optional, many}."""
    out = []
    for i, part in enumerate(menu_.split_args(spec or "")):
        q = menu_.question(part)
        kind = q["kind"]
        if kind == "option" and not q.get("choices"):
            out.append({"id": f"f{i}", "kind": "value", "label": f"{q['flag']} {q['label']}", "flag": q["flag"], "choices": [],
                        "optional": True, "many": False})
        elif kind in ("choice", "option"):
            out.append({"id": f"f{i}", "kind": "choice", "label": q.get("flag") or part, "flag": q.get("flag", ""),
                        "choices": list(q["choices"]), "optional": q["optional"], "many": False})
        elif kind == "flag":
            out.append({"id": f"f{i}", "kind": "flag", "label": q["flag"], "flag": q["flag"], "choices": [], "optional": True,
                        "many": False})
        elif kind == "value":
            out.append({"id": f"f{i}", "kind": "value", "label": q["label"], "flag": "", "choices": [], "optional": q["optional"],
                        "many": q.get("many", False)})
        else:
            out.append({"id": f"f{i}", "kind": "text", "label": f"options {q['label']}", "flag": "", "choices": [],
                        "optional": True, "many": True})
    return out


def line_for(name: str, flds: list[dict], values: dict) -> tuple[list[str], str]:
    """The command line the dialog makes (as arguments) and what is still missing ("" when it can run). A choice can also
    be typed (a backup's name rather than latest: <id>_typed), as the numbered menu's "something else"."""
    out, missing = [name], []
    for f in flds:
        v = values.get(f["id"])
        if f["kind"] == "flag":
            if v:
                out.append(f["flag"])
            continue
        text = str(values.get(f"{f['id']}_typed") or "").strip() if f["kind"] == "choice" else ""
        text = text or str(v or "").strip()
        if not text:
            if not f["optional"]:
                missing.append(f["label"])
            continue
        if f["flag"]:
            out.append(f["flag"])
        out += text.split() if f["many"] or f["kind"] == "text" else [text]
    return out, (f"Needed: {', '.join(missing)}" if missing else "")


def shown(line: list[str], how: str = ".\\eax") -> str:
    """The command as it would be typed."""
    return " ".join([how, *(f'"{a}"' if " " in a else a for a in line)])


def in_window(line: list[str]) -> bool:
    """True when the command only prints (its output in a window); False when it takes the terminal."""
    if not line:
        return False
    if line[0] == "logs" and len(line) == 1:
        return False                                   # logs alone follows them
    return line[0] in IN_WINDOW and not any(a in ("-f", "--follow", "--console", "--web") for a in line[1:])


STATE_COLOUR = {"running": "green", "healthy": "green", "starting": "yellow", "restarting": "yellow", "created": "yellow",
                "paused": "yellow", "exited": "red", "dead": "red", "unhealthy": "red", "removing": "yellow"}


def containers(lines: list[str]) -> list[dict]:
    """docker compose ps --format json (one object a line, or one array) as rows: service, state, health, colour, status."""
    rows: list[dict] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            got = json.loads(ln)
        except ValueError:
            continue
        for c in got if isinstance(got, list) else [got]:
            state = str(c.get("State") or "").lower()
            health = str(c.get("Health") or "").lower()
            word = health if health in ("unhealthy", "starting") else state
            rows.append({"service": c.get("Service") or c.get("Name") or "?", "state": state, "health": health,
                         "colour": STATE_COLOUR.get(word, "white"), "status": c.get("Status") or state})
    return sorted(rows, key=lambda r: (r["colour"] != "red", r["colour"] != "yellow", r["service"]))


def disks(paths: list[Path]) -> list[dict]:
    """Free space where EA Explorer keeps its files: path, free, total, percent used, colour (red over 90%)."""
    out, seen = [], set()
    for p in paths:
        try:
            u = shutil.disk_usage(p)
        except OSError:
            continue
        key = (u.total, u.free)
        if key in seen:
            continue
        seen.add(key)
        used = round(100 * (u.total - u.free) / u.total) if u.total else 0
        out.append({"path": str(p), "free": u.free, "total": u.total, "used": used,
                    "colour": "red" if used >= 90 else "yellow" if used >= 80 else "green"})
    return out


def gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


STATUS_LINE = "F1 Help  F10 Menu  F5 Refresh  Alt+F5 User screen  Alt+X Exit"
