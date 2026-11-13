"""Self-test runs and their results (core.test_runs, core.test_results, core.test_fixtures; D522), in the tests
database (R2.28, D613): the shared PostgreSQL unless EAX_TESTS_DB_URL gives it one of its own (databases.py).

Code that reads or writes only these tables uses engine(); code that also touches the architecture (a fixture's model,
service account or credential) holds a repository connection and reaches the test tables through tests(conn), which is
that same connection when the tests database is the shared one (one transaction, as before), else its own.

The one results store for every way a run starts (System admin > Self-test, `eax test`, CI): the runner writes as it
goes, the API and the command line read it, MCP reads it (test_results). Plain rows: the runner decides outcomes (D248)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text

from . import SUITES


def engine():
    """The tests database's engine (the repository's when it has no setting of its own)."""
    from ..databases import engine_for
    return engine_for("tests")


def separate() -> bool:
    """Whether the tests database lives apart from the repository (EAX_TESTS_DB_URL set to another database)."""
    from ..databases import BY_KEY, own
    return own(BY_KEY["tests"])


@contextmanager
def tests(conn) -> Iterator[Any]:
    """The test tables beside a repository connection: conn itself when they share a database, else a transaction of
    the tests database (committed when the block ends)."""
    if not separate():
        yield conn
        return
    with engine().begin() as tc:
        yield tc


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
    add = {"api": (3, 10), "ui": (2, 5), "db": (0, 1), "security": (5, 15), "backup": (3, 15)}
    for s in suites:
        lo, hi = lo + add[s][0], hi + add[s][1]
    if watch:
        lo, hi = lo + 1, hi + 3
    return lo, hi


def create_run(conn, by: str, trigger: str, suites: list[str], folder: str = "", version: str = "", level: str = "smoke",
               role: str = "", area: str = "", watch: bool = False, journeys: list[str] | None = None,
               pages_only: bool = False, repeat_of: int | None = None, repeat_warnings: bool = False) -> int:
    return int(conn.execute(text("""
        INSERT INTO core.test_runs (started_by, trigger, suites, folder, version, level, role, area, watch, journeys, pages_only,
                                    repeat_of, repeat_warnings)
        VALUES (:by, :trigger, :suites, :folder, :version, :level, :role, :area, :watch, :journeys, :pages_only, :repeat_of,
                :repeat_warnings) RETURNING id"""),
        {"by": by or "unknown", "trigger": trigger, "suites": suites, "folder": folder, "version": version, "level": level,
         "role": role, "area": area, "watch": watch, "journeys": list(journeys or []), "pages_only": pages_only,
         "repeat_of": repeat_of or None, "repeat_warnings": bool(repeat_warnings)}).scalar())


def repeat_options(conn, of: int | None, with_warnings: bool = False) -> dict[str, Any]:
    """What a repeat of run `of` (None: the newest closed run) runs as (R2.36, D605): its level, role, area and the suites
    with something to repeat. ValueError when there is no such run, it is still going, or nothing failed in it."""
    from . import repeat
    of = of or repeat.latest(conn)
    if not of:
        raise ValueError("There is no finished self-test to repeat.")
    row = conn.execute(text("SELECT id, state, level, role, area, suites FROM core.test_runs WHERE id = :id"),
                       {"id": of}).mappings().first()
    if not row:
        raise ValueError(f"No self-test run {of}.")
    if row["state"] in OPEN:
        raise ValueError(f"Self-test {of} is still going: wait for it to finish.")
    rows = repeat.wanted(conn, of, with_warnings)
    if not rows:
        raise ValueError(f"Self-test {of} had no failed checks" + (" or warnings" if with_warnings else "") + ": nothing to repeat.")
    found = {r["suite"] for r in rows}
    suites = [s for s in SUITES if s in found] or [s for s in (row["suites"] or SUITES) if s in SUITES] or list(SUITES)
    if "smoke" in found or row["level"] == "smoke":
        level = "smoke"
    else:
        level = "detailed"
    return {"of": int(of), "level": level, "role": row["role"] or "", "area": row["area"] or "", "suites": suites,
            "checks": len(rows), "with_warnings": bool(with_warnings)}


def set_fixture_ids(conn, run_id: int, ids: dict[str, str]) -> None:
    """The ids the run's fixtures have (a repeat matches pages of the run's own model by them, R2.36)."""
    from .repeat import ID_KEYS
    conn.execute(text("UPDATE core.test_runs SET fixture_ids = CAST(:i AS jsonb) WHERE id = :id"),
                 {"i": json.dumps({k: str(v) for k, v in ids.items() if k in ID_KEYS and v}), "id": run_id})


def clean_journeys(journeys: list[str] | str | None) -> list[str]:
    """Browser journeys asked for by part of their names (D577); each must match one."""
    from . import ui_flows
    if isinstance(journeys, str):
        journeys = [j for j in journeys.split(",") if j.strip()]
    asked = [j.strip() for j in (journeys or []) if j and j.strip()][:20]
    names = [j["name"].lower() for j in ui_flows.JOURNEYS]
    bad = [j for j in asked if not any(j.lower() in n for n in names)]
    if bad:
        raise ValueError(f"No journey {', '.join(bad)}: choose from {', '.join(j['name'] for j in ui_flows.JOURNEYS)}.")
    return asked


def command_line(run: dict[str, Any], eax: str = ".\\eax") -> str:
    """The `eax test` command a run equals (shown on the Self-test page's History and the report, D578)."""
    bits = [eax, "test"]
    suites = list(run.get("suites") or [])
    journeys, pages_only = list(run.get("journeys") or []), bool(run.get("pages_only"))
    if run.get("repeat_of"):                      # a repeat of an earlier run's failed checks (R2.36)
        return " ".join(bits + ["failed", str(run["repeat_of"])] + (["--warnings"] if run.get("repeat_warnings") else []))
    if pages_only:
        bits.append("--pages-only")
    elif journeys:
        bits += [f'--journey "{j}"' if " " in j else f"--journey {j}" for j in journeys]
    elif run.get("level") == "detailed":
        bits.append("--detailed")
        if suites and set(suites) != set(SUITES):
            bits += [f"--suite {x}" for x in suites]
    else:
        bits.append("--smoke")
    if run.get("role"):
        bits.append(f"--role {run['role']}")
    if run.get("area"):
        bits.append(f"--area {run['area']}")
    return " ".join(bits) + ("   (journeys watched in a browser: from the Self-test page only)" if run.get("watch") else "")


def short(run_guid: str) -> str:
    """The run's short id: the first 12 characters of its guid (in every fixture's name)."""
    return str(run_guid).replace("-", "")[:12]


def add_fixture(conn, run_id: int, kind: str, ident: str, name: str) -> None:
    conn.execute(text("INSERT INTO core.test_fixtures (run_id, kind, ident, name) VALUES (:r, :k, :i, :n) "
                      "ON CONFLICT (kind, ident) DO NOTHING"), {"r": run_id, "k": kind, "i": str(ident), "n": name})


def fixtures(conn, run_id: int | None = None, include_purged: bool = False) -> list[dict[str, Any]]:
    """Every fixture of every run (or of one run): its run, kind, name, when made, and its size (entities for a model,
    models for a project). conn: a repository connection (the sizes); the fixtures come from the tests database."""
    with tests(conn) as tc:
        rows = [dict(r) for r in tc.execute(text(f"""
            SELECT f.id, f.run_id, r.run_guid::text AS run_guid, r.state AS run_state, f.kind, f.ident, f.name, f.created_at,
                   f.purged_at, f.purged_by
              FROM core.test_fixtures f JOIN core.test_runs r ON r.id = f.run_id
             WHERE (CAST(:run AS bigint) IS NULL OR f.run_id = :run) {"" if include_purged else "AND f.purged_at IS NULL"}
             ORDER BY f.run_id DESC, f.kind, f.name"""), {"run": run_id}).mappings().all()]
    guids = [r["ident"] for r in rows if r["kind"] == "model"]
    sizes: dict[str, tuple[int, int]] = {}
    if guids:
        for g, e, x in conn.execute(text("""
                SELECT m.guid::text, (SELECT count(*) FROM core.entities e WHERE e.model_id = m.id),
                       (SELECT count(*) FROM core.relationships x WHERE x.model_id = m.id)
                  FROM core.models m WHERE m.guid::text = ANY(:g)"""), {"g": guids}).all():
            sizes[g] = (int(e), int(x))
    for r in rows:
        r["entities"], r["relationships"] = (sizes.get(r["ident"], (0, 0)) if r["kind"] == "model" else (None, None))
    return rows


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


def progress(conn, run: dict[str, Any], done: int) -> dict[str, Any]:
    """How many checks are left, roughly (R2.40; owner, 12 Nov 2026: "please tell how many tests are left as well when
    in the screen"): a repeat has as many as it repeats; any other run as many as the newest finished run of the same
    level, suites, role and area had. None known: the first run of its kind."""
    if run.get("repeat_of"):
        total = conn.execute(text("SELECT count(DISTINCT (suite, name)) FROM core.test_results WHERE run_id = :id "
                                  "AND outcome = ANY(:o)"), {"id": run["repeat_of"],
                                  "o": ["failed", "warning"] if run.get("repeat_warnings") else ["failed"]}).scalar()
        how = f"the failed checks of run {run['repeat_of']}"
    else:
        row = conn.execute(text("""SELECT r.id, (SELECT count(*) FROM core.test_results x WHERE x.run_id = r.id) AS n
                                     FROM core.test_runs r
                                    WHERE r.id <> :id AND r.state IN ('passed', 'failed') AND r.level = :l AND r.repeat_of IS NULL
                                      AND r.suites = CAST(:s AS text[]) AND r.role = :ro AND r.area = :a
                                    ORDER BY r.id DESC LIMIT 1"""),
                           {"id": run["id"], "l": run.get("level") or "", "s": list(run.get("suites") or []),
                            "ro": run.get("role") or "", "a": run.get("area") or ""}).first()
        total = int(row[1]) if row and row[1] else None
        how = f"as many as run {row[0]} had" if total else ""
    if not total:
        return {"done": done, "total": None, "left": None, "how": "not known: the first run of its kind"}
    total = max(int(total), done)
    return {"done": done, "total": total, "left": total - done, "how": how,
            "percent": round(100 * done / total) if total else 100}


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
             "r.level, r.role, r.area, r.watch, r.journeys, r.pages_only, r.repeat_of, r.repeat_warnings, r.followed_up_by, r.stop_asked, r.message, r.purged_at, r.purged_by, r.queued_at, r.started_at, "
             "r.finished_at, (SELECT count(*) FROM core.test_fixtures f WHERE f.run_id = r.id AND f.purged_at IS NULL) AS fixtures, "
             + ", ".join(_LIVE.format(o=o, c=c) for o, c in (("= 'passed'", "passed"), ("= 'failed'", "failed"),
                                                             ("IN ('skipped', 'warning')", "skipped"))))


def runs(conn, limit: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(text(f"SELECT {_RUN_COLS} FROM core.test_runs r ORDER BY r.queued_at DESC, r.id DESC LIMIT :n"),
                        {"n": max(1, min(200, limit))}).mappings().all()
    return [{**dict(r), "command": command_line(dict(r))} for r in rows]


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
    from . import health
    every = [dict(r) for r in conn.execute(text("SELECT suite, name, outcome FROM core.test_results WHERE run_id = :id"),
                                          {"id": run_id}).mappings().all()]
    from . import repeat
    return {"run": run, "results": [dict(r) for r in results], "tally": tally(conn, run_id),
            "health": health.summary(every),                   # critical and non-critical, and the health (R2.35)
            "repeat": repeat.compare(conn, run_id),            # a repeat: each check then and now (R2.36)
            "progress": progress(conn, run, len(every)) if run["state"] in OPEN else None}   # checks left (R2.40)


def screenshot(conn, result_id: int) -> bytes | None:
    row = conn.execute(text("SELECT screenshot FROM core.test_results WHERE id = :id"), {"id": result_id}).first()
    return bytes(row[0]) if row and row[0] is not None else None


_re_choice = __import__("re").compile(r"^  (smoke|full|backup|failed|delete|clean)\s{2,}(.*)$")


def test_entry(help_text: str) -> dict:
    """The `test` entry of help.txt: its syntax line, its one-line summary, its options (flag and what it does) and its
    examples ({eax} left for the page to fill with .\\eax, ./eax.sh or eaxpy)."""
    lines = help_text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("### test ")), None)
    if start is None:
        return {"syntax": "", "summary": "", "options": [], "examples": []}
    out = {"syntax": lines[start][4:].strip(), "summary": "", "options": [], "examples": []}
    for ln in lines[start + 1:]:
        if ln.startswith("### ") or ln.startswith("## "):
            break
        if ln.startswith("> "):
            out["summary"] = ln[2:].strip()
        elif ln.startswith("$ "):
            out["examples"].append(ln[2:].strip())
        elif _re_choice.match(ln):           # the choices of `eax test` since R2.0.1 (smoke, full, clean; D592)
            m = _re_choice.match(ln)
            out["options"].append({"flag": m.group(1), "what": m.group(2).strip()})
        elif ln.startswith("  --"):
            import re as _re
            m = _re.match(r"^(--\S+(?:\s+(?:\[[^\]]*\]|<[^>]*>|[A-Z]\b|--\S+))*)(?:\s+(.*))?$", ln.strip())
            flag, what = (m.group(1), m.group(2) or "") if m else (ln.strip(), "")
            out["options"].append({"flag": flag.strip(), "what": what.strip()})
        elif ln.startswith("    ") and out["options"]:
            out["options"][-1]["what"] = (out["options"][-1]["what"] + " " + ln.strip()).strip()
    return out
