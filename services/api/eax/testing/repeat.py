"""Run the failed ones again (R2.36, D605; owner, 12 Nov 2026: "run last failed tests only").

A repeat is a new run of only the checks that failed in an earlier run (and those with warnings, if asked): the same
level, role and area, fresh fixtures and the clean-up of earlier test data first as always (D593). What it runs:

  api        the failed endpoint checks by name (api_matrix.run only=); the writes run in order up to the last failed
             one (a write needs what earlier ones made), and only the failed ones are recorded
  ui         the failed pages only (no crawl) and the failed journeys only, as the same roles
  db         every database check (read only, seconds); only the failed ones are recorded
  security   the headers, cookies and Python dependencies when one of them failed; ZAP when it failed; Trivy only for
             the images that failed (the operations helper reads scans.json in the run's folder)
  smoke      the failed smoke checks the same way

Result names that carry a fixture's id (a page of the run's own model) are compared with the ids replaced by what they
are ({model}, {project}, ...), so a page of the earlier run's model is the same check as that page of the new one.
When every repeated check passes, the earlier run is marked as followed up by the repeat. Plain rows (D248)."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text

CLOSED = ("passed", "failed", "error", "stopped")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_TRIVY = re.compile(r"^image (.+) \(Trivy\)$")
ZAP = "OWASP ZAP baseline scan"
SCANS = "scans.json"
ID_KEYS = ("model", "other_model", "project", "entity", "view", "sid")


def latest(conn) -> int | None:
    """The newest closed run (the one `eax test failed` repeats when no run is named)."""
    return conn.execute(text(f"SELECT id FROM tests.test_runs WHERE state IN {CLOSED} ORDER BY id DESC LIMIT 1")).scalar()


def outcomes(with_warnings: bool) -> tuple[str, ...]:
    return ("failed", "warning") if with_warnings else ("failed",)


def wanted(conn, run_id: int, with_warnings: bool = False) -> list[dict[str, Any]]:
    """The checks to repeat: the run's failed results (and warnings), one per suite and name."""
    rows = conn.execute(text("""SELECT DISTINCT ON (suite, name) suite, name, outcome FROM tests.test_results
                                 WHERE run_id = :id AND outcome = ANY(:o) ORDER BY suite, name, id"""),
                        {"id": run_id, "o": list(outcomes(with_warnings))}).mappings().all()
    return [dict(r) for r in rows]


def fixture_ids(conn, run_id: int) -> dict[str, str]:
    """The ids a run made (kept with the run since R2.36), else what tests.test_fixtures says of its models and project."""
    got = conn.execute(text("SELECT fixture_ids FROM tests.test_runs WHERE id = :id"), {"id": run_id}).scalar() or {}
    if isinstance(got, str):
        got = json.loads(got or "{}")
    if got:
        return {k: str(v) for k, v in got.items() if k in ID_KEYS and v}
    out: dict[str, str] = {}
    for _kind, ident, name in conn.execute(text("SELECT kind, ident, name FROM tests.test_fixtures WHERE run_id = :id "
                                               "AND kind IN ('model', 'project')"), {"id": run_id}).all():
        key = {"_1": "model", "_2": "other_model", "_3": "project"}.get(str(name)[-2:])
        if key:
            out[key] = str(ident)
        m = re.match(r"self_test_([0-9a-f]{12})_", str(name))
        if m:
            out["sid"] = m.group(1)
    return out


def canon(name: str, ids: dict[str, str]) -> str:
    """A result's name with the run's own ids put as what they are: the same check in two runs has the same canon."""
    by = {str(v).lower(): k for k, v in ids.items() if k in ID_KEYS and v and k != "sid"}
    out = _UUID.sub(lambda m: "{" + by.get(m.group(0).lower(), "id") + "}", name)
    sid = ids.get("sid")
    return out.replace(sid, "{sid}") if sid else out


def fill(name: str, ids: dict[str, str]) -> str | None:
    """canon() back again with another run's ids; None when it names an id the new run has not got."""
    out = name
    for key in re.findall(r"\{(\w+)\}", name):
        if key == "id" or not ids.get(key):
            return None
        out = out.replace("{" + key + "}", str(ids[key]))
    return out


def plan(rows: list[dict[str, Any]], old_ids: dict[str, str]) -> dict[str, Any]:
    """What to run for these checks: suites, names (canon) to record, API checks, writes, page routes (canon),
    journeys, and which scans."""
    keys = {(r["suite"], canon(r["name"], old_ids)) for r in rows}
    out: dict[str, Any] = {"keys": keys, "suites": sorted({s for s, _ in keys}), "api": set(), "writes": set(),
                           "routes": [], "journeys": set(), "db": False, "front_door": False, "zap": False, "images": []}
    for suite, name in sorted(keys):
        if suite == "api" and name.startswith("write ") and ": " in name:
            out["writes"].add(name)
        elif name.startswith("page: "):
            out["routes"].append(name[6:])
        elif name.startswith("journey: "):
            out["journeys"].add(name)
        elif suite == "db":
            out["db"] = True
        elif suite == "security":
            if name == ZAP:
                out["zap"] = True
            elif _TRIVY.match(name):
                out["images"].append(_TRIVY.match(name).group(1))
            elif name == "image and dependency scans (Trivy)":
                out["images"].append("*")
            else:
                out["front_door"] = True
        elif suite == "api" or suite == "smoke":
            out["api"].add(name)
    return out


def scans(p: dict[str, Any]) -> dict[str, Any]:
    """scans.json for the operations helper: whether ZAP runs and which images Trivy scans ("*": every one)."""
    return {"zap": bool(p["zap"]), "images": sorted(set(p["images"]))}


def then_and_now(earlier: list[dict[str, Any]], old_ids: dict[str, str], results: list[tuple[str, str, str]],
                 new_ids: dict[str, str]) -> list[dict[str, Any]]:
    """Each repeated check (earlier: the run's failed results) beside its outcome in the repeat (results: suite, name,
    outcome); "not repeated" when the repeat has none for it."""
    now: dict[tuple[str, str], str] = {}
    for suite, name, outcome in results:
        k = (suite, canon(name, new_ids))
        if now.get(k) != "failed":                   # the worst of several (a page opened twice)
            now[k] = outcome
    return [{"suite": r["suite"], "name": r["name"], "then": r["outcome"],
             "now": now.get((r["suite"], canon(r["name"], old_ids)), "not repeated")} for r in earlier]


def compare(conn, run_id: int) -> dict[str, Any] | None:
    """A repeat beside the run it repeats: each repeated check's outcome then and now ("not repeated" when the new run
    has no result for it: a fixture it could not make, or a check that no longer exists)."""
    row = conn.execute(text("SELECT repeat_of, repeat_warnings FROM tests.test_runs WHERE id = :id"), {"id": run_id}).first()
    if not row or not row[0]:
        return None
    of, warn = int(row[0]), bool(row[1])
    results = [tuple(x) for x in conn.execute(text("SELECT suite, name, outcome FROM tests.test_results WHERE run_id = :id "
                                                   "ORDER BY id"), {"id": run_id}).all()]
    checks = then_and_now(wanted(conn, of, warn), fixture_ids(conn, of), results, fixture_ids(conn, run_id))
    fixed = sum(1 for c in checks if c["now"] == "passed")
    return {"of": of, "with_warnings": warn, "checks": checks, "fixed": fixed, "still": len(checks) - fixed,
            "all_passed": bool(checks) and fixed == len(checks)}


def mark_followed_up(conn, run_id: int) -> bool:
    """When every repeated check passes, the earlier run is followed up by this one (shown in History)."""
    c = compare(conn, run_id)
    if not c or not c["all_passed"]:
        return False
    conn.execute(text("UPDATE tests.test_runs SET followed_up_by = :r WHERE id = :of"), {"r": run_id, "of": c["of"]})
    return True
