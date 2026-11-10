"""The help of the eax command (D331), read from eaxcli/help.txt: the one source for eax.ps1, eax.sh and eaxpy.

eax.ps1 and eax.sh print the same text from the same file with their own few lines of code; tests/test_eax_help.py
checks that all three agree, and that every command each script accepts is in the help.
"""

from __future__ import annotations

import re
from pathlib import Path

SOURCE = Path(__file__).with_name("help.txt")
PAGE = Path(__file__).with_name("document.html")   # eax document --web: the page, filled from help.txt
TAGS = {"win", "unix", "ps1", "sh", "py"}


def parse(text: str, tags: set[str]) -> dict:
    """The help as intro, sections (each with notes and commands), internal commands and footer, for these tags."""
    doc: dict = {"intro": [], "sections": [], "internal": [], "footer": []}
    where = "intro"
    cmd = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith(";"):
            continue
        m = re.match(r"^\[(\w+)\] ?", line)
        if m and m.group(1) in TAGS:
            if m.group(1) not in tags:
                continue
            line = line[m.end():]
        if where == "footer":
            doc["footer"].append(line)
        elif line == "@footer":
            where = "footer"
        elif line.startswith("@internal "):
            name, _, what = line[len("@internal "):].partition(" ")
            doc["internal"].append((name, what))
        elif line.startswith("## "):
            doc["sections"].append({"title": line[3:], "notes": [], "commands": []})
            where, cmd = "section", None
        elif line.startswith("### "):
            names, _, args = line[4:].partition(" ")
            cmd = {"names": names.split("|"), "args": args, "summary": "", "detail": [], "examples": []}
            doc["sections"][-1]["commands"].append(cmd)
        elif where == "intro":
            if line:
                doc["intro"].append(line)
        elif line.startswith(": ") and cmd is None:
            doc["sections"][-1]["notes"].append(line[2:])
        elif cmd is None:
            continue
        elif line.startswith("> "):
            cmd["summary"] = line[2:]
        elif line.startswith("$ "):
            cmd["examples"].append(line[2:])
        elif line:
            cmd["detail"].append(line)
    while doc["footer"] and not doc["footer"][-1]:
        doc["footer"].pop()
    return doc


def _label(c: dict) -> str:
    return " ".join(x for x in (", ".join(c["names"]), c["args"]) if x)


def _block(c: dict) -> list[str]:
    head = "  " + " ".join(x for x in (c["names"][0], c["args"]) if x)
    if len(c["names"]) > 1:
        head += "   (also: " + ", ".join(c["names"][1:]) + ")"
    out = [head, "    " + c["summary"]]
    out += ["    " + d for d in c["detail"]]
    if c["examples"]:
        out.append("    Examples:")
        out += ["      " + e for e in c["examples"]]
    return out


def _text(c: dict) -> str:
    return " ".join([*c["names"], c["args"], c["summary"], *c["detail"], *c["examples"]]).lower()


def lines(doc: dict, name: str = "", arg: str = "") -> tuple[list[str], int]:
    """The lines to print for help (name ""), help <command> or help --all, and the exit code. For eax document's
    console: --groups (the groups, numbered), --group <n> (one group in full), --search <word> (every command with it)."""
    out: list[str] = []
    if name == "--groups":
        return [f"{i:>4}  {s['title']}" for i, s in enumerate(doc["sections"], 1)], 0
    if name == "--group":
        n = int(arg) if arg.isdigit() else 0
        if not 1 <= n <= len(doc["sections"]):
            return [f"No group {arg}."], 1
        s = doc["sections"][n - 1]
        out = [s["title"]] + ["  " + x for x in s["notes"]]
        for c in s["commands"]:
            out += [""] + _block(c)
        return out, 0
    if name == "--search":
        word = arg.lower()
        for s in doc["sections"]:
            for c in s["commands"]:
                if word and word in _text(c):
                    out += [""] + _block(c)
        return (out[1:], 0) if out else ([f"Nothing found for '{arg}'."], 1)
    if name in ("", "--all"):
        out += doc["intro"]
        for s in doc["sections"]:
            out += ["", s["title"]]
            out += ["  " + n for n in s["notes"]]
            for c in s["commands"]:
                if name:
                    out += [""] + _block(c)
                    continue
                label = _label(c)
                out += [f"  {label:<22}{c['summary']}"] if len(label) <= 20 else [f"  {label}", " " * 24 + c["summary"]]
        if name and doc["internal"]:
            out += ["", "Internal (run by eax itself; not for typing)"]
            out += [f"  {n:<22}{w}" for n, w in doc["internal"]]
        out += [""] + doc["footer"]
        return out, 0
    for s in doc["sections"]:
        for c in s["commands"]:
            if name in c["names"]:
                return _block(c), 0
    for n, w in doc["internal"]:
        if n == name:
            return [f"  {n}", "    " + w], 0
    return [f"No command '{name}'. Run {{eax}} help to list them."], 1


def render(form: str, eax: str, windows: bool, name: str = "", arg: str = "") -> tuple[str, int]:
    """The help text for one form (ps1, sh, py) as typed with eax, on Windows or not."""
    tags = {form, "win" if windows else "unix"}
    out, code = lines(parse(SOURCE.read_text(encoding="utf-8"), tags), name, arg)
    text = "\n".join(out).replace("{eax}", eax)
    if windows:
        text = re.sub(r"\bwork/[^\s,;)]*", lambda m: m.group(0).replace("/", "\\"), text)
    return text, code


def commands() -> set[str]:
    """Every command name and alias the help lists (internal ones included)."""
    doc = parse(SOURCE.read_text(encoding="utf-8"), TAGS)
    names = {n for s in doc["sections"] for c in s["commands"] for n in c["names"]}
    return names | {n for n, _ in doc["internal"]}


def document_html(form: str, eax: str, windows: bool) -> str:
    """eax document --web: the page (document.html) with help.txt copied in as it is; the page reads it the same way.
    eax.ps1 and eax.sh make the same file byte for byte (tests/test_eax_help.py)."""
    page = PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")
    page = page.replace("__FORM__", form).replace("__EAX__", eax).replace("__WINDOWS__", "true" if windows else "false")
    return page.replace("__HELP__", "\n".join(SOURCE.read_text(encoding="utf-8").splitlines()))
