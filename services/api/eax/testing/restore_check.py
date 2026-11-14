"""The full backup-and-restore test (R3.8; owner, 13 Nov 2026: "test backup and restore properly and completely in an
automated manner from command line ... We will have the app, then we start it, call some APIs, create docs etc, then we
back it up, add more changes to environment, then restore. Check all the content"; decided: on the installation in use,
no time limit; and 16:31: "full test should also test backup and restores when run from command line").

The suite "restore", the very last of a run, from the command line only (`eax test restore`, and `eax test full` from the
command line); from the web it is skipped with the reason, as restores stop the services the web runs on.

  1. the content: the run's own models (with their entities, relationships and attribute values, made through the API
     at the start of the run) and project, fingerprinted: counts and a checksum per model and per project
  2. an infrastructure backup (it is also the safety backup) and an application backup of the run's models
  3. for each restore: the content changed first (names changed, a relationship removed, a project renamed), then
     restored, and the fingerprint compared with the one taken before the backup: what was there comes back exactly,
     the changes are gone
       - every model of the application backup put back over itself (restore all)
       - the run's first model put back over itself, and restored as a new model
       - the infrastructure backup: each part the installation offers (db, app+data, files, full), the API waited
         for after each, people can sign in again
  4. the backups the test made (and the ones a restore takes first) removed; when a step failed, the safety backup is
     put back whole so the installation is as it was

An infrastructure restore puts the database back as it was at the backup, which holds this run's own record: so the
suite keeps its results in memory and records them after the last restore."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

from sqlalchemy import text

from .api_writes import call
from .backups_check import wait_task

SUITE = "restore"
CLI_ONLY = "from the command line only (eax test restore, or eax test full from the command line): restores stop the services the web runs on"


# ---------------------------------------------------------------- the fingerprint
def _digest(rows) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(("\x1f".join("" if v is None else str(v) for v in r) + "\x1e").encode("utf-8"))
    return h.hexdigest()[:16]


def fingerprint(engine, models: list[str], projects: list[str]) -> dict:
    """{model guid: {entities, relationships, attributes, sum}, "project:<guid>": {...}}: the content compared after
    each restore. Ids change when a model is made again, so the checksum is over guids, names and values only."""
    out: dict[str, dict] = {}
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
        for g in models:
            m = conn.execute(text("SELECT id, name FROM core.models WHERE guid = CAST(:g AS uuid) AND NOT is_deleted"),
                             {"g": g}).first()
            if not m:
                out[g] = {"missing": True}
                continue
            ents = conn.execute(text("""SELECT e.guid::text, e.name, coalesce(e.description, '') FROM core.entities e
                                         WHERE e.model_id = :m AND NOT e.is_deleted ORDER BY e.guid"""), {"m": m[0]}).all()
            rels = conn.execute(text("""SELECT r.guid::text, s.guid::text, t.guid::text, coalesce(r.name, '')
                                          FROM core.relationships r JOIN core.entities s ON s.id = r.source_entity_id
                                          JOIN core.entities t ON t.id = r.target_entity_id
                                         WHERE r.model_id = :m AND NOT r.is_deleted ORDER BY r.guid"""), {"m": m[0]}).all()
            vals = conn.execute(text("""SELECT v.guid::text, v.value_text, v.value_number, v.value_date, v.value_bool
                                          FROM core.attribute_values v WHERE v.model_id = :m AND NOT v.is_deleted
                                         ORDER BY v.guid"""), {"m": m[0]}).all()
            out[g] = {"name": m[1], "entities": len(ents), "relationships": len(rels), "attributes": len(vals),
                      "sum": _digest([("m", m[1]), *ents, *rels, *vals])}
        for p in projects:
            try:
                row = conn.execute(text("SELECT id, name FROM proj.projects WHERE guid = CAST(:g AS uuid)"), {"g": p}).first()
            except Exception:  # noqa: BLE001 - the projects in a database of their own (R2.50): not fingerprinted here
                out[f"project:{p}"] = {"skipped": "the projects are in a database of their own"}
                continue
            if not row:
                out[f"project:{p}"] = {"missing": True}
                continue
            steps = conn.execute(text("SELECT phase, seq, name, coalesce(done_note, '') FROM proj.steps WHERE project_id = :p "
                                      "AND NOT removed ORDER BY phase, seq, name"), {"p": row[0]}).all()
            items = conn.execute(text("SELECT phase, name, kind FROM proj.items WHERE project_id = :p ORDER BY phase, name, kind"),
                                 {"p": row[0]}).all()
            people = conn.execute(text("SELECT lower(username), role FROM proj.members WHERE project_id = :p ORDER BY 1, 2"),
                                  {"p": row[0]}).all()
            out[f"project:{p}"] = {"name": row[1], "steps": len(steps), "items": len(items), "members": len(people),
                                   "sum": _digest([("p", row[1]), *steps, *items, *people])}
    return out


def compare(before: dict, after: dict) -> list[str]:
    """What differs, in words (empty: the same)."""
    diffs = []
    for key, b in before.items():
        a = after.get(key) or {"missing": True}
        if b.get("skipped"):
            continue
        if a.get("missing") and not b.get("missing"):
            diffs.append(f"{b.get('name') or key} is missing")
            continue
        for k in ("name", "entities", "relationships", "attributes", "steps", "items", "members"):
            if k in b and a.get(k) != b.get(k):
                diffs.append(f"{b.get('name') or key}: {k} {b.get(k)} before, {a.get(k)} after")
        if b.get("sum") != a.get("sum") and not any(d.startswith(f"{b.get('name') or key}:") for d in diffs):
            diffs.append(f"{b.get('name') or key}: the content differs (same counts)")
    return diffs


def change(engine, models: list[str], projects: list[str], mark: str) -> int:
    """Changes made between the backup and a restore: entity names changed, one relationship removed, the project
    renamed. Rows only, through the database (the restore must undo whatever way content changed). Returns the rows."""
    n = 0
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
        for g in models:
            n += conn.execute(text("""UPDATE core.entities SET name = name || :mark WHERE id IN (
                                         SELECT e.id FROM core.entities e JOIN core.models m ON m.id = e.model_id
                                          WHERE m.guid = CAST(:g AS uuid) AND NOT e.is_deleted ORDER BY e.id LIMIT 3)"""),
                              {"g": g, "mark": mark}).rowcount or 0
            n += conn.execute(text("""UPDATE core.relationships SET is_deleted = true WHERE id IN (
                                         SELECT r.id FROM core.relationships r JOIN core.models m ON m.id = r.model_id
                                          WHERE m.guid = CAST(:g AS uuid) AND NOT r.is_deleted ORDER BY r.id LIMIT 1)"""),
                              {"g": g}).rowcount or 0
        for p in projects:
            try:
                n += conn.execute(text("UPDATE proj.projects SET name = name || :mark WHERE guid = CAST(:g AS uuid)"),
                                  {"g": p, "mark": mark}).rowcount or 0
            except Exception:  # noqa: BLE001 - projects elsewhere: their change is left out
                pass
    return n


# ---------------------------------------------------------------- the suite
class Buffer:
    """The suite's results, kept until the last restore (which puts back the run's own record as it was)."""

    def __init__(self):
        self.rows: list[tuple] = []
        self.tally = {"passed": 0, "failed": 0}

    def rec(self, name: str, ok: bool, detail: str = "", ms: int = 0) -> None:
        self.tally["passed" if ok else "failed"] += 1
        self.rows.append((f"restore: {name}", "passed" if ok else "failed", detail, ms))

    def flush(self, record: Callable[..., None]) -> None:
        for name, outcome, detail, ms in self.rows:
            record(name, outcome, detail, ms)


def wait_api(base: str, seconds: int = 1800, call=call, sleep=time.sleep) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        code, _ = call(base, "GET", "/api/health", None)
        if code == 200:
            return True
        sleep(5)
    return False


def wait_restore(base: str, token: str, seconds: int = 7200, call=call, sleep=time.sleep) -> dict:
    """Follows an infrastructure restore in the operations helper until it is no longer busy; its last state. The API may
    be away while the database is put back: those answers are waited through."""
    end, last = time.time() + seconds, {}
    sleep(5)
    while time.time() < end:
        code, body = call(base, "GET", "/api/v1/admin/backups/restore", token)
        if code == 200 and isinstance(body, dict):
            last = body
            if not body.get("busy"):
                return body
        sleep(10)
    return {**last, "error": f"not finished after {seconds // 60} minutes"}


def run(base: str, token: str, ids: dict[str, str], record: Callable[..., None], log: Callable[[str], None], engine,
        run_id: int, trigger: str, call=call, sleep=time.sleep) -> dict[str, int]:
    """The suite (see the module). token: a Super Admin's. Returns passed and failed counts (recorded at the end)."""
    buf = Buffer()
    if trigger not in ("eax", "ci"):
        record("restore: the full backup and restore test", "skipped", CLI_ONLY, 0)
        return buf.tally
    models = [g for g in (ids.get("model"), ids.get("other_model")) if g]
    projects = [g for g in (ids.get("project_guid") or ids.get("project"),) if g]
    tag = f"self-test-{run_id}-restore"
    started = time.time()

    def say(msg: str) -> None:
        try:
            log(msg)
        except Exception:  # noqa: BLE001 - the database may be away while a restore runs
            print(msg, flush=True)

    def task(path: str, body: dict, minutes: int) -> tuple[bool, dict, int]:
        t0 = time.time()
        code, b = call(base, "POST", path, token, body)
        if code not in (200, 202) or not isinstance(b, dict):
            return False, {"message": f"HTTP {code}: {str(b)[:300]}"}, int((time.time() - t0) * 1000)
        t = wait_task(base, token, b, minutes * 60, call=call)
        return t.get("status") == "done", t, int((time.time() - t0) * 1000)

    before = fingerprint(engine, models, projects)
    buf.rec("the content fingerprinted before the backup", bool(models),
            "; ".join(f"{v.get('name')}: {v.get('entities', v.get('steps', 0))} {'entities' if 'entities' in v else 'steps'}"
                      for v in before.values() if v.get("name")) or "no model in the run's test data")
    if not models:
        buf.flush(record)
        return buf.tally

    # 2: the backups
    say("restore: an infrastructure backup (also the safety backup) and an application backup")
    ok, t, ms = task("/api/v1/admin/backups/infrastructure", {"tag": tag}, 240)
    infra = (t.get("result") or {}).get("name") if ok else ""
    buf.rec("an infrastructure backup (the safety backup too)", bool(infra), t.get("message") or t.get("status") or "", ms)
    ok, t, ms = task("/api/v1/admin/backups/application", {"tag": tag, "models": models}, 60)
    app = (t.get("result") or {}).get("name") if ok else ""
    buf.rec("an application backup of the run's models", bool(app), t.get("message") or t.get("status") or "", ms)

    def check(name: str, ms: int) -> bool:
        diffs = compare(before, fingerprint(engine, models, projects))
        buf.rec(f"{name}: the content is as before the backup", not diffs, "; ".join(diffs[:8]) or "the same", ms)
        return not diffs

    healthy = True
    # 3a: application restores
    if app:
        change(engine, models, [], " (changed)")
        say("restore: every model of the application backup put back over itself")
        ok, t, ms = task(f"/api/v1/admin/backups/application/{app}/restore-all", {"confirm": "RESTORE"}, 120)
        buf.rec("restore all from the application backup", ok, t.get("message") or t.get("status") or "", ms)
        healthy &= ok and check("after restore all", ms)

        code, b = call(base, "GET", "/api/v1/admin/backups", token)
        runs = ((b.get("application") or {}).get("runs") or []) if isinstance(b, dict) else []
        mine = next((r for r in runs if r.get("name") == app), {})
        file = next((m.get("file") for m in mine.get("models") or [] if m.get("id") == models[0] or m.get("file")), "")
        if file:
            change(engine, models[:1], [], " (changed again)")
            say("restore: the first model put back over itself")
            ok, t, ms = task("/api/v1/admin/backups/restore-model",
                             {"where": "application", "name": app, "file": file, "mode": "over", "model": models[0],
                              "confirm": before[models[0]].get("name", "")}, 60)
            buf.rec("one model put back over itself", ok, t.get("message") or t.get("status") or "", ms)
            healthy &= ok and check("after one model over itself", ms)

    # 3b: infrastructure restores, part by part
    if infra:
        code, b = call(base, "GET", "/api/v1/admin/backups", token)
        choices = list((((b or {}).get("infrastructure") or {}).get("restore_choices") or {}).keys()) \
            if isinstance(b, dict) else []
        for what in [w for w in ("db", "app+data", "files", "full") if w in choices] or ["full"]:
            database = what in ("db", "app+data", "full")
            if database:
                change(engine, models, projects, f" (changed before {what})")
            say(f"restore: the infrastructure backup, {what}")
            t0 = time.time()
            code, _ = call(base, "POST", f"/api/v1/admin/backups/infrastructure/{infra}/restore", token,
                           {"what": what, "confirm": "RESTORE"})
            state = wait_restore(base, token, call=call, sleep=sleep) if code in (200, 202) else {"error": f"HTTP {code}"}
            up = wait_api(base, call=call, sleep=sleep)
            ms = int((time.time() - t0) * 1000)
            ok = code in (200, 202) and not state.get("error") and up
            buf.rec(f"infrastructure restore ({what})", ok,
                    state.get("error") or ("" if up else "the API did not come back within 30 minutes") or "restored", ms)
            if not ok:
                healthy = False
                continue
            healthy &= check(f"after the infrastructure restore ({what})", ms)
            code, _ = call(base, "GET", "/api/v1/me", token)
            buf.rec(f"signing in after the infrastructure restore ({what})", code == 200, f"{code}")

    # 4: put back whole when anything failed, and remove what the test made
    if not healthy and infra:
        say("restore: something failed; the safety backup is put back whole")
        code, _ = call(base, "POST", f"/api/v1/admin/backups/infrastructure/{infra}/restore", token,
                       {"what": "full", "confirm": "RESTORE"})
        state = wait_restore(base, token, call=call, sleep=sleep) if code in (200, 202) else {"error": f"HTTP {code}"}
        buf.rec("the safety backup put back", not state.get("error") and wait_api(base, call=call, sleep=sleep),
                state.get("error") or "the installation is as it was before the test")
    code, b = call(base, "GET", "/api/v1/admin/backups", token)
    made = [x.get("name") for x in (((b or {}).get("infrastructure") or {}).get("infrastructure") or [])
            if x.get("kind") == "before-restore" and _after(x.get("created"), started)] if isinstance(b, dict) else []
    gone, left = [], []
    for name in [n for n in [infra, *made] if n]:
        c, _ = call(base, "POST", f"/api/v1/admin/backups/infrastructure/{name}/delete", token, {})
        (gone if c == 200 else left).append(name)
    if app:
        c, _ = call(base, "POST", f"/api/v1/admin/backups/application/{app}/delete", token, {})
        (gone if c == 200 else left).append(app)
    buf.rec("the test's backups removed", not left,
            f"removed {len(gone)}" if not left else f"could not remove {', '.join(left)}: delete them on the Backups page")
    buf.flush(record)
    return buf.tally


def _after(stamp, started: float) -> bool:
    """A backup's name stamp (20261113T180721Z) is from this test."""
    import calendar
    try:
        return calendar.timegm(time.strptime(str(stamp)[:15], "%Y%m%dT%H%M%S")) >= started - 60
    except (ValueError, TypeError):
        return False
