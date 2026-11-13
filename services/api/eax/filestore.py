"""The file store (R2.44, D635; owner, 12 Nov 2026, 21:28: "users should be able to work on local file system, but purely
serverless docker environment uses a separate DB"; 13 Nov 2026: schemas only).

One setting chooses where EA Explorer's own files go, so nothing else changes between the two:

  EAX_FILE_STORE=folder     (default; laptop and server) the work folder and the API's folders, as today
  EAX_FILE_STORE=database   a Docker platform with no local file system: the files schema (files.store), reached by
                            EAX_FILES_DB_URL (empty = the repository's database)

Areas: tests (each self-test run's folder: run.log, report.html and .xlsx, videos, the scanners' reports) and exports
(a model's last package before it is deleted). Backups never go into a database (owner, 21:47): see eax/backup_folder.py.
In database mode the self-test still writes its folder in the container while it runs (a temporary folder) and the
whole folder is put in the store when the run ends (put_folder); the screens read it from the store.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from sqlalchemy import text

AREAS = ("tests", "exports")


def mode() -> str:
    from .config import _env
    v = _env("EAX_FILE_STORE", "folder").lower()
    return "database" if v == "database" else "folder"


def in_database() -> bool:
    return mode() == "database"


def _engine():
    from . import databases
    return databases.engine_for("files")


def _check(area: str, name: str) -> None:
    if area not in AREAS:
        raise ValueError(f"No file area {area!r}.")
    if not name or name.startswith("/") or ".." in Path(name).parts or len(name) > 500:
        raise ValueError("Not a file name of the store.")


def put(area: str, name: str, content: bytes) -> int:
    _check(area, name)
    with _engine().begin() as c:
        c.execute(text("""INSERT INTO files.store (area, name, content, bytes) VALUES (:a, :n, :c, :b)
                          ON CONFLICT (area, name) DO UPDATE SET content = EXCLUDED.content, bytes = EXCLUDED.bytes,
                                                                 modified_at = now()"""),
                  {"a": area, "n": name, "c": content, "b": len(content)})
    return len(content)


def get(area: str, name: str) -> bytes | None:
    _check(area, name)
    with _engine().connect() as c:
        v = c.execute(text("SELECT content FROM files.store WHERE area = :a AND name = :n"), {"a": area, "n": name}).scalar()
    return bytes(v) if v is not None else None


def listing(area: str, prefix: str = "") -> list[dict]:
    if area not in AREAS:
        raise ValueError(f"No file area {area!r}.")
    with _engine().connect() as c:
        return [dict(r) for r in c.execute(text("""SELECT name, bytes, modified_at FROM files.store
                                                     WHERE area = :a AND name LIKE :p ORDER BY name"""),
                                           {"a": area, "p": prefix.replace("%", r"\%").replace("_", r"\_") + "%"}).mappings()]


def delete(area: str, prefix: str) -> int:
    """Every file under a prefix (a run's folder) taken out of the store."""
    if area not in AREAS or not prefix:
        raise ValueError("Say which files to delete.")
    with _engine().begin() as c:
        return c.execute(text("DELETE FROM files.store WHERE area = :a AND (name = :p OR name LIKE :pp)"),
                         {"a": area, "p": prefix.rstrip("/"), "pp": prefix.rstrip("/").replace("%", r"\%").replace("_", r"\_") + "/%"}).rowcount


def put_folder(area: str, folder: Path, under: str) -> int:
    """A local folder's files put in the store under `under/` (a self-test run's folder when the run ends)."""
    n = 0
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file():
            put(area, f"{under}/{p.relative_to(folder).as_posix()}", p.read_bytes())
            n += 1
    return n


def kind_of(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def local_root(area: str) -> Path:
    """Where an area's files are in folder mode."""
    if area == "tests":
        return Path(os.environ.get("EAX_WORK_TESTS", "/eax-work/tests"))
    return Path(os.environ.get("EAX_EXPORT_DIR_IN", "/data/exports"))
