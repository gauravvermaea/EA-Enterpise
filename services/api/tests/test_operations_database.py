"""R2.27 (D614; owner, 12 Nov 2026, 21:45): the running of the installation (backup schedules, deployments, updates,
start-up status, health history) in the operations database (EAX_OPERATIONS_DB_URL); empty = the shared PostgreSQL and
the same connection as before. Checked on PostgreSQL on 13 Nov 2026 with a database of its own: its tables made (serial
counters included), the rows copied, the schedules read and changed there while the shared copy stayed as it was."""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "eax"
OPS = ("backup_schedules", "deployments", "update_history", "heartbeat_logs", "startup_parts")


def test_on_is_the_same_connection_when_shared(monkeypatch):
    from eax import databases as dbs
    monkeypatch.delenv("EAX_OPERATIONS_DB_URL", raising=False)
    conn = object()
    assert dbs.on("operations", conn) is conn
    monkeypatch.setenv("EAX_OPERATIONS_DB_URL", "postgresql://u:p@dbops:5432/eaxops")
    assert isinstance(dbs.on("operations", conn), dbs._Apart)
    assert dbs.TABLES["operations"][:len(OPS)] == tuple(f"operations.{t}" for t in OPS)   # then ssh_sessions (R2.2)


def test_every_statement_on_an_operations_table_goes_through_on():
    """No statement reaches an operations table but through databases.on("operations", ...)."""
    for f in sorted(API.rglob("*.py")):
        if f.name == "later.py":                       # its own connection, to the operations database (below)
            continue
        src = f.read_text()
        for m in re.finditer(r"\b(\w+)\.execute\(", src):
            seg = src[m.end(): src.find(".execute(", m.end()) if src.find(".execute(", m.end()) != -1 else len(src)][:900]
            if re.search(r"core\.(" + "|".join(OPS) + r")\b", seg) and m.group(1) != "self":
                head = src[max(0, m.start() - 40): m.start()]
                assert 'databases.on("operations", ' in head, (f.name, src[m.start(): m.start() + 80])
    later = (API / "seed" / "later.py").read_text()
    assert 'databases.BY_KEY["operations"]' in later                  # the start-up status' own connection


def test_serial_counters_are_made_before_their_table():
    from eax import databases as dbs

    class Q:
        def __init__(self, cols):
            self.cols = cols

        def execute(self, stmt, params=None):
            rows = self.cols.get((params or {}).get("t"), []) if "pg_attribute" in str(stmt) else []

            class R:
                def all(self_inner):
                    return rows
            return R()
    shared = Q({"core.h": [("id", "bigint", True, "nextval('core.h_id_seq'::regclass)", "")]})
    steps = dbs.plan(shared, Q({}), ("core.h",))
    assert steps[1] == "CREATE SEQUENCE IF NOT EXISTS core.h_id_seq"
    assert steps[2].startswith("CREATE TABLE core.h") and steps[3] == 'ALTER SEQUENCE core.h_id_seq OWNED BY core.h."id"'
