"""Application backups and model restores from the command line (phase 8.4, D227), for when the screens cannot be used.

Run in the api container by the eax command:
    .\\eax app-backup [tag]              every model backed up now
    .\\eax restore-model                 choose an application backup, a model in it, then: as a new model or over itself
    .\\eax restore-model <run> <file> [--new "<name>" | --over] [--yes]
    .\\eax restore-app [run|tag|latest] [--yes]   every model of an application backup put back over itself; models no
                                         longer there are made again; models made since stay as they are (D233)
Every restore is recorded with its log in work/backups/restores (listed by .\\eax restores and on Administration >
Restores). It runs as the system with the Super Admin's rights, so whoever runs it on the server must be trusted to.
"""

from __future__ import annotations

import sys

from . import backups as bk
from . import permissions as perms
from .db import get_engine
from .metamodel_edit import EditError

SYSTEM = perms.Principal("eax-command", (perms.SUPER_ADMIN,))


def _ask(prompt: str, choices: list[str] | None = None) -> str:
    while True:
        try:
            answer = input(prompt).strip()
        except EOFError:
            return ""
        if not choices or answer in choices:
            return answer
        print(f"  Type one of: {', '.join(c or '(empty)' for c in choices)}")


def _pick(rows: list, label) -> int | None:
    for i, r in enumerate(rows, 1):
        print(f"  {i:>3}  {label(r)}")
    n = _ask(f"Which (1-{len(rows)}, empty to stop)? ", [""] + [str(i) for i in range(1, len(rows) + 1)])
    return int(n) - 1 if n else None


def backup(tag: str) -> int:
    with get_engine().begin() as conn:
        msg, out = bk.application_backup(conn, SYSTEM, tag or "eax-command")
    print(msg)
    print(f"Folder: work/backups/application/{out['name']}")
    return 0 if not out["failed"] else 1


def restore_model(args: list[str]) -> int:
    runs = [r for r in bk.list_application()["runs"] if r.get("status") in ("ok", "partial")]
    uploaded = bk.list_application()["uploaded"]
    where, name, file = "application", "", ""
    positional = [a for a in args if not a.startswith("--") and a not in _option_values(args)]
    if len(positional) >= 2:
        name, file = positional[0], positional[1]
        where = "uploaded" if name == "uploaded" else "application"
    else:
        if not runs and not uploaded:
            print("No application backup to restore from: make one with .\\eax app-backup")
            return 1
        print("Application backups (work/backups/application):")
        choices = [("application", r) for r in runs] + [("uploaded", u) for u in uploaded]
        i = _pick(choices, lambda x: f"{bk.human(x[1].get('created', ''))}  {x[1].get('tag') or 'uploaded: ' + x[1]['model']['name']}"
                  f"  ({len([m for m in x[1].get('models') or [] if m.get('status') == 'ok']) or 1} model(s))")
        if i is None:
            return 1
        where, chosen = choices[i]
        if where == "uploaded":
            name, file = "", chosen["file"]
        else:
            name = chosen["name"]
            models = [m for m in chosen.get("models") or [] if m.get("status") == "ok"]
            print(f"Models in {chosen.get('tag')}:")
            j = _pick(models, lambda m: f"{m['name']}  ({m.get('kind')}, {(m.get('counts') or {}).get('entities', 0)} entities)")
            if j is None:
                return 1
            file = models[j]["file"]
    path = bk.path_of(where, name, file)
    info, z = bk.read_file(path)
    z.close()
    mode = "over" if "--over" in args else "new" if "--new" in args else ""
    if not mode:
        print(f"  1  as a new model (a draft, next to {info['model']['name']})")
        if where != "uploaded" and info["model"].get("kind") != "template":
            print(f"  2  over {info['model']['name']} (it goes back to how it was in this backup; what it is now is backed up first)")
        mode = {"1": "new", "2": "over"}.get(_ask("How (1 or 2)? ", ["1", "2"]), "new")
    new_name = args[args.index("--new") + 1] if "--new" in args and args.index("--new") + 1 < len(args) else ""
    if mode == "new" and not new_name and "--yes" not in args:
        new_name = _ask(f"Name of the new model (empty: '{info['model']['name']} (restored ...)'): ")
    if "--yes" not in args:
        what = f"over {info['model']['name']}" if mode == "over" else f"as the new model '{new_name or info['model']['name'] + ' (restored ...)'}'"
        if _ask(f"Restore {file} {what}? Type RESTORE to go on: ") != "RESTORE":
            print("Nothing restored.")
            return 1
    try:
        with get_engine().begin() as conn:
            msg, out = bk.restore(conn, SYSTEM, {"where": where, "name": name, "file": file, "model": info["model"]["id"],
                                                 "mode": mode, "new_name": new_name, "target": info["model"]["id"]})
    except EditError as exc:
        print(f"Not restored: {exc}")
        return 1
    print(msg)
    print(f"Log: work/backups/restores/{out['restore']}/restore.log")
    return 0


def restore_all(args: list[str]) -> int:
    runs = [r for r in bk.list_application()["runs"] if r.get("status") in ("ok", "partial")]
    if not runs:
        print("No application backup to restore from: make one with .\\eax app-backup")
        return 1
    want = next((a for a in args if not a.startswith("--")), "")
    if want:
        low = want.lower()
        hits = runs[:1] if low in ("latest", "newest") else [r for r in runs if low in (r["name"].lower(), str(r.get("tag") or "").lower())]
        if not hits:
            print(f"No application backup named or tagged '{want}': .\\eax backups lists them.")
            return 1
        run = hits[0]
    else:
        print("Application backups (work/backups/application):")
        i = _pick(runs, lambda r: f"{bk.human(r.get('created', ''))}  {r.get('tag')}  "
                                  f"({len([m for m in r.get('models') or [] if m.get('status') == 'ok'])} models)")
        if i is None:
            return 1
        run = runs[i]
    n = len([m for m in run.get("models") or [] if m.get("status") == "ok"])
    print(f"Backup: {run['name']} (tag {run.get('tag')}, made {bk.human(run.get('created', ''))} by {run.get('by')}), {n} models.")
    print("Every model in it goes back to how it was in this backup (each one is backed up first, and kept as a tag);")
    print("models no longer there are made again; models made since stay as they are. Everyone is notified.")
    if "--yes" not in args and _ask("Type RESTORE to go on: ") != "RESTORE":
        print("Nothing restored.")
        return 1
    try:
        with get_engine().begin() as conn:
            msg, out = bk.restore_application(conn, SYSTEM, run["name"])
    except EditError as exc:
        print(f"Not restored: {exc}")
        return 1
    print(msg)
    for f in out["failed"]:
        print(f"  Not restored: {f}")
    print(f"Log: work/backups/restores/{out['restore']}/restore.log")
    return 0 if not out["failed"] else 1


def _option_values(args: list[str]) -> set[str]:
    return {args[i + 1] for i, a in enumerate(args[:-1]) if a == "--new"}


def main(argv: list[str]) -> int:
    perms.current.set(SYSTEM)   # the database sees the command as a Super Admin (as the job runner sees the person)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "backup":
        return backup(argv[1] if len(argv) > 1 else "")
    if argv[0] == "restore":
        return restore_model(argv[1:])
    if argv[0] == "restore-all":
        return restore_all(argv[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
