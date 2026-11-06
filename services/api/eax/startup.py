"""Starting several API and job servers side by side (D249): each api container runs this at start.

    python -m eax.startup serial -- <command> [args]   wait for the start-up lock, run the command, let the lock go: the
                                                     database upgrade and the seed run on one server at a time (the
                                                     first does the work, the others find nothing left to do)
    python -m eax.startup single <name> -- <command>   run the command on one server only: the others wait (and take
                                                     over if that server stops), for the change log shipper
    python -m eax.startup once <name> -- <command>     run the command unless another server runs it now (then
                                                     skip it): the work after the API has started (D255)

Both use PostgreSQL advisory locks held by a session of this process (not triggers or functions in the database, D248);
a lock goes away by itself when the process or its server stops.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time

import psycopg

from .config import get_settings


def _key(name: str) -> int:
    return int.from_bytes(hashlib.sha256(f"eax:{name}".encode()).digest()[:8], "big", signed=True)


def _connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().libpq_conninfo, autocommit=True)


def serial(cmd: list[str]) -> int:
    with _connect() as conn:
        print("EA Explorer: waiting for the start-up lock (one server at a time)", flush=True)
        conn.execute("SELECT pg_advisory_lock(%s)", (_key("startup"),))
        try:
            return subprocess.call(cmd)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_key("startup"),))


def single(name: str, cmd: list[str]) -> int:
    conn = _connect()
    while not conn.execute("SELECT pg_try_advisory_lock(%s)", (_key(name),)).fetchone()[0]:
        time.sleep(15)        # another server runs it; take over if it stops
    print(f"EA Explorer: this server runs {name}", flush=True)
    try:
        return subprocess.call(cmd)
    finally:
        conn.close()


def once(name: str, cmd: list[str]) -> int:
    conn = _connect()
    try:
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (_key(name),)).fetchone()[0]:
            print(f"EA Explorer: another server runs {name}; skipped here", flush=True)
            return 0
        return subprocess.call(cmd)
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if "--" not in argv or not argv:
        print(__doc__)
        return 2
    i = argv.index("--")
    head, cmd = argv[:i], argv[i + 1:]
    if head[:1] == ["serial"]:
        return serial(cmd)
    if head[:1] == ["single"] and len(head) == 2:
        return single(head[1], cmd)
    if head[:1] == ["once"] and len(head) == 2:
        return once(head[1], cmd)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
