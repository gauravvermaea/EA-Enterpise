"""eax persist: what persist/ holds, and deleting it (owner, 12 Nov 2026: "give command line and web ui ability to delete
anything in persist", R2.26). persist/ survives every reset by design (D558); this is the one way to empty it.

  eax persist                       list it: name, size, when changed, what it is
  eax persist delete <item> [--yes] delete one item (a settings file with its .bak, or a safety backup)
  eax persist delete --all [--yes]  delete everything in it
"""

from __future__ import annotations

from datetime import datetime

from . import persist


def _size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def main(rest: list[str], ask=input) -> int:
    args = [a for a in rest if not a.startswith("--")]
    flags = {a for a in rest if a.startswith("--")}
    if not args or args[0] == "list":
        found = persist.items()
        print(f"persist/ ({persist.folder()}): kept across every reset (D558)")
        if not found:
            print("  empty")
        for i in found:
            when = datetime.fromtimestamp(i["changed"]).strftime("%Y-%m-%d %H:%M")
            print(f"  {i['name']:<44}{_size(i['size']):>10}  {when}  {i['what']}")
        return 0
    if args[0] != "delete" or (len(args) < 2 and "--all" not in flags):
        print(__doc__)
        return 2
    names = [i["name"] for i in persist.items()] if "--all" in flags else [args[1]]
    if not names:
        print("persist/ is empty: nothing to delete.")
        return 0
    print(f"This deletes FOR GOOD: {', '.join(names)}. A deleted settings file falls back to its default.")
    if "--yes" not in flags and ask("Type DELETE to go on: ").strip() != "DELETE":
        print("Nothing deleted.")
        return 1
    try:
        gone = []
        for n in names:
            gone += persist.delete(n)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"Deleted: {', '.join(gone)}.")
    return 0
