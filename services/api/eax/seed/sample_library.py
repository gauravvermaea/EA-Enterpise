"""The sample libraries (owner, 9 Nov 2026, phase 15.2, D346; AGENTS.md: every feature comes with sample data): laptop
only, made once by the library service itself. This step gathers what the pages point at (models, sample projects,
their documents and canvases, reference library entries) and sends it; the library never reads this database.

Between them the samples show every state: the enterprise library with folders, pages (text, tables, lists, links),
links into EA Explorer and out to the web, a file, and history to undo; three project libraries (one shown in the
enterprise library); and a project whose library is somewhere else (its own link)."""

from __future__ import annotations

from sqlalchemy import text

PROJECTS = ["Protea Claims Transformation 2028 (sample)", "Fynbos Pet Insurance launch (sample)", "Karoo Re cloud migration (sample)"]
EXTERNAL = ("Fynbos Board reporting pack (sample)", "https://intranet.example.org/sites/fynbos-board-pack/library")


def gather(conn) -> dict:
    from .. import projects as pj
    core = pj.core(conn)
    def short(s: str, n: int = 140) -> str:
        s = " ".join((s or "").split())
        return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"
    models = [{"id": r["guid"], "name": r["name"], "about": short(r["description"]), "kind": r["kind_code"]}
              for r in core.execute(text("""SELECT guid::text AS guid, name, description, kind_code FROM core.models
                                             WHERE NOT is_deleted AND kind_code IN ('project', 'reference') AND name ~ ' '
                                             ORDER BY kind_code = 'reference' DESC, id LIMIT 12""")).mappings()]
    names = {r["guid"]: r["name"] for r in core.execute(text("SELECT guid::text AS guid, name FROM core.models WHERE NOT is_deleted")).mappings()}
    projects = []
    for n in PROJECTS:
        p = conn.execute(text("SELECT id, guid::text AS guid, name FROM proj.projects WHERE name = :n"), {"n": n}).mappings().first()
        if not p:
            continue
        ms = conn.execute(text("SELECT model_guid::text AS g, how FROM proj.project_models WHERE project_id = :p ORDER BY how, model_guid"), {"p": p["id"]}).mappings()
        docs = conn.execute(text("""SELECT guid::text AS guid, coalesce(nullif(title, ''), file_name) AS title FROM proj.documents
                                     WHERE project_id = :p AND deleted_at IS NULL AND archived_at IS NULL ORDER BY id LIMIT 6"""), {"p": p["id"]}).mappings()
        cvs = conn.execute(text("SELECT guid::text AS guid, name FROM proj.canvases WHERE project_id = :p ORDER BY id LIMIT 5"), {"p": p["id"]}).mappings()
        projects.append({"id": p["guid"], "name": p["name"],
                         "models": [{"id": m["g"], "name": names.get(m["g"], "model"), "role": m["how"]} for m in ms if m["g"] in names],
                         "documents": [{"id": d["guid"], "title": d["title"]} for d in docs],
                         "canvases": [{"id": c["guid"], "name": c["name"]} for c in cvs]})
    refs = [{"id": r["guid"], "title": r["title"]} for r in conn.execute(text(
        "SELECT guid::text AS guid, title FROM proj.org_ref_entries ORDER BY id LIMIT 4")).mappings()]
    ext = conn.execute(text("SELECT guid::text AS guid, name FROM proj.projects WHERE name = :n"), {"n": EXTERNAL[0]}).mappings().first()
    return {"models": models, "projects": projects, "reference": refs,
            "external": [{"id": ext["guid"], "name": ext["name"], "link": EXTERNAL[1]}] if ext else []}


def run() -> list[str]:
    from .. import library_client as lc
    from .. import projects as pj
    if not lc.service_on():
        return ["the library service is switched off: no sample libraries"]
    with pj.connections() as conn:
        data = gather(conn)
    import time
    out, why = None, ""
    for _ in range(30):                # the library may still be starting: up to about two and a half minutes
        try:
            out = lc.seed(data)
            break
        except lc.LibraryDown as exc:
            why = str(exc)
            if "not answering" not in why:
                break
            time.sleep(5)
    if out is None:                    # the next start makes them
        return [f"sample libraries not made yet ({why}); the next start makes them"]
    made = out.get("made") or []
    return [f"sample libraries: {', '.join(made)}" if made else "sample libraries: already there"]
