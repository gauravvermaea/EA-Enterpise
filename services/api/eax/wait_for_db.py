"""Wait until the repository database accepts connections (used by the container entrypoint)."""

from __future__ import annotations

import sys
import time

import psycopg

from .config import get_settings


def main(timeout_seconds: int = 120) -> int:
    settings = get_settings()
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with psycopg.connect(settings.libpq_conninfo, connect_timeout=3):
                print("EA Explorer: database is reachable")
                return 0
        except psycopg.OperationalError as exc:
            if time.monotonic() > deadline:
                print(f"EA Explorer: database not reachable: {exc}", file=sys.stderr)
                return 1
            time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
