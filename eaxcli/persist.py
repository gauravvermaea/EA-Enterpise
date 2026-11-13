"""Settings that survive resets (owner, 10 Nov 2026, D558): the persist/ folder beside the installation.

cleanup, clean-run and clean-restart empty work/ (the config file, logs, laptop data, backups) and the Docker volumes.
Some settings must outlive that, e.g. a demo that resets itself every night: they live in persist/, which no command
ever deletes, as small JSON files a person can also read and edit by hand:

  persist/schedules.json      scheduled eax commands (eaxcli/schedules.py)
  persist/banner.json         the banner under the top bar (eaxcli/banner.py)
  persist/safety-backups/     the backup taken before a command that deletes everything (eaxcli/commands.py)
  persist/test-results/       the reset-survival test's results (eaxcli/reset_survival.py)

The JSON files are the source of truth. They are written atomically (a temporary file, then a rename), with the last
good copy kept as <name>.bak; a file that does not parse is never fatal: the .bak is used and a warning is returned.
The folder is EAX_PERSIST_DIR (in the config file or the environment), else persist/ at the installation's root.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = 1


def _config_value(root: Path, key: str) -> str:
    try:
        for line in (root / "work" / "eaexplorer.env").read_text(encoding="utf-8").splitlines():
            m = re.match(rf"^\s*{key}\s*=(.*)$", line)
            if m:
                return m.group(1).strip().strip("'\"")
    except OSError:
        pass
    return ""


def folder(root: Path | str | None = None) -> Path:
    """persist/: EAX_PERSIST_DIR from the environment or the config file, else persist/ beside work/."""
    root = Path(root) if root else ROOT
    given = os.environ.get("EAX_PERSIST_DIR") or _config_value(root, "EAX_PERSIST_DIR")
    p = Path(given) if given else root / "persist"
    if not p.is_absolute():
        p = root / p
    return p


def write_json(path: Path | str, data: dict) -> None:
    """Atomically: the old file becomes .bak, the new one is written to a temporary file and renamed into place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)                                         # never write what would not read back
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    if path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))     # only a good file becomes the last good copy
            shutil.copyfile(path, path.with_name(path.name + ".bak"))
        except (OSError, ValueError):
            pass
    os.replace(tmp, path)


def read_json(path: Path | str, default: dict) -> tuple[dict, str]:
    """(data, warning): the file; if it is missing, the default; if it does not parse, its .bak with a warning; if
    that fails too, the default with a warning. Never raises."""
    path = Path(path)
    if not path.exists():
        return dict(default), ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")  # noqa: TRY004 - caught just below, as a bad file
        return data, ""
    except (OSError, ValueError) as exc:
        bak = path.with_name(path.name + ".bak")
        try:
            data = json.loads(bak.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, (f"{path.name} could not be read ({exc}); the last good copy ({bak.name}) is used. "
                              f"Fix {path.name} or save the settings again.")
        except (OSError, ValueError):
            pass
        return dict(default), f"{path.name} could not be read ({exc}) and there is no good copy; nothing from it is used."


# ---------------------------------------------------------------- what is there, and deleting it (R2.26)
WHAT = {
    "schedules.json": "scheduled eax commands (none once deleted)",
    "banner.json": "the banner under the top bar and its history (no banner once deleted)",
    "settings.json": "the Self-test page's settings (the defaults once deleted)",
    "test-results": "the reset-survival test's results",
}


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def items(root: Path | str | None = None) -> list[dict]:
    """What persist/ holds, one item per settings file (with its .bak) and per safety backup: name, kind, size in
    bytes, when changed, what it is."""
    base = folder(root)
    out: list[dict] = []
    if not base.is_dir():
        return out
    for p in sorted(base.iterdir()):
        if p.name.endswith((".bak", ".tmp")) or ".tmp" in p.name:
            continue
        if p.name == "safety-backups" and p.is_dir():
            for b in sorted(p.iterdir()):
                out.append({"name": f"safety-backups/{b.name}", "kind": "folder" if b.is_dir() else "file",
                            "size": _size(b), "changed": b.stat().st_mtime,
                            "what": "the record of commands run from the web" if b.name == "commands" else
                            "a safety backup taken before a command that deletes everything"})
            continue
        bak = p.with_name(p.name + ".bak")
        out.append({"name": p.name, "kind": "folder" if p.is_dir() else "file",
                    "size": _size(p) + (bak.stat().st_size if bak.exists() else 0), "changed": p.stat().st_mtime,
                    "what": WHAT.get(p.name, "kept across resets")})
    return out


def delete(name: str, root: Path | str | None = None) -> list[str]:
    """Deletes one item of items() for good (a file with its .bak, or a folder with all in it); returns what went.
    Only what items() lists: nothing outside persist/."""
    base = folder(root).resolve()
    known = {i["name"] for i in items(root)}
    if name not in known:
        raise ValueError(f"persist/ has no {name!r}. There: {', '.join(sorted(known)) or 'nothing'}.")
    target = (base / name).resolve()
    if base not in target.parents:
        raise ValueError("Only what is in persist/ can be deleted.")
    gone = []
    for p in (target, target.with_name(target.name + ".bak")):
        if p.is_dir():
            shutil.rmtree(p)
            gone.append(str(p.relative_to(base)))
        elif p.exists():
            p.unlink()
            gone.append(str(p.relative_to(base)))
    return gone


def delete_all(root: Path | str | None = None) -> list[str]:
    """Every item of items(), for good."""
    gone: list[str] = []
    for i in items(root):
        gone += delete(i["name"], root)
    return gone
