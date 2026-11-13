"""Where backups go (R2.44, D635; owner, 12 Nov 2026, 21:47: "On the selected folder server that is mounted, for laptop on
file system. On server or docker ask for a file system that is mounted as a part of initial config").

Backups never go into a database. On a laptop they go to work/backups, as always. On a server or a Docker platform
the first-time setup (eax init) asks for a mounted folder (a network share or a volume), kept as EAX_BACKUP_DIR; until
one is given, EA Explorer takes no backup and says why.
"""

from __future__ import annotations


def folder() -> str:
    from .config import _env
    return _env("EAX_BACKUP_DIR", "")


def ready() -> tuple[bool, str]:
    """Whether backups may be taken here, and why not."""
    from .config import get_settings
    if get_settings().deployment == "laptop" or folder():
        return True, ""
    return False, ("No backups yet: give the mounted folder for backups first (a network share or a volume): EAX_BACKUP_DIR "
                   "in eaexplorer.env (eax init asks for it), then eax up.")
