"""The test bench's state counts (GET /api/v1/admin/testbench/state, D582), kept out of the API module so they can be
tested without Flask."""

from __future__ import annotations

import time

from sqlalchemy import text

# the counts the upgrade test compares before and after (D582): fixed names, fixed read-only SQL, nothing from the caller
COUNTS = {"models": "core.models", "entities": "core.entities", "relationships": "core.relationships",
          "attribute values": "core.attribute_values", "drawn views": "views.drawn_views", "known users": "core.known_users",
          "audit events": "audit.events", "history rows": "history.row_versions"}


# The whole answer within STATE_BUDGET seconds, well inside a caller's minute (the full self-test, 13 Nov 2026: "GET
# /api/v1/admin/testbench/state: no answer" after 71 s: eight exact counts of up to 20 s each under the run's parallel
# calls). Each count gets what is left of the budget (at most COUNT_LIMIT); once it is spent, the rest are not counted
# (None, said in problems), which the upgrade test's comparison skips.
STATE_BUDGET = 30.0
COUNT_LIMIT = 10.0


def count_rows(engine, clock=time.monotonic, budget: float = STATE_BUDGET) -> tuple[dict, list[str]]:
    counts: dict[str, int | None] = {}
    problems: list[str] = []
    end = clock() + budget
    for name, table in COUNTS.items():
        left = min(COUNT_LIMIT, end - clock())
        if left < 1:
            counts[name] = None
            problems.append(f"{name}: not counted, the answer's {int(budget)} seconds were used up")
            continue
        # each count on its own connection: one that fails (a busy table under the self-test's parallel calls, a table
        # this role may not read) is reported, not a server error for the whole answer (R2.0.1)
        try:
            with engine.begin() as conn:
                ms = int(left * 1000)
                conn.execute(text(f"SET LOCAL statement_timeout = {ms}"))       # noqa: S608 - a number
                conn.execute(text(f"SET LOCAL lock_timeout = {ms}"))            # noqa: S608 - a number
                if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                    counts[name] = int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)  # noqa: S608 - fixed names
                else:
                    counts[name] = None
        except Exception as exc:  # noqa: BLE001
            counts[name] = None
            problems.append(f"{name}: {type(exc).__name__}")
    return counts, problems
