"""Self-test runs and their results in the installation's own database (core.test_runs, core.test_results; D522).

The one results store for every way a run starts (System admin > Self-test, `eax test`, CI): the runner writes as it
goes, the API and the command line read it, MCP reads it (test_results). Plain rows: the runner decides outcomes (D248)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from . import SUITES

STATES = ("queued", "running", "passed", "failed", "error", "stopped")
OUTCOMES = ("passed", "failed", "skipped", "warning")
OPEN = ("queued", "running")


def clean_suites(suites: list[str] | str | None) -> list[str]:
    """The suites asked for, in the usual order; empty or 'all' means every suite."""
    if isinstance(suites, str):
        suites = [s for s in suites.replace(",", " ").split() if s]
    asked = [s.strip().lower() for s in (suites or []) if s and s.strip()]
    if not asked or "all" in asked:
        return list(SUITES)
    bad = [s for s in asked if s not in SUITES]
    if bad:
        raise ValueError(f"Unknown suite {', '.join(bad)}: choose from {', '.join(SUITES)} (or all).")
    return [s for s in SUITES if s in asked]


# the roles a run tests, each a service account of the run (svc-self-test-<guid>-<role>): global roles, the model roles
# (on the run's first model), and someone with no role at all (D529)
GLOBAL_TEST_ROLES = ["super-admin", "it-admin", "model-creator", "library-admin"]
MODEL_TEST_ROLES = ["model-admin", "model-sub-admin", "committer", "architect", "history-viewer", "report-viewer"]
NO_ROLE = "no-role"
TEST_ROLES = GLOBAL_TEST_ROLES + MODEL_TEST_ROLES + [NO_ROLE]


def clean_options(level: str = "smoke", role: str = "", area: str = "") -> tuple[str, str, str]:
    """smoke or detailed; one role (TEST_ROLES) or every role; one API area or all."""
    from ..machine_access import AREA_CODES
    level = (level or "smoke").lower()
    if level not in ("smoke", "detailed"):
        raise ValueError("level is smoke or detailed.")
    role = (role or "").strip().lower().removeprefix("user_").replace("_", "-")
    if role and role not in TEST_ROLES:
        raise ValueError(f"No test role {role}: choose from {', '.join(TEST_ROLES)}.")
    area = (area or "").strip().lower()
    if area and area not in AREA_CODES:
        raise ValueError(f"No API area {area}: choose from {', '.join(AREA_CODES)}.")
    return level, role, area


def estimate_minutes(level: str, suites: list[str], watch: bool = False) -> tuple[int, int]:
    """How long a run takes, roughly (minutes, from and to)."""
    if level == "smoke":
        return (2, 5)
    lo, hi = 1, 2                                                   # its fixtures: models, a project, accounts
    add = {"api": (3, 10), "ui": (2, 5), "db": (0, 1), "security": (5, 15)}
    for s in suites:
        lo, hi = lo + add[s][0], hi + add[s][1]
    if watch:
        lo, hi = lo + 1, hi + 3
    return lo, hi


def create_run(conn, by: str, trigger: str, suites: list[str], folder: str = "", version: str = "", level: str = "smoke",
               role: str = "", area: str = "", watch: bool = False) -> int:
    return int(conn.execute(text("""
        INSERT INTO core.test_runs (started_by, trigger, suites, folder, version, level, role, area, watch)
        VALUES (:by, :trigger, :suites, :folder, :version, :level, :role, :area, :watch) RETURNING id"""),
        {"by": by or "unknown", "trigger": trigger, "suites": suites, "folder": folder, "version": version, "level": level,
         "role": role, "area": area, "watch": watch}).scalar())


def short(run_guid: str) -> str:
    """The run's short id: the first 12 characters of its guid (in every fixture's name)."""
    return str(run_guid).replace("-", "")[:12]


def add_fixture(conn, run_id: int, kind: str, ident: str, name: str) -> None:
    conn.execute(text("INSERT INTO core.test_fixtures (run_id, kind, ident, name) VALUES (:r, :k, :i, :n) "
                      "ON CONFLICT (kind, ident) DO NOTHING"), {"r": run_id, "k": kind, "i": str(ident), "n": name})


def fixtures(conn, run_id: int | None = None, include_purged: bool = False) -> list[dict[str, Any]]:
    """Every fixture of every run (or of one run): its run, kind, name, when made, and its size (entities for a model,
    models for a project)."""
    rows = conn.execute(text(f"""
        SELECT f.id, f.run_id, r.run_guid::text AS run_guid, r.state AS run_state, f.kind, f.ident, f.name, f.created_at,
               f.purged_at, f.purged_by,
               CASE f.kind WHEN 'model' THEN (SELECT count(*) FROM core.entities e JOIN core.models m ON m.id = e.model_id
                                               WHERE m.guid::text = f.ident) END AS entities,
               CASE f.kind WHEN 'model' THEN (SELECT count(*) FROM core.relationships x JOIN core.models m ON m.id = x.model_id
                                               WHERE m.guid::text = f.ident) END AS relationships
          FROM core.test_fixtures f JOIN core.test_runs r ON r.id = f.run_id
         WHERE (CAST(:run AS bigint) IS NULL OR f.run_id = :run) {"" if include_purged else "AND f.purged_at IS NULL"}
         ORDER BY f.run_id DESC, f.kind, f.name"""), {"run": run_id}).mappings().all()
    return [dict(r) for r in rows]


def set_state(conn, run_id: int, state: str | None = None, step: str | None = None, message: str | None = None,
              folder: str | None = None, version: str | None = None) -> None:
    sets, params = [], {"id": run_id}
    if state is not None:
        if state not in STATES:
            raise ValueError(state)
        sets.append("state = :state")
        params["state"] = state
        if state == "running":
            sets.append("started_at = COALESCE(started_at, now())")
        if state in ("passed", "failed", "error", "stopped"):
            sets.append("finished_at = now()")
    for key, value in (("step", step), ("message", message), ("folder", folder), ("version", version)):
        if value is not None:
            sets.append(f"{key} = :{key}")
            params[key] = value[:2000] if key == "message" else value
    if sets:
        conn.execute(text(f"UPDATE core.test_runs SET {', '.join(sets)} WHERE id = :id"), params)


def set_browser(conn, run_id: int, data: dict) -> None:
    conn.execute(text("UPDATE core.test_runs SET browser = browser || CAST(:b AS jsonb) WHERE id = :id"),
                 {"b": json.dumps(data), "id": run_id})


def ask_stop(conn, run_id: int, by: str) -> bool:
    return bool(conn.execute(text("UPDATE core.test_runs SET stop_asked = :by WHERE id = :id AND state IN ('queued', 'running') "
                                  "RETURNING id"), {"by": by or "unknown", "id": run_id}).first())


def add_result(conn, run_id: int, suite: str, name: str, outcome: str, detail: str = "", duration_ms: int = 0,
               screenshot: bytes | None = None, video: str = "", request: str = "", response: str = "",
               browser: str = "") -> None:
    if outcome not in OUTCOMES:
        raise ValueError(outcome)
    conn.execute(text("""
        INSERT INTO core.test_results (run_id, suite, name, outcome, detail, duration_ms, screenshot, video, request, response,
                                       browser)
        VALUES (:run, :suite, :name, :outcome, :detail, :ms, :shot, :video, :req, :resp, :browser)"""),
        {"run": run_id, "suite": suite, "name": name[:400], "outcome": outcome, "detail": (detail or "")[:20000],
         "ms": int(duration_ms), "shot": screenshot, "video": video, "req": (request or "")[:4000],
         "resp": (response or "")[:8000], "browser": (browser or "")[:200]})


def tally(conn, run_id: int) -> dict[str, int]:
    rows = conn.execute(text("SELECT outcome, count(*) AS n FROM core.test_results WHERE run_id = :id GROUP BY outcome"),
                        {"id": run_id}).mappings().all()
    out = {o: 0 for o in OUTCOMES}
    out.update({r["outcome"]: int(r["n"]) for r in rows})
    return out


def finish(conn, run_id: int, error: str = "", stopped: str = "") -> str:
    """Counts the results and closes the run: stopped when someone stopped it, error when the run itself broke, failed
    when any check failed, else passed."""
    t = tally(conn, run_id)
    state = "stopped" if stopped else "error" if error else ("failed" if t["failed"] else "passed")
    counts = f"{t['passed']} passed, {t['failed']} failed, {t['skipped']} skipped, {t['warning']} warnings"
    msg = f"Stopped by {stopped}: {counts} before it stopped" if stopped else error[:2000] if error else counts
    conn.execute(text("""UPDATE core.test_runs SET passed = :p, failed = :f, skipped = :s, state = :state, step = '',
                         message = :msg, finished_at = now() WHERE id = :id"""),
                 {"p": t["passed"], "f": t["failed"], "s": t["skipped"] + t["warning"], "state": state, "msg": msg, "id": run_id})
    return state


_LIVE = "CASE WHEN r.state IN ('queued', 'running') THEN (SELECT count(*) FROM core.test_results x WHERE x.run_id = r.id AND x.outcome {o}) ELSE r.{c} END AS {c}"
_RUN_COLS = ("r.id, r.run_guid::text AS run_guid, r.started_by, r.trigger, r.suites, r.state, r.step, r.folder, r.version, "
             "r.level, r.role, r.area, r.watch, r.stop_asked, r.message, r.purged_at, r.purged_by, r.queued_at, r.started_at, "
             "r.finished_at, (SELECT count(*) FROM core.test_fixtures f WHERE f.run_id = r.id AND f.purged_at IS NULL) AS fixtures, "
             + ", ".join(_LIVE.format(o=o, c=c) for o, c in (("= 'passed'", "passed"), ("= 'failed'", "failed"),
                                                             ("IN ('skipped', 'warning')", "skipped"))))


def runs(conn, limit: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(text(f"SELECT {_RUN_COLS} FROM core.test_runs r ORDER BY r.queued_at DESC, r.id DESC LIMIT :n"),
                        {"n": max(1, min(200, limit))}).mappings().all()
    return [dict(r) for r in rows]


def run_row(conn, run_id: int) -> dict[str, Any] | None:
    row = conn.execute(text(f"SELECT {_RUN_COLS}, r.browser FROM core.test_runs r WHERE r.id = :id"), {"id": run_id}).mappings().first()
    return dict(row) if row else None


def run_detail(conn, run_id: int, outcome: str = "", suite: str = "") -> dict[str, Any] | None:
    run = run_row(conn, run_id)
    if not run:
        return None
    run.pop("browser", None)
    where, params = ["run_id = :id"], {"id": run_id}
    if outcome:
        where.append("outcome = :outcome")
        params["outcome"] = outcome
    if suite:
        where.append("suite = :suite")
        params["suite"] = suite
    results = conn.execute(text(f"""
        SELECT id, suite, name, outcome, detail, duration_ms, (screenshot IS NOT NULL) AS has_screenshot, video, request,
               response, browser, recorded_at
          FROM core.test_results WHERE {' AND '.join(where)}
         ORDER BY CASE outcome WHEN 'failed' THEN 0 WHEN 'warning' THEN 1 WHEN 'skipped' THEN 2 ELSE 3 END, suite, id"""),
        params).mappings().all()
    return {"run": run, "results": [dict(r) for r in results], "tally": tally(conn, run_id)}


def screenshot(conn, result_id: int) -> bytes | None:
    row = conn.execute(text("SELECT screenshot FROM core.test_results WHERE id = :id"), {"id": result_id}).first()
    return bytes(row[0]) if row and row[0] is not None else None
