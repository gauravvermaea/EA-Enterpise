"""The self-test's backup checks, the last suite of a full test (R2.45; owner, 12 Nov 2026: "do u test application backup
and infra backup in your testing? If not it should be. Please test it atleast in command line at the end of test as a
last test"). As a Super Admin, through the same API the Backups page uses:

  1. an infrastructure backup, tagged self-test-<run>, followed until it is made
  2. a trial restore of it (the operations helper's verify.sh): the checksums, every file set readable, every database
     restored into a scratch copy (<name>_restore_test), its tables counted against the live one's, and dropped;
     nothing live is touched
  3. an application backup of the run's own model (self_test_<id>_1)
  4. that model restored from it as a new model (self_test_<id>_4, a fixture of the run), its entities and
     relationships counted against the original's
  5. the backups the test made, removed (D593: the self-test leaves nothing behind)

Each step is a result in the suite "backup" (critical, R2.35). When every one passes, backups and restores from the web
count as proven (R2.46) and the Backups page shows its buttons; until then it shows the commands to run."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import text

from .api_writes import call

Record = Callable[..., None]
SUITE = "backup"


def wait_task(base: str, token: str, task: dict | str, seconds: int, call=call) -> dict:
    """Follows a background task (D273) until it is done; its last state (status timeout when it took too long)."""
    tid = task.get("id") if isinstance(task, dict) else task
    end = time.time() + seconds
    last: dict = task if isinstance(task, dict) else {}
    while time.time() < end:
        code, body = call(base, "GET", f"/api/v1/tasks/{tid}", token)
        if code == 200 and isinstance(body, dict):
            last = body
            if body.get("done"):
                return body
        time.sleep(3)
    return {**last, "status": "timeout", "message": f"not done after {seconds // 60} minutes"}


def counts(engine, model_guid: str) -> tuple[int, int]:
    """A model's live entities and relationships."""
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
        row = conn.execute(text("""SELECT (SELECT count(*) FROM core.entities e WHERE e.model_id = m.id AND NOT e.is_deleted),
                                          (SELECT count(*) FROM core.relationships r WHERE r.model_id = m.id AND NOT r.is_deleted)
                                     FROM core.models m WHERE m.guid = CAST(:g AS uuid)"""), {"g": model_guid}).first()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def run(base: str, token: str, ids: dict[str, str], record: Record, log: Callable[[str], None], engine,
        run_id: int, add_fixture: Callable[[str, str, str], None], call=call) -> dict[str, int]:
    """The backup checks (see the module). token: a Super Admin's. Returns passed and failed counts."""
    tally = {"passed": 0, "failed": 0}
    tag, sid = f"self-test-{run_id}", ids.get("sid", "")

    def rec(name: str, ok: bool, detail: str, ms: int = 0) -> None:
        tally["passed" if ok else "failed"] += 1
        record(f"backup: {name}", "passed" if ok else "failed", detail, ms)

    def task(path: str, body: dict, minutes: int) -> tuple[bool, dict, int]:
        t0 = time.time()
        code, b = call(base, "POST", path, token, body)
        if code not in (200, 202) or not isinstance(b, dict):
            return False, {"message": f"HTTP {code}: {str(b)[:300]}"}, int((time.time() - t0) * 1000)
        t = wait_task(base, token, b, minutes * 60, call=call)
        return t.get("status") == "done", t, int((time.time() - t0) * 1000)

    # 1 and 2: an infrastructure backup and its trial restore
    log("backups: an infrastructure backup (every database and file set)")
    ok, t, ms = task("/api/v1/admin/backups/infrastructure", {"tag": tag}, 120)
    infra = (t.get("result") or {}).get("name") if ok else ""
    rec("an infrastructure backup", ok and bool(infra), t.get("message") or t.get("status") or "", ms)
    if infra:
        log(f"backups: a trial restore of {infra} into scratch copies")
        ok, t, ms = task(f"/api/v1/admin/backups/infrastructure/{infra}/verify", {}, 120)
        checks = (t.get("result") or {}).get("checks") or []
        if not checks:
            rec("the trial restore", False, t.get("message") or t.get("status") or "no checks came back", ms)
        for c in checks:
            rec(f"trial restore: {c.get('name')}", bool(c.get("ok")), str(c.get("detail") or ""))

    # 3 and 4: an application backup of the run's model, and that model restored from it as a new model
    model = ids.get("model", "")
    app = ""
    if model:
        log("backups: an application backup of the test model")
        ok, t, ms = task("/api/v1/admin/backups/application", {"tag": tag, "models": [model]}, 30)
        app = (t.get("result") or {}).get("name") if ok else ""
        rec("an application backup of the test model", ok and bool(app), t.get("message") or t.get("status") or "", ms)
    if app:
        code, b = call(base, "GET", "/api/v1/admin/backups", token)
        runs = ((b.get("application") or {}).get("runs") or []) if isinstance(b, dict) else []
        mine = next((r for r in runs if r.get("name") == app), {})
        file = next((m.get("file") for m in mine.get("models") or [] if m.get("file")), "")
        if not file:
            rec("the test model restored from its backup", False, f"no model file in the application backup {app}")
        else:
            log("backups: the test model restored from it as a new model")
            new_name = f"self_test_{sid}_4"
            ok, t, ms = task("/api/v1/admin/backups/restore-model",
                             {"where": "application", "name": app, "file": file, "mode": "new", "new_name": new_name}, 30)
            new = (t.get("result") or {}).get("model") if ok else ""
            if new:
                add_fixture("model", new, new_name)
                before, after = counts(engine, model), counts(engine, new)
                same = before == after
                rec("the test model restored from its backup", same,
                    f"{after[0]} entities and {after[1]} relationships, as in the model backed up" if same else
                    f"restored {after[0]} entities and {after[1]} relationships; the model has {before[0]} and {before[1]}", ms)
            else:
                rec("the test model restored from its backup", False, t.get("message") or t.get("status") or "", ms)

    # 5: what the test made, removed
    gone, left = [], []
    if infra:
        code, _ = call(base, "POST", f"/api/v1/admin/backups/infrastructure/{infra}/delete", token, {})
        (gone if code == 200 else left).append(infra)
    if app:
        code, _ = call(base, "POST", f"/api/v1/admin/backups/application/{app}/delete", token, {})
        (gone if code == 200 else left).append(app)
    if gone or left:
        rec("the test's backups removed", not left,
            f"removed {', '.join(gone)}" if not left else f"could not remove {', '.join(left)}: delete them on the Backups page")
    return tally
