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
Each model appears as soon as its step is done. How far it has got is kept in core.startup_parts (part 'later'), which
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
    """The 'later' row of core.startup_parts, written at once (its own connection, autocommit) so screens see each step."""

    def __init__(self, conninfo: str, name: str, total: int):
        self.conn = psycopg.connect(conninfo, autocommit=True)
        self.done, self.total, self.failed = 0, total, []
        self.conn.execute("""INSERT INTO core.startup_parts (part, name, state, done, total, detail, started_at, finished_at, updated_at)
                             VALUES (%s, %s, 'starting', 0, %s, 'starting', now(), NULL, now())
                             ON CONFLICT (part) DO UPDATE SET name = EXCLUDED.name, state = 'starting', done = 0,
                                   total = EXCLUDED.total, detail = 'starting', started_at = now(), finished_at = NULL,
                                   updated_at = now()""", (PART, name, total))

    def step(self, label: str) -> None:
        self.conn.execute("UPDATE core.startup_parts SET detail = %s, updated_at = now() WHERE part = %s",
                          (f"loading: {label}", PART))

    def finished(self, label: str, ok: bool, why: str = "") -> None:
        self.done += 1
        if not ok:
            self.failed.append(f"{label}: {why}"[:300])
        self.conn.execute("UPDATE core.startup_parts SET done = %s, detail = %s, updated_at = now() WHERE part = %s",
                          (self.done, f"done: {label}" if ok else f"failed: {label}", PART))

    def close(self) -> None:
        state = "down" if self.failed else "up"
        detail = ("; ".join(self.failed) + ". The next start tries again.") if self.failed else "everything loaded"
        self.conn.execute("""UPDATE core.startup_parts SET state = %s, done = total, detail = %s, finished_at = now(),
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
        steps.append(("Sample libraries: the enterprise library and three project libraries", sample_library))
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
            "viewpoints": ["VP-01", "VP-05", "VP-08", "VP-11"],
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


def sample_library() -> None:
    """Laptop (owner, 9 Nov 2026, D346): the enterprise library and project libraries, made once by the library service."""
    from . import sample_library as sl
    for line in sl.run():
        _say(line)


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
    _say(f"all done in {time.monotonic() - t:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
