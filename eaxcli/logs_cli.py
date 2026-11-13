"""eax logs backup | clean (R2.30): the containers' daily log files (logs/, EAX_LOGS_DIR) and eax's own logs (work/logs).

  eax logs backup [tag] [--outside-work]   one zip of them in work/backups/logs (or, before a reset, logs/backups:
                                           cleanup and clean-restart take one there by themselves, R2.30)
  eax logs clean [--older-than N] [--yes]  deletes those older than N days (default: the deployment's, 14 on a laptop,
                                           90 on a server), and the log backups older than that
Following the logs stays `eax logs [service]`.
"""

from __future__ import annotations

from pathlib import Path

from . import logkeep, persist

ROOT = Path(__file__).resolve().parent.parent


def main(rest: list[str], ask=input) -> int:
    if not rest or rest[0] not in ("backup", "clean"):
        print(__doc__)
        return 2
    base, own, zips = logkeep.folder(), ROOT / "work" / "logs", ROOT / "work" / "backups" / "logs"
    if rest[0] == "backup":
        tag = next((a for a in rest[1:] if not a.startswith("--")), "")
        dest = logkeep.kept_backups(base) if "--outside-work" in rest else zips
        out = logkeep.backup(base, own, dest, tag)
        where = f"{dest}/{out['file']}" if "--outside-work" in rest else f"work/backups/logs/{out['file']}"
        print(f"Logs backed up: {where} ({out['files']} files, {out['size'] // 1024} KB).")
        return 0
    days = logkeep.default_keep_days(persist._config_value(ROOT, "EAX_DEPLOYMENT") or "laptop")
    if "--older-than" in rest:
        i = rest.index("--older-than")
        if i + 1 >= len(rest) or not rest[i + 1].isdigit() or int(rest[i + 1]) < 1:
            print("--older-than takes a number of days, 1 or more.")
            return 2
        days = int(rest[i + 1])
    print(f"This deletes the logs and log backups older than {days} days (before {logkeep.older_than(days)}) for good.")
    if "--yes" not in rest and ask("Type DELETE to go on: ").strip() != "DELETE":
        print("Nothing deleted.")
        return 1
    out = logkeep.clean(base, own, zips, days)
    out["deleted"] += logkeep.clean(base, own, logkeep.kept_backups(base), days)["deleted"]
    print(f"Deleted {len(out['deleted'])} file(s)." + (f" {', '.join(out['deleted'][:10])}" if out["deleted"] else ""))
    return 0
