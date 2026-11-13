"""After the API has started (D255): python -m eax.seed.later

The start-up has two tiers. The core (database, sign-in, the API and the screens) comes first: the entrypoint upgrades
the database and loads only what everyone needs (eax/seed/__main__.py), then starts the API. Everything else is loaded
here, in the background, one step at a time, so nobody waits for it to sign in:
  * the sample insurance model (when EAX_SEED_SAMPLE is true: the laptop template sets it)
  * laptop only, with the sample: the test models (Fynbos Mutual group, Fynbos Life and Commercial, Karoo Re, the Lean
    EA metamodel and a model in each state), the demo estate Protea Insurance, the data quality samples, a few saved
    versions of two sample entities for the History tab (D110), the test users' roles, and the demo estate's tags,
    gap analyses and sheets (D176)
  * laptop only, with the sample: key questions in every sample project, in every state (D341), and Business Model
    Canvases in three of them (D344)
  * every model's first data quality measurement (models never measured yet), so highlights show from the start
Each model appears as soon as its step is done. How far it has got is kept in operations.startup_parts (part 'later'), which
the screens show to everyone (Sample data: loading 3 of 9, amber; then green). A failed step is logged and the others
carry on; the next start tries again (a step already loaded is skipped). Several API servers: one runs it
(entrypoint.sh: eax.startup single later).
"""

from __future__ import annotations

import os
import sys
import time

import psycopg

from ..config import get_settings
from .__main__ import assign_test_users, give_icons, history_demo, refresh_views
from .build import SAMPLE_ID, seed_sql, test_model_steps

PART = "later"


def _say(msg: str) -> None:
    print(f"EA Explorer later: {msg}", flush=True)


class Progress:
    """The 'later' row of operations.startup_parts, written at once (its own connection, autocommit) so screens see each step."""

    def __init__(self, conninfo: str, name: str, total: int):
        from .. import databases
        ops = databases.BY_KEY["operations"]          # the start-up status lives in the operations database (R2.27)
        self.conn = psycopg.connect(databases.setting(ops) if databases.own(ops) else conninfo, autocommit=True)
        self.done, self.total, self.failed = 0, total, []
        self.conn.execute("""INSERT INTO operations.startup_parts (part, name, state, done, total, detail, started_at, finished_at, updated_at)
                             VALUES (%s, %s, 'starting', 0, %s, 'starting', now(), NULL, now())
                             ON CONFLICT (part) DO UPDATE SET name = EXCLUDED.name, state = 'starting', done = 0,
                                   total = EXCLUDED.total, detail = 'starting', started_at = now(), finished_at = NULL,
                                   updated_at = now()""", (PART, name, total))

    def step(self, label: str) -> None:
        self.conn.execute("UPDATE operations.startup_parts SET detail = %s, updated_at = now() WHERE part = %s",
                          (f"loading: {label}", PART))

    def finished(self, label: str, ok: bool, why: str = "") -> None:
        self.done += 1
        if not ok:
            self.failed.append(f"{label}: {why}"[:300])
        self.conn.execute("UPDATE operations.startup_parts SET done = %s, detail = %s, updated_at = now() WHERE part = %s",
                          (self.done, f"done: {label}" if ok else f"failed: {label}", PART))

    def close(self) -> None:
        state = "down" if self.failed else "up"
        detail = ("; ".join(self.failed) + ". The next start tries again.") if self.failed else "everything loaded"
        self.conn.execute("""UPDATE operations.startup_parts SET state = %s, done = total, detail = %s, finished_at = now(),
                                    updated_at = now() WHERE part = %s""", (state, detail[:1000], PART))
        self.conn.close()


def _run(progress: Progress, label: str, fn) -> None:
    """One step in its own transaction; a failure is logged and kept, the others carry on."""
    progress.step(label)
    t = time.monotonic()
    try:
        fn()
        progress.finished(label, True)
        _say(f"{label}: done ({time.monotonic() - t:.0f} s)")
    except Exception as exc:  # noqa: BLE001 - the API already serves; never stop the container
        progress.finished(label, False, str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
        _say(f"{label}: FAILED ({exc})")


def plan(settings, with_sample: bool) -> list[tuple[str, object]]:
    """The steps, in order: (what it loads, a function doing it)."""
    info = settings.migrator_conninfo
    steps: list[tuple[str, object]] = []
    loaded: set[str] = set()                         # what this start loaded (not skipped as already there)

    def sql_step(label: str, check: str, sql: str):
        def go():
            with psycopg.connect(info) as conn:      # one transaction, committed on leaving
                if check and conn.execute(check).fetchone():
                    return
                conn.execute(sql)
            loaded.add(label)
        return go

    if with_sample:
        steps.append(("Sample insurance model", sql_step("Sample insurance model", f"SELECT 1 FROM core.models WHERE guid = '{SAMPLE_ID}'::uuid",
                                                         seed_sql(with_template=False, with_insurance=False, with_sample=True, with_togaf10=False,
                                                                  with_principles=False))))
    laptop = settings.deployment == "laptop" and with_sample
    if laptop:
        for _key, label, check, sql in test_model_steps():
            steps.append((label, sql_step(label, check, sql)))

        def history():                               # once: when this start loaded the sample model
            if "Sample insurance model" in loaded:
                with psycopg.connect(info) as conn:
                    history_demo(conn)
        steps.append(("History of two sample entities", history))

    def tidy():
        with psycopg.connect(info) as conn:
            if settings.deployment == "laptop":
                assign_test_users(conn)
            give_icons(conn)
            refresh_views(conn)
    steps.append(("Model icons, roles and report views", tidy))
    steps.append(("Library models into their schema (R2.42)", library_models_in))

    if laptop:
        def estate():
            from .versions_demo import main as demo_main
            demo_main()
        steps.append(("Demo estate tags, gap analyses and sheets", estate))
    if laptop:
        steps.append(("Sample architecture project", sample_project))
        steps.append(("Sample projects, one per project template", sample_projects))
        steps.append(("Sample content: governance, people, calendars, sheets, the board", sample_content))
        steps.append(("Sample key questions in every sample project", sample_questions))
        steps.append(("Sample Business Model Canvases", sample_canvases))
        steps.append(("Sample drawn views on the demo estate, one as project evidence", sample_drawn_views))
        steps.append(("Sample libraries: the enterprise library and three project libraries", sample_library))
        steps.append(("Sample merge requests and duplicates", sample_merge_dedupe))
        steps.append(("Sample surveys and EA capability maturity assessments", sample_surveys))
        steps.append(("Sample machine access and operations: service accounts, credentials, usage, housekeeping",
                      sample_machine_ops))
        steps.append(("Sample KPI trends on the demo estate", sample_kpis))
        steps.append(("Sample uploads on Other views and documents", sample_other_uploads))
        steps.append(("Sample import sources and deliveries, and a model from a metamodel workbook", sample_imports))
        steps.append(("Sample MCP work: a copy cleaned up, an override, the AI activity log", sample_mcp))
        steps.append(("Sample scenario planning: a scenario committed, one with what-ifs pending, an assessment", sample_scenarios))
        steps.append(("Sample ADM iterations: full, development then transition, governance, custom, none chosen", sample_iterations))
        steps.append(("Sample update history: succeeded, rolled back, not started, scheduled", sample_updates))
        steps.append(("Sample archive: a model archived and one deleted, a project archived", sample_archive))
        steps.append(("Sample derived entity types: Server > Windows Server > Database Server", sample_derived))
    if laptop:
        steps.append(("Sample test runs: passed, failed with a screenshot, could not start", sample_tests))
    # the industry packs (D546) are no longer a step here: they load beside these steps, with their own status
    # (industry_packs_beside, main), so the sample data does not wait for Documents (R2.23)
    steps.append(("First data quality measurement", first_measurements))
    return steps


def sample_project() -> None:
    """Laptop (phase 13): an architecture project on the demo estate with the test users in each project role, so the
    projects, the wizard's choices and the repository can be tried at once (its repository is built when Documents is up)."""
    from sqlalchemy import text

    from .. import permissions
    from .. import projects as pj
    name = "Protea Target Architecture 2028 (sample project)"

    class _U:
        username = "user_project_admin"
        roles = ("user",)
    with pj.connections() as conn:      # proj may have its own database (D266)
        if conn.execute(text("SELECT 1 FROM proj.projects WHERE name = :n"), {"n": name}).first():
            return
        protea = pj.core(conn).execute(text("SELECT guid::text FROM core.models WHERE name = 'Protea Insurance (demo estate)' AND NOT is_deleted")).scalar()
        steps = conn.execute(text("SELECT id FROM proj.lib_steps WHERE phase = 'B' AND name LIKE 'Model the product lifecycle%'")).scalar()
        principles = [r["id"] for r in conn.execute(text("SELECT id FROM proj.lib_principles ORDER BY code LIMIT 6")).mappings().all()]
        pj.create(conn, _U(), {
            "name": name, "purpose": "portfolio",
            "description": "Sample: the demo estate's move from the 2026 baseline to the 2028 target, run as one ADM cycle.",
            "models": [{"how": "added", "model": protea}] if protea else [],
            "views": ["VP-01", "VP-05", "VP-08", "VP-11"],
            "principles": [{"library_id": i} for i in principles]
                          + [{"name": "Reuse before buy, buy before build", "statement": "Use what the estate has before buying, and buy before building."}],
            "removed_steps": [{"library_id": steps, "reason": "Products do not change in this cycle."}] if steps else [],
            "own_steps": [{"phase": "A", "name": "Agree the 2028 target scope with the Executive Committee"}],
            "members": [{"username": u, "role": r} for u, r in permissions.PROJECT_TEST_ROLES],
            "signoff": {"": ["user_lead_architect", "user_stakeholder"]},
            "libraries": ["EA Explorer"],
        }, sample=True)


def sample_projects() -> None:
    """Laptop (owner, 7 Nov 2026): a sample project for each project template, between them showing every way a model
    joins a project: referred to, added, a separate copy (now or at a tag), a child, a new empty model."""
    from . import sample_projects as sp
    for line in sp.run():
        _say(line)


def sample_content() -> None:
    """Laptop (owner, 8 Nov 2026, phase 13.8): seed content for the sample projects and the organisation, made once."""
    from . import sample_content as sc
    for line in sc.run():
        _say(line)


def sample_questions() -> None:
    """Laptop (owner, 9 Nov 2026, D341): key questions in every sample project, in every state, made once per project."""
    from . import sample_questions as sq
    for line in sq.run():
        _say(line)


def sample_canvases() -> None:
    """Laptop (owner, 9 Nov 2026, D344): Business Model Canvases in three sample projects, in every kind and state."""
    from . import sample_canvases as sc
    for line in sc.run():
        _say(line)


def sample_drawn_views() -> None:
    """Laptop (owner, 10 Nov 2026, phases 28 and 29): drawn views in every state on the demo estate, made once."""
    from . import sample_drawn_views as sd
    for line in sd.run():
        _say(line)


def sample_library() -> None:
    """Laptop (owner, 9 Nov 2026, D346): the enterprise library and project libraries, made once by the library service."""
    from . import sample_library as sl
    for line in sl.run():
        _say(line)


def sample_kpis() -> None:
    """Laptop (owner, 10 Nov 2026, phase 24): a year of KPI snapshots and the model's own KPIs on the demo estate, made once."""
    from ..db import get_engine
    from . import sample_kpis as sk
    with get_engine().begin() as conn:
        for line in sk.run(conn):
            _say(line)


def sample_machine_ops() -> None:
    """Laptop (owner, 10 Nov 2026, phases 25 and 35): machine access and operations in every state, made once."""
    from . import sample_machine_ops as sm
    for line in sm.run():
        _say(line)


def sample_archive() -> None:
    """Laptop (R2.41): a model archived and one deleted, in the archive database, made once."""
    from . import sample_archive as sa
    for line in sa.run():
        _say(line)


def library_models_in() -> None:
    """R2.42 (D633): every library model whose content is still in core moved into the library_models schema, one model
    at a time (each all or nothing); made once, a no-op afterwards."""
    from .. import library_models as lm
    for line in lm.move_all(lambda _p, note: _say(note)):
        _say(line)


def sample_derived() -> None:
    """Laptop (R2.9, D629): a metamodel with a type derived from another, two levels deep, made once."""
    from . import sample_derived as sd
    for line in sd.run():
        _say(line)


def sample_surveys() -> None:
    """Laptop (owner, 9 Nov 2026, phases 38.1 and 40): surveys and maturity assessments in every state, made once."""
    from . import sample_surveys as ss
    for line in ss.run():
        _say(line)


def sample_merge_dedupe() -> None:
    """Laptop (owner, 10 Nov 2026, phases 19, 20 and 21): merge requests in every state and duplicates to find and merge."""
    from . import sample_merge_dedupe as smd
    for line in smd.run():
        _say(line)


def sample_imports() -> None:
    """Laptop (owner, 10 Nov 2026, phase 34, D419): import sources and deliveries in every state, and a model from a
    metamodel workbook, made once."""
    from . import sample_imports as si
    for line in si.run():
        _say(line)


def sample_other_uploads() -> None:
    """Laptop (owner, 10 Nov 2026, D461): a project's own uploads on Other views and documents, one replaced, made once."""
    from . import sample_other_uploads as so
    for line in so.run():
        _say(line)


def sample_tests() -> None:
    """Laptop (phase 36.1, D522): sample test runs on System admin > Health > Tests: passed, failed (a screenshot), could
    not start; made once."""
    from . import sample_tests as st
    for line in st.run():
        _say(line)


def sample_scenarios() -> None:
    """Laptop (owner, 10 Nov 2026, phase 27.1, D495): scenario planning in Protea build or buy, made once."""
    from . import sample_scenarios as ss
    for line in ss.run():
        _say(line)


def sample_iterations() -> None:
    """Laptop (owner, 11 Nov 2026, D571-D574): ADM iteration types on the sample projects, one of each state, made once."""
    from . import sample_iterations as si
    for line in si.run():
        _say(line)


def sample_mcp() -> None:
    """Laptop (owner, 10 Nov 2026, phases 26/27, D458, D482): a model copied and deduped through MCP, a merge done through
    MCP, and the AI activity log with a call of every kind, made once."""
    from . import sample_mcp as smc
    for line in smc.run():
        _say(line)


def sample_updates() -> None:
    """Laptop (owner, 10 Nov 2026, phase 36, D516): the update history in each state, made once."""
    from . import sample_updates as su
    for line in su.run():
        _say(line)


def industry_packs() -> None:
    """D546: the packs shipped in the repository (library/industry-packs, mounted at /data/industry-packs) are uploaded
    into Documents when missing or changed (by checksum); unchanged files are skipped, so every start is quick after the
    first. When Documents is off or not up yet, nothing is lost: the 10-minute job (or `eax packs load`) loads them."""
    from .. import industry_packs as ip
    # each file in its own transaction, the status kept up to date file by file, one loader at a time; what Documents
    # refuses is tried again by the 10-minute job (R2.23)
    out = ip.load_shipped_each("system:seed")
    _say(f"industry packs: {out['message']}")
    for name in out.get("refused", []):
        _say(f"industry packs: not loaded (marked not for AI use): {name}")
    for why in out.get("failed", []):
        _say(f"industry packs: not loaded, tried again in 10 minutes: {why}")


def industry_packs_beside(wait_minutes: float = 20, pause: float = 20) -> None:
    """The industry packs, beside the steps (a thread of main): waits for Documents to answer (up to 20 minutes; after
    that the 10-minute job carries on), then loads them file by file with their own start-up status (R2.23)."""
    from .. import industry_packs as ip
    from .. import mayan
    end = time.monotonic() + wait_minutes * 60
    try:
        while mayan.enabled() and not mayan.ping() and time.monotonic() < end:
            time.sleep(pause)
        industry_packs()
    except Exception as exc:  # noqa: BLE001 - the job tries again in 10 minutes
        _say(f"industry packs: FAILED ({exc}); tried again in 10 minutes")
        try:
            from ..db import get_engine
            ip._part(get_engine(), "down", 0, 0, f"{exc}"[:300] + "; tried again in 10 minutes", finish=True)
        except Exception:  # noqa: BLE001
            pass


def first_measurements() -> None:
    """Every measured model never measured yet is measured once and kept, so its highlights show from the start."""
    from sqlalchemy import text

    from .. import quality
    from ..db import get_engine
    with get_engine().begin() as conn:
        quality._bypass(conn, True)
        models = [dict(r._mapping) for r in conn.execute(text(f"""
            SELECT m.id AS _id, m.guid::text AS id, m.name, m.kind_code AS kind FROM core.models m
             WHERE NOT m.is_deleted AND {quality.MEASURED_SQL}
               AND NOT EXISTS (SELECT 1 FROM core.quality_runs r WHERE r.model_id = m.id) ORDER BY m.id"""))]
        quality._bypass(conn, False)
    for m in models:
        try:
            with get_engine().begin() as conn:
                quality._bypass(conn, True)
                quality.run(conn, m, "system", "on-demand")
                quality._bypass(conn, False)
            _say(f"first data quality measurement of {m['name']}")
        except Exception as exc:  # noqa: BLE001 - one model never stops the others
            _say(f"first data quality measurement of {m['name']} failed: {exc}")


def main() -> int:
    settings = get_settings()
    if not settings.db_migrator_password:
        _say("EAX_DB_MIGRATOR_PASSWORD is not set; nothing loaded")
        return 0
    with_sample = os.environ.get("EAX_SEED_SAMPLE", "false").strip().lower() in ("1", "true", "yes")
    steps = plan(settings, with_sample)
    name = "Sample data" if with_sample else "Start-up tasks"
    t = time.monotonic()
    try:
        progress = Progress(settings.migrator_conninfo, name, len(steps))
    except Exception as exc:  # noqa: BLE001 - no status row: still load
        _say(f"cannot record progress ({exc})")
        progress = None
    import threading
    packs = threading.Thread(target=industry_packs_beside, name="industry-packs", daemon=True)
    packs.start()
    for label, fn in steps:
        if progress:
            _run(progress, label, fn)
        else:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                _say(f"{label}: FAILED ({exc})")
    if progress:
        progress.close()
    packs.join()                                     # the process ends when the packs are loaded too
    _say(f"all done in {time.monotonic() - t:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
