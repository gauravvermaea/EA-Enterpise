"""Laptop sample data for the archive (R2.41, D626): one model archived and one deleted, made once, so the Archive page
shows both states straight after a clean restart (invented names only)."""

from __future__ import annotations

from sqlalchemy import text

from .. import archive as ar
from .. import model_ops as mo
from ..db import get_engine


class _Super:
    username, roles = "user_super_admin", ["super-admin"]


SAMPLES = (("Retired 2024 baseline (sample archived model)", "archived", "The 2024 baseline: replaced by the 2026 one"),
           ("Abandoned pilot (sample deleted model)", "deleted", "Pilot stopped; kept until a Super Admin purges it"))


def run() -> list[str]:
    out = []
    eng = get_engine()
    with eng.connect() as conn:
        with ar.beside("archive", conn) as ac:
            have = {r[0] for r in ac.execute(text("SELECT name FROM archive.archive_store WHERE kind = 'model'")).all()}
    for name, state, note in SAMPLES:
        if name in have:
            out.append(f"sample archive: {name} is there already")
            continue
        with eng.begin() as conn:
            conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true), "
                              "set_config('eax.user_roles', 'super-admin', true)"))
            conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
            guid = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": name}).scalar()
            conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
            if not guid:                             # made, but not moved yet (a start that stopped half way)
                made = mo.create_model(conn, "user_super_admin", {"kind": "project", "name": name, "source": "ArchiMate 4",
                                                                  "copy": "metamodel", "description": note})
                guid = str((made.get("model") or made)["id"])
        with eng.begin() as conn:
            conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
            ar.move_model(conn, _Super, guid, state, note)
        out.append(f"sample archive: {name} ({state})")
    out.append(_project())
    return out


PROJECT = ("Closed 2025 data platform study (sample archived project)", "Finished: kept for reference",
           "Study model (sample, archived with its project)")


def _project() -> str:
    """One archived project with a model of its own (R2.41 part 2): the model moves into the archive with it."""
    from .. import projects as pj
    name, note, model = PROJECT
    with get_engine().connect() as conn:
        with ar.beside("archive", conn) as ac:
            if ac.execute(text("SELECT 1 FROM archive.archive_store WHERE kind = 'project' AND name = :n"), {"n": name}).first():
                return f"sample archive: {name} is there already"
    with pj.connections() as pc:
        core = pj.core(pc)
        core.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true), "
                          "set_config('eax.user_roles', 'super-admin', true)"))
        p = pc.execute(text("SELECT id, guid::text AS guid FROM proj.projects WHERE name = :n"), {"n": name}).mappings().first()
        if not p:
            p = pc.execute(text("""INSERT INTO proj.projects (name, purpose, description, created_by)
                                   VALUES (:n, 'Sample', :d, 'user_super_admin') RETURNING id, guid::text AS guid"""),
                           {"n": name, "d": note}).mappings().first()
            pc.execute(text("""INSERT INTO proj.members (project_id, username, role, added_by)
                               VALUES (:p, 'user_super_admin', 'project-admin', 'user_super_admin') ON CONFLICT DO NOTHING"""),
                       {"p": p["id"]})
            made = mo.create_model(core, "user_super_admin", {"kind": "project", "name": model, "source": "ArchiMate 4",
                                                              "copy": "metamodel", "description": note})
            pc.execute(text("""INSERT INTO proj.project_models (project_id, model_guid, how, added_by)
                               VALUES (:p, CAST(:m AS uuid), 'created', 'user_super_admin')"""),
                       {"p": p["id"], "m": str((made.get("model") or made)["id"])})
        ar.move_project(pc, _Super, p["guid"], "archived", note)
    return f"sample archive: {name} (archived, with {model})"
