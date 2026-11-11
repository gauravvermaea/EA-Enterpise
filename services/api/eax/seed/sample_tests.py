"""Sample self-test runs on System admin > Self-test (phase 36.1, D367, D522, D529): laptop only, made once (when no run
is there yet). Between them they show every state:

  * a smoke test that passed, by user_it_admin from the Self-test page, **with its fixtures still there** (the models
    self_test_<id>_1 and _2, the project self_test_<id>_3, its test accounts and their revoked tokens), made the way a
    real run makes them, so Test fixtures has something to purge;
  * detailed tests that failed, by `eax test`: an API check with a server error (what was asked and what came back), a
    browser journey that failed with its screenshot (headless) and one watched in a browser, a ZAP warning and a skipped
    check; its fixtures already removed (the report stays, marked so);
  * a run that could not start (the runner image was not built), with the reason.
"""

from __future__ import annotations

import struct
import zlib

from sqlalchemy import text

from ..testing import store


def _png(width: int = 320, height: int = 180) -> bytes:
    """A small plain PNG standing in for a failed journey's screenshot: a page with a red bar where the error showed."""
    rows = []
    for y in range(height):
        row = bytearray([0])
        for _x in range(width):
            if 20 <= y < 40:
                row += bytes((31, 59, 102))          # the header
            elif 90 <= y < 110:
                row += bytes((200, 40, 40))          # the error
            else:
                row += bytes((246, 247, 249))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def run() -> list[str]:
    from ..db import get_engine
    from ..testing import fixtures
    eng = get_engine()
    with eng.begin() as conn:
        if conn.execute(text("SELECT 1 FROM core.test_runs LIMIT 1")).first():
            return ["sample self-test runs: there are runs already"]
        version = conn.execute(text("SELECT version FROM core.schema_versions ORDER BY applied_at DESC LIMIT 1")).scalar() or ""
        ok = store.create_run(conn, "user_it_admin", "web", ["api", "ui", "db", "security"], "20261109T201500Z-run1", version,
                              "smoke")
        store.set_state(conn, ok, state="running")
        run = dict(conn.execute(text("SELECT id, run_guid::text AS run_guid FROM core.test_runs WHERE id = :i"), {"i": ok}).mappings().first())
    notes = []
    try:
        with eng.begin() as conn:
            fixtures.accounts(conn, run, "user_it_admin", ["super-admin", "architect", "model-admin"], notes.append)
        fixtures.models_and_project(eng, run, "user_it_admin", ["super-admin", "architect", "model-admin"], notes.append)
    except Exception as exc:  # noqa: BLE001 - the run's records still show; its fixtures are listed as far as they were made
        notes.append(f"fixtures not all made: {exc}")
    with eng.begin() as conn:
        for name, detail in [("sign in as super-admin", "200"), ("sign in as architect", "200"), ("sign in as model-admin", "200"),
                             ("area models answers: GET /api/v1/models", "200"), ("area projects answers: GET /api/v1/projects", "200"),
                             ("area administration answers: GET /api/v1/admin/settings", "200"),
                             ("journey: sign in and the start page", "1 page(s) as architect"),
                             ("journey: a model: overview, grid and quality", "3 page(s) as model-admin")]:
            store.add_result(conn, ok, "smoke", name, "passed", detail, 140,
                             browser="Chromium 130 (headless, on the server)" if name.startswith("journey") else "")
        store.finish(conn, ok)
        conn.execute(text("UPDATE core.machine_credentials SET revoked_at = now(), revoked_by = 'user_it_admin', "
                          "revoke_reason = 'the self-test run ended' WHERE owner LIKE :o AND revoked_at IS NULL"),
                     {"o": f"svc-self-test-{store.short(run['run_guid'])}-%"})
        conn.execute(text("""UPDATE core.test_runs SET queued_at = now() - interval '1 day', started_at = now() - interval '1 day',
                             finished_at = now() - interval '1 day' + interval '4 minutes' WHERE id = :id"""), {"id": ok})

        bad = store.create_run(conn, "eax test", "eax", ["api", "ui", "db", "security"], "20261110T061000Z", version, "detailed",
                               watch=True)
        store.set_state(conn, bad, state="running")
        store.add_result(conn, bad, "db", "every table has a primary key", "passed", "nothing wrong", 40)
        store.add_result(conn, bad, "db", "foreign keys have an index (speed)", "warning",
                         "core.models(kind_code) (a sample: the speed check lists what it would index)", 60)
        store.add_result(conn, bad, "api", "GET /api/v1/models/{model_id}/kpis: every test role", "failed",
                         "report-viewer: server error 500 (a sample failure)", 210,
                         request="GET /api/v1/models/0b6c.../kpis  as report-viewer",
                         response='500\n{"code": 500, "status": "Internal Server Error", "message": "a sample failure"}')
        store.add_result(conn, bad, "api", "PUT /api/v1/admin/servers: refused without a global role", "passed", "refused: 403", 15)
        store.add_result(conn, bad, "ui", "journey: a project and its tasks", "failed",
                         "Timeout 30000ms exceeded waiting for text=Tasks (a sample failure)", 41000, _png(), "",
                         browser="Chromium 130 (headless, on the server)")
        store.add_result(conn, bad, "ui", "journey: the models list", "passed", "1 page(s) as architect", 3200,
                         browser="Edge 130 (watched here)")
        store.add_result(conn, bad, "security", "OWASP ZAP baseline scan", "warning", "Medium: Content Security Policy (CSP) Header Not Set", 0)
        store.add_result(conn, bad, "security", "Python dependencies (pip-audit)", "skipped",
                         "pip-audit could not run: no internet to read the advisory database", 0)
        store.finish(conn, bad)
        conn.execute(text("UPDATE core.test_runs SET purged_at = now(), purged_by = 'user_super_admin' WHERE id = :id"), {"id": bad})

        err = store.create_run(conn, "user_super_admin", "web", ["ui"], "", version, "detailed")
        store.set_state(conn, err, state="error",
                        message="Could not start: The test runner image eaexplorer/testrunner is not built yet: run eax test once on this server.")
        conn.execute(text("UPDATE core.test_runs SET queued_at = now() - interval '2 days', finished_at = now() - interval '2 days' "
                          "WHERE id = :id"), {"id": err})
    return [f"sample self-test runs: {ok} passed (its fixtures kept), {bad} failed (fixtures removed), {err} could not start"]
