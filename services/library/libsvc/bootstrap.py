"""Start-up: the library's database and its login are made when missing (as the PostgreSQL superuser, on the same
server on a laptop, D346), then the migrations in libsvc/migrations are run, each once, in order."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

from .config import get_settings

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def _say(msg: str) -> None:
    print(f"EA Explorer library: {msg}", flush=True)


def ensure_database() -> None:
    s = get_settings()
    if not s.db_password:
        raise SystemExit("EA Explorer library: EAX_LIBRARY_DB_PASSWORD is empty: set it in work/eaexplorer.env")
    if not s.superuser_password:
        _say("no superuser password: the database and its login must exist already")
        return
    for attempt in range(60):
        try:
            with psycopg.connect(s.dsn(user="postgres", password=s.superuser_password, db="postgres"), autocommit=True) as c:
                if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (s.db_user,)).fetchone():
                    c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(s.db_user), sql.Literal(s.db_password)))
                    _say(f"login {s.db_user} made")
                else:      # the password follows the config file
                    c.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(s.db_user), sql.Literal(s.db_password)))
                if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (s.db_name,)).fetchone():
                    c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(s.db_name), sql.Identifier(s.db_user)))
                    c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(s.db_name)))
                    _say(f"database {s.db_name} made")
            with psycopg.connect(s.dsn(user="postgres", password=s.superuser_password), autocommit=True) as c:
                c.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                c.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            return
        except psycopg.OperationalError as exc:
            _say(f"waiting for the database ({exc.__class__.__name__}), attempt {attempt + 1}")
            time.sleep(2)
    raise SystemExit("EA Explorer library: the database did not answer")


def migrate() -> list[str]:
    s = get_settings()
    done: list[str] = []
    with psycopg.connect(s.dsn(), autocommit=False) as c:
        have = c.execute("SELECT to_regclass('lib.schema_versions') IS NOT NULL").fetchone()[0]
        applied = {r[0] for r in c.execute("SELECT version FROM lib.schema_versions").fetchall()} if have else set()
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.stem in applied:
                continue
            c.execute(f.read_text(encoding="utf-8"))
            if f.stem != "0001_library":          # 0001 records itself (it makes the table)
                c.execute("INSERT INTO lib.schema_versions (version) VALUES (%s)", (f.stem,))
            done.append(f.stem)
        c.commit()
    return done


def main() -> int:
    ensure_database()
    done = migrate()
    _say(f"migrated: {', '.join(done)}" if done else "database up to date")
    # the running version's documents as a library folder (D550)
    from . import shipped_docs
    shipped_docs.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
