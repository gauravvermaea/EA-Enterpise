"""A self-test in progress keeps normal users out (R2.51, D609; owner, 12 Nov 2026: "when a test is in
progress normal users can not login, they get a banner on login environment test in progress. Admins can login and only
see test results"; then: block new sign-ins, a banner for those already in).

While a run is queued or running (and not left open too long, STALE_HOURS, so a broken run never keeps people out):
  * a normal person's changes are refused (423) with why; reading goes on (those already in see a banner);
  * the screens, from the heartbeat's test_in_progress, show a person signing in "Environment test in progress" and let
    them in when it ends; Super Admins and IT Admins sign in as usual and see only the Self-test page meanwhile;
  * the test's own accounts (svc-self-test-*) and machine credentials made by it are never affected.
State is the run's row (core.test_runs); nothing is kept anywhere else (D248)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

STALE_HOURS = 3
ADMIN_ROLES = ("super-admin", "it-admin")
TEST_ACCOUNT = "svc-self-test-"


def active(conn) -> dict[str, Any] | None:
    """The run in progress, if any: id, when it started, its step and how far it is (R2.40)."""
    row = conn.execute(text(f"""SELECT id, state, started_by, coalesce(started_at, queued_at) AS since, step, level, suites
                                  FROM core.test_runs WHERE state IN ('queued', 'running')
                                   AND queued_at > now() - interval '{STALE_HOURS} hours'
                                 ORDER BY id DESC LIMIT 1""")).mappings().first()
    if not row:
        return None
    done = conn.execute(text("SELECT count(*) FROM core.test_results WHERE run_id = :id"), {"id": row["id"]}).scalar() or 0
    return {"id": row["id"], "state": row["state"], "by": row["started_by"], "since": row["since"], "step": row["step"] or "",
            "level": row["level"], "done": int(done)}


def exempt(username: str, roles) -> bool:
    """Who the lock does not stop: Super Admins and IT Admins, and the test's own accounts."""
    return (username or "").startswith(TEST_ACCOUNT) or any(r in ADMIN_ROLES for r in (roles or ()))


def refusal(run: dict[str, Any]) -> dict[str, Any]:
    return {"message": f"An environment test is in progress (self-test {run['id']}, started {run['since']:%H:%M} by "
                       f"{run['by']}): changes wait until it ends. You can keep reading.",
            "test_in_progress": run}
