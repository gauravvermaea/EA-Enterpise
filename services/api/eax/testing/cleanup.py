"""Deleting test results (R2.43; owner, 12 Nov 2026: "delete test logs both on web and UI so that all the captured
images, logs videos all are deleted. Otherwise this will take a lot of space").

Deleting a run removes, for good: its test data first (its fixtures, fixtures.purge), then its results with their
screenshots (rows in core.test_results), its fixture records and its run row, and its folder in work/tests (the report,
the log, the videos and screenshots; the operations helper removes it, as only it may write there). A run still going
cannot be deleted. Old runs go by themselves after the days set on the Self-test page (persist/settings.json,
testrunner_keep_days, default 30; 0 keeps them), once a day."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from . import fixtures as fx
from . import store

DEFAULT_KEEP_DAYS = 30


def pick(conn, which: str = "", older_than_days: int | None = None) -> list[dict[str, Any]]:
    """The finished runs asked for: one id, "all", or those that ended more than N days ago."""
    where, params = ["state NOT IN ('queued', 'running')"], {}
    if which and which != "all":
        if not str(which).isdigit():
            raise ValueError("Give a run's number, all, or --older-than DAYS.")
        where.append("id = :id")
        params["id"] = int(which)
    if older_than_days is not None:
        if int(older_than_days) < 1:
            raise ValueError("--older-than takes a number of days, 1 or more.")
        where.append(f"coalesce(finished_at, queued_at) < now() - make_interval(days => {int(older_than_days)})")
    if not which and older_than_days is None:
        raise ValueError("Give a run's number, all, or --older-than DAYS.")
    return [dict(r) for r in conn.execute(text(f"SELECT id, folder, state FROM core.test_runs WHERE {' AND '.join(where)} "
                                               "ORDER BY id"), params).mappings()]


def delete(engine, ids: list[int], by: str, remove_folders, say=lambda _m: None) -> dict[str, Any]:
    """Deletes these runs for good (see the module). remove_folders(list of folder names) deletes their folders and
    says which it could not. Returns the counts."""
    out = {"runs": 0, "results": 0, "fixtures": 0, "folders": [], "left": [], "notes": []}
    folders = []
    for run_id in ids:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT id, folder, state FROM core.test_runs WHERE id = :id"), {"id": run_id}).mappings().first()
            if not row:
                continue
            if row["state"] in store.OPEN:
                out["notes"].append(f"run {run_id} is still going: not deleted")
                continue
            purged = fx.purge(conn, run_id, by)
            out["fixtures"] += purged["models"] + purged["projects"] + purged["service_accounts"] + purged["credentials"]
            out["results"] += conn.execute(text("DELETE FROM core.test_results WHERE run_id = :id"), {"id": run_id}).rowcount
            conn.execute(text("DELETE FROM core.test_fixtures WHERE run_id = :id"), {"id": run_id})
            conn.execute(text("DELETE FROM core.test_runs WHERE id = :id"), {"id": run_id})
            out["runs"] += 1
            if row["folder"]:
                folders.append(row["folder"])
        say(f"run {run_id}: deleted")
    if folders:
        done = remove_folders(folders)
        out["folders"] = done.get("removed", [])
        out["left"] = done.get("left", [])
    return out


def message(out: dict[str, Any]) -> str:
    return (f"Deleted {out['runs']} run(s): {out['results']} results with their screenshots, {out['fixtures']} test fixture(s), "
            f"{len(out['folders'])} folder(s) of reports, logs and videos"
            + (f"; could not remove {', '.join(out['left'])} (delete them in work/tests)" if out["left"] else "")
            + (f"; {'; '.join(out['notes'])}" if out["notes"] else "") + ".")
