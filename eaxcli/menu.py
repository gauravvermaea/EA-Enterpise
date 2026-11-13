"""eax menu (R2.29; owner, 13 Nov 2026): a numbered menu of every command, by group, for every form of eax.

  eax            with no command, on a terminal: this menu (piped or in a script: the help, as before)
  eax menu       the same

Pick a group, then a command; each of its options is asked for in turn (Enter leaves an optional one out), the whole
command is shown, and it runs only when you say y. The groups and commands come from eaxcli/help.txt, the one source
of the help (D331), so the menu never lists a command the help does not.

eax.sh and eax.ps1 hand `menu` to this program (through eaxpy, as deploy and packs, D500) with EAX_FORM set, so the
command chosen runs in the form that was typed: ./eax.sh <command> or .\\eax <command>.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable

from . import help as help_
from .core import EAX, ROOT, WINDOWS, heading, paint

Ask = Callable[[str], str]


def _form() -> tuple[str, str, bool]:
    """(form, how the command is typed, windows) of the eax that opened the menu."""
    form = os.environ.get("EAX_FORM", "")
    if form == "ps1":
        return "ps1", ".\\eax", True
    if form == "sh":
        return "sh", "./eax.sh", False
    return "py", EAX, WINDOWS


def groups(form: str = "py", windows: bool = WINDOWS) -> list[dict]:
    doc = help_.parse(help_.SOURCE.read_text(encoding="utf-8"), {form, "win" if windows else "unix"})
    return [s for s in doc["sections"] if s["commands"]]


def split_args(spec: str) -> list[str]:
    """The top-level parts of a command's options: '[a|b] [--yes] <id>' -> ['[a|b]', '[--yes]', '<id>']."""
    parts, depth, cur = [], 0, ""
    for ch in spec:
        if ch == " " and depth == 0:
            if cur:
                parts.append(cur)
            cur = ""
            continue
        depth += ch in "[<"
        depth -= ch in "]>"
        cur += ch
    if cur:
        parts.append(cur)
    return parts


def question(part: str) -> dict:
    """What to ask for one option: a choice, a yes/no flag, a value (optional or not), or free text."""
    optional = part.startswith("[") and part.endswith("]")
    inner = part[1:-1] if optional else part
    if any(c in inner for c in "[]") or (" " in inner and not re.fullmatch(r"--[\w-]+ \S+", inner)):
        return {"kind": "text", "label": part, "optional": True}
    m = re.fullmatch(r"(--[\w-]+) (\S+)", inner)
    if m:                                                         # [--what full|app|db]  [--older-than N]
        choices = m.group(2).split("|") if "|" in m.group(2) and "<" not in m.group(2) else []
        return {"kind": "option", "flag": m.group(1), "choices": choices, "label": m.group(2), "optional": True}
    if re.fullmatch(r"--[\w-]+", inner):                         # [--yes]
        return {"kind": "flag", "flag": inner, "optional": True}
    if "|" in inner:                                              # [laptop|server]  on|off
        return {"kind": "choice", "choices": inner.split("|"), "optional": optional}
    return {"kind": "value", "label": inner.strip("<>").rstrip("."), "many": inner.endswith("..."),
            "optional": optional or part.startswith("[")}


def _pick(ask: Ask, prompt: str, n: int, optional: bool = True) -> int | None:
    """A number from 1 to n; Enter (when optional) or q gives None."""
    while True:
        a = ask(prompt).strip().lower()
        if a in ("q", "quit") or (not a and optional):
            return None
        if a.isdigit() and 1 <= int(a) <= n:
            return int(a)
        print(f"  Type a number from 1 to {n}" + (", or Enter to leave it out." if optional else "."))


def ask_options(spec: str, ask: Ask) -> list[str] | None:
    """Every option of a command asked for in turn; None when the person quits."""
    out: list[str] = []
    for part in split_args(spec):
        q = question(part)
        if q["kind"] == "flag":
            if ask(f"  {q['flag']}? [y/N] ").strip().lower() in ("y", "yes"):
                out.append(q["flag"])
        elif q["kind"] in ("choice", "option") and q.get("choices"):
            head = q["flag"] if q["kind"] == "option" else part
            print(f"  {head}:")
            for i, c in enumerate(q["choices"], 1):
                print(f"    {i}  {c}")
            other = len(q["choices"]) + 1                        # a name, a tag, a run: typed rather than chosen
            print(f"    {other}  something else (type it)")
            n = _pick(ask, "  Number" + (" (Enter: leave it out): " if q["optional"] else ": "), other, q["optional"])
            if n is None and not q["optional"]:
                return None
            value = q["choices"][n - 1] if n is not None and n < other else ""
            if n == other:
                value = ask("  Type it: ").strip()
            if value:
                out += ([q["flag"]] if q["kind"] == "option" else []) + [value]
        elif q["kind"] == "option":
            v = ask(f"  {q['flag']} {q['label']} (Enter: leave it out): ").strip()
            if v:
                out += [q["flag"], v]
        elif q["kind"] == "value":
            many = " (several: spaces between)" if q.get("many") else ""
            v = ask(f"  {q['label']}{many}" + (" (Enter: leave it out): " if q["optional"] else ": ")).strip()
            if not v and not q["optional"]:
                print(f"  {q['label']} is needed; stopped.")
                return None
            out += v.split() if v else []
        else:
            v = ask(f"  Options {q['label']} (Enter: none): ").strip()
            out += v.split() if v else []
    return out


def choose(ask: Ask = input, form: str = "", eax: str = "", windows: bool | None = None) -> list[str] | None:
    """The menu itself: the command line chosen (as arguments), or None when the person quits."""
    if not form:
        form, eax, windows = _form()
    gs = groups(form, bool(windows))
    while True:
        print()
        heading("EA Explorer: what do you want to do?")
        for i, g in enumerate(gs, 1):
            print(f"  {i:>2}  {g['title']}")
        n = _pick(ask, "Group number (q to quit): ", len(gs), optional=False)
        if n is None:
            return None
        g = gs[n - 1]
        print()
        heading(g["title"])
        for note in g["notes"]:
            print(paint("  " + note, "yellow"))
        for i, c in enumerate(g["commands"], 1):
            print(f"  {i:>2}  {c['names'][0]:<16}{c['summary']}")
        c_n = _pick(ask, "Command number (Enter: back to the groups): ", len(g["commands"]))
        if c_n is None:
            continue
        c = g["commands"][c_n - 1]
        if c["args"]:
            print(f"{c['names'][0]} {c['args']}")
        opts = ask_options(c["args"], ask)
        if opts is None:
            continue
        line = [c["names"][0], *opts]
        print()
        print("Will run:  " + paint(f"{eax} {' '.join(line)}", "cyan"))
        if ask("Run it? [y/N] ").strip().lower() in ("y", "yes"):
            return line
        print("Not run.")


def run(line: list[str]) -> int:
    """The chosen command, run in the form of eax that opened the menu."""
    form = os.environ.get("EAX_FORM", "")
    if form == "sh":
        return subprocess.call(["bash", str(ROOT / "eax.sh"), *line])
    if form == "ps1":
        exe = os.environ.get("EAX_FORM_EXE") or "powershell"
        return subprocess.call([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "eax.ps1"), *line])
    from . import main as main_
    return main_.main(line)


def main(argv: list[str] | None = None) -> int:
    if not sys.stdin.isatty() and not os.environ.get("EAX_MENU_ANYWAY"):
        _, eax, windows = _form()
        print(help_.render(_form()[0], eax, windows)[0])
        return 0
    try:
        line = choose()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    return run(line) if line else 0
