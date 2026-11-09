"""MCP tools to BUILD with a language model (owner, 7 Nov 2026): projects, models and their content.

Registered on the same MCP server (eax.mcp_server imports this module at its end). Every tool runs as the signed-in
person, through the same code and permission checks as the screens:
  * content added to a working model is kept as the person's uncommitted changes (D165), exactly as on the screens:
    commit_my_changes (or the Changes page) makes it part of the model; a library model being built is saved at once
  * projects use the project rules (who may create, contribute, administer); their repository is built in Documents by
    the background job, as it is for the wizard
Prompts (build_a_project, build_a_model, fill_a_model) give the assistant the order of work.
"""

from __future__ import annotations

from typing import Any

import anyio

from . import audit, permissions
from . import repository as repo
from .mcp_server import _clean, _run, mcp
from .metamodel_edit import EditError

BUILD_GUIDE = """How to build with EA Explorer (read this before creating anything):

MODELS
1. Look first: list_models, list_library, get_metamodel. Reuse a model when one fits.
2. create_model makes a project model:
   start="empty"  from a root metamodel (source = e.g. "ArchiMate 4"): the metamodel only
   start="copy"   a separate copy of a model (source), metamodel and content (copy="metamodel" for the metamodel only);
                  with tag=<tag name or id> it is the model as it was at that tag (always a separate copy)
   start="child"  a copy that stays linked to its parent (source) and can be merged back later
3. Content: add_entities (many at once, by entity type), then add_relationships. Use the entity type and attribute
   codes from describe_entity_type; check allowed_relationships before relating. Entities are referred to by name
   or guid. Values go in values {attribute code: value}.
4. In a working model your additions are YOUR uncommitted changes: list_my_changes shows them, commit_my_changes
   (with a message) makes them part of the model. Tell the person what you added and ask before committing.
5. tag_model marks the model as it is now (a baseline), to compare or copy from later.

PROJECTS (TOGAF ADM)
1. list_project_templates: transformation, document-as-is, new product, regulatory change, cloud migration...
   Each says which models it needs (current, target, transition, reference...).
2. create_project with a template, a name, the models (each: how = referred | added | derived | created, role, and
   for derived/created: start, source, name) and optionally goals [{name, outcomes: [{name, measure, target_date}]}].
   Exactly one model is the primary working one (home=true) when there are goals.
3. get_project shows phases, steps, document classes, documents, approvals and models. Work through it:
   add_project_step / complete_project_step (who and when are kept; complete again = a new sub step),
   add_document_class, set_document_tags, accept_document (with the evidence) or send_document_for_approval.
4. Documents themselves (Word, Excel...) are uploaded on the project's Repository tab: you prepare their content.

ALWAYS: say what you are about to create and get the person's yes for anything that makes models or projects;
prefer small steps; report the names and links (/#/metamodel/<id>, /#/projects/<id>) of what you made."""


def _who() -> permissions.Principal:
    return permissions.current.get()


async def _proj(fn, *args, write: bool = False) -> Any:
    """A projects function on the projects' connection (with the repository's beside it), as the signed-in person."""
    from . import projects as pj
    if permissions.current.get() is None:
        return {"error": "Sign in required."}
    from . import settings as app_settings
    if not app_settings.parts().get("projects", True):         # D329
        return {"error": "Projects are switched off in this installation (System admin > System settings)."}
    who = _who()

    def work():
        with pj.connections(write) as pc:
            out = fn(pc, who, *args)
            if write:
                audit.record(pj.core(pc), actor=who.username, action=f"mcp.{getattr(fn, '__name__', 'project')}", object_type="project",
                             object_id=str(args[0]) if args else "", source="mcp")
            return out
    try:
        result = _clean(await anyio.to_thread.run_sync(work))
    except (repo.NotFound, EditError) as exc:
        return {"error": str(exc)}
    return {"count": len(result), "items": result} if isinstance(result, list) else result


def _content_change(model: str, op_rows):
    """Content into a model: the person's uncommitted changes in a working model; saved at once in a library model."""
    from . import commits as cm

    def run(conn):
        who = _who()
        m = repo.get_model(conn, model)
        out = op_rows(conn, who, m, cm.uses_commits(m))
        audit.record(conn, actor=who.username, action="mcp.content", object_type="model", object_id=str(m["id"]), source="mcp")
        return out
    return run


# ================================================================ guidance
@mcp.tool()
async def how_to_build() -> Any:
    """READ FIRST when asked to build or change anything: how to make models (empty, copy, copy at a tag, child),
    add content, and set up and run an architecture project, step by step, with the tools to use."""
    return {"guide": BUILD_GUIDE}


if hasattr(mcp, "prompt"):
    @mcp.prompt()
    def build_a_project(goal: str = "") -> str:
        """Set up an architecture project (TOGAF ADM) with an assistant."""
        return (f"{BUILD_GUIDE}\n\nThe person wants a project for: {goal or '(ask them)'}.\nStart with list_project_templates and "
                "list_models, propose the template, the models (and how each joins) and two or three goals with outcomes, and "
                "wait for their yes before create_project.")

    @mcp.prompt()
    def build_a_model(purpose: str = "") -> str:
        """Make a model and fill it with an assistant."""
        return (f"{BUILD_GUIDE}\n\nThe person wants a model for: {purpose or '(ask them)'}.\nCheck list_models and list_library "
                "first; propose how to start (empty from ArchiMate 4, a copy, a copy at a tag, or a child) and wait for their yes.")

    @mcp.prompt()
    def fill_a_model(model: str = "", source: str = "") -> str:
        """Add entities and relationships to a model from a description or a document."""
        return (f"{BUILD_GUIDE}\n\nModel: {model or '(ask)'}. Material: {source or '(the person will paste it)'}.\nRead the "
                "metamodel (get_metamodel, describe_entity_type), map the material to entity types, show the person a table "
                "of what you will add, then add_entities and add_relationships; list_my_changes; commit only when they agree.")


# ================================================================ models
@mcp.tool()
async def create_model(name: str, start: str = "empty", source: str = "ArchiMate 4", copy: str = "content",
                       tag: str = "", description: str = "", industry: str = "") -> Any:
    """Make a project model. start: "empty" (from a root metamodel named in source, e.g. "ArchiMate 4"), "copy" (a
    separate copy of the model in source; copy="metamodel" for its metamodel only; tag=<tag name or id> for the model as
    it was at that tag) or "child" (a copy linked to its parent, source, that can merge back). Copies of content are
    made straight away. Needs the right to create models."""
    from . import model_ops as mo
    from . import tags as tg

    def run(conn):
        who = _who()
        src = repo.get_model(conn, source)
        spec = {"kind": "project", "name": name, "description": description, "industry": industry, "source": str(src["id"]),
                "copy": "metamodel" if start == "empty" else copy}
        if start == "child":
            spec["parent"] = str(src["id"])
        if tag:
            if start == "child":
                raise EditError("A model made from a tag is a separate copy: use start=\"copy\".")
            found = [t for t in tg.list_tags(conn, str(src["id"])).get("tags", []) if tag in (str(t.get("id")), t.get("name"))]
            if not found:
                raise EditError(f"{src['name']} has no tag '{tag}'.")
            spec["tag"] = str(found[0]["id"])
        out = mo.create_model(conn, who.username, spec)
        for c in [out.get("_copy")] if out.get("_copy") else []:
            mo.run_copy(conn, c["source"], c["target"], who.username)
        audit.record(conn, actor=who.username, action="mcp.model.created", object_type="model",
                     object_id=str(out["model"]["id"]), source="mcp")
        m = repo.get_model(conn, str(out["model"]["id"]))
        return {"model": m["id"], "name": m["name"], "entities": m.get("entity_count"), "link": f"/#/metamodel/{m['id']}"}
    return await _run(run, begin=True)


@mcp.tool()
async def add_entities(model: str, entity_type: str, rows: list[dict]) -> Any:
    """Add entities of one type: rows [{name, description, parent, display_id, tags: [...], values: {attribute code:
    value}}] (up to 500). In a working model they are your uncommitted changes (see list_my_changes)."""
    from . import commits as cm
    from . import content as ct
    if len(rows) > 500:
        return {"error": "Add at most 500 rows at a time."}
    flat = [{**{k: v for k, v in r.items() if k != "values"}, **(r.get("values") or {})} for r in rows]

    def do(conn, who, m, commits):
        if commits:
            return cm.record_entity_rows(conn, str(m["id"]), entity_type, flat, who.username)
        return ct.bulk_entities(conn, str(m["id"]), entity_type, flat, who.username)
    return await _run(_content_change(model, do), begin=True)


@mcp.tool()
async def update_entity(model: str, entity: str, name: str | None = None, description: str | None = None,
                        values: dict | None = None, tags: list[str] | None = None) -> Any:
    """Change an entity's name, description, values {attribute code: value} or tags (only what you give)."""
    from . import commits as cm
    from . import content as ct
    data = {k: v for k, v in {"name": name, "description": description, "values": values, "tags": tags}.items() if v is not None}

    def do(conn, who, m, commits):
        if commits:
            return cm.record(conn, str(m["id"]), who.username, "entity.update", {"entity": entity, "data": data})
        return ct.update_entity(conn, str(m["id"]), entity, data, who.username)
    return await _run(_content_change(model, do), begin=True)


@mcp.tool()
async def add_relationships(model: str, rows: list[dict]) -> Any:
    """Relate entities: rows [{relationship_type, source, target, name}] (entities by name or guid; up to 1000).
    Check allowed_relationships first: a relationship the metamodel does not allow is refused."""
    from . import commits as cm
    from . import content as ct
    if len(rows) > 1000:
        return {"error": "Add at most 1000 relationships at a time."}

    def do(conn, who, m, commits):
        if commits:
            return cm.record_relationship_rows(conn, str(m["id"]), rows, who.username)
        return ct.bulk_relationships(conn, str(m["id"]), rows, who.username)
    return await _run(_content_change(model, do), begin=True)


@mcp.tool()
async def list_my_changes(model: str) -> Any:
    """Your uncommitted changes in a model (what you added or changed that is not yet part of it)."""
    from . import commits as cm
    return await _run(lambda conn: cm.changes_page(conn, model, _who()))


@mcp.tool()
async def commit_my_changes(model: str, message: str) -> Any:
    """Make your uncommitted changes part of the model, with a message (only when the person agrees). Needs the right
    to commit in that model; otherwise ask for a commit with request_my_commit."""
    from . import commits as cm
    return await _run(lambda conn: cm.commit(conn, model, _who(), message=message), begin=True)


@mcp.tool()
async def request_my_commit(model: str, note: str = "") -> Any:
    """Ask the model's committers to commit your changes (when you may not commit yourself)."""
    from . import commits as cm
    return await _run(lambda conn: cm.request_commit(conn, model, _who(), note=note), begin=True)


@mcp.tool()
async def tag_model(model: str, name: str, description: str = "") -> Any:
    """Tag a model as it is now (a baseline to compare with or copy from later)."""
    from . import tags as tg
    return await _run(lambda conn: tg.create_tag(conn, model, _who(), name, description), begin=True)


# ================================================================ projects
@mcp.tool()
async def list_projects() -> Any:
    """The architecture projects you are on (a Super Admin sees all): name, purpose, status, repository state."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.listing(pc, who))


@mcp.tool()
async def list_project_templates() -> Any:
    """The kinds of project (templates): what each is for, the models it needs (slots), its phases and viewpoints."""
    from . import project_templates as pt
    return await _proj(lambda pc, who: pt.listing(pc))


@mcp.tool()
async def get_project(project: str, part: str = "summary") -> Any:
    """A project by name or id. part: "summary" (models, goals, phases with steps done and documents), "steps",
    "documents", "classes" (deliverables and artifacts), "approvals", "viewpoints", "questions" (the key questions with
    their status, answer and what it points to, the viewpoints that answer each, and the placeholder viewpoints) or "all"."""
    from . import projects as pj

    def run(pc, who):
        d = pj.detail(pc, _project_id(pc, project), who)
        if part == "all":
            return d
        if part in ("steps", "documents", "viewpoints"):
            return {"project": d["name"], part: d[part]}
        if part == "questions":
            return {"project": d["name"], "questions": d["key_questions"], "placeholders": d["placeholder_viewpoints"]}
        if part == "classes":
            return {"project": d["name"], "classes": d["items"]}
        if part == "approvals":
            return {"project": d["name"], "approvals": d.get("signoffs"), "quorum": d.get("signoff_quorum")}
        phases = []
        for ph in d["phases"]:
            st = [s for s in d["steps"] if s["phase"] == ph["code"] and not s.get("parent") and not s["removed"]]
            items = [i for i in d["items"] if i["phase"] == ph["code"] and i["chosen"]]
            if st or items:
                phases.append({"phase": ph["code"], "name": ph["name"], "steps": len(st), "steps_done": len([s for s in st if s["done_at"]]),
                               "classes": len(items), "documents": sum(i.get("documents") or 0 for i in items)})
        return {"id": d["id"], "name": d["name"], "purpose": d.get("purpose"), "status": d.get("status"),
                "repository": d.get("repo_state"), "models": [{k: m.get(k) for k in ("id", "name", "how", "role", "home")} for m in d["models"]],
                "goals": d.get("goals"), "phases": phases, "link": f"/#/projects/{d['id']}"}
    return await _proj(run)


def _project_id(pc, project: str) -> str:
    from . import projects as pj
    try:
        return str(pj.project_row(pc, project)["guid"])
    except Exception:  # noqa: BLE001 - by name
        r = pj._one(pc, "SELECT guid::text AS g FROM proj.projects WHERE lower(name) = lower(:n)", n=project)
        if not r:
            raise EditError(f"No project called '{project}' (list_projects shows yours).", 404) from None
        return r["g"]


@mcp.tool()
async def create_project(name: str, template: str, models: list[dict], description: str = "", goals: list[dict] | None = None,
                         purpose: str = "", start: str = "", end: str = "") -> Any:
    """Create an architecture project from a template (list_project_templates). models: [{how: "referred" | "added" |
    "derived" | "created", role: "current" | "target" | "transition" | "scenario" | "reference" | "working-copy",
    model: <existing model, for referred/added>, start: "empty" | "copy" | "child", source: <model or root metamodel>,
    name: <new model's name, for derived/created>, tag: <optional, a separate copy at a tag>, home: true for the
    primary working model}]. goals: [{name, outcomes: [{name, measure, target_date}]}] (need a home model). Model
    copies are made straight away; the repository in Documents is built in the background."""
    from . import model_ops as mo
    from . import project_templates as pt
    from . import project_work as pw
    from . import projects as pj
    from .seed import sample_projects as sp

    def run(pc, who):
        core = pj.core(pc)
        tpl = pt.get(pc, template)
        links = []
        for m in models:
            how = m.get("how") or "referred"
            if how in ("referred", "added"):
                links.append({"how": how, "model": str(repo.get_model(core, m["model"])["id"]), "role": m.get("role") or "",
                              "home": bool(m.get("home"))})
            else:
                src = repo.get_model(core, m.get("source") or m.get("model") or "ArchiMate 4")
                st = m.get("start") or ("child" if how == "derived" else "copy" if src["kind"] != "template" else "empty")
                link = {"how": "derived" if st == "child" else "created", "start": st, "from": str(src["id"]),
                        "copy": "metamodel" if st == "empty" else (m.get("copy") or "content"), "name": m.get("name") or f"{name} {m.get('role') or 'model'}",
                        "role": m.get("role") or "", "home": bool(m.get("home"))}
                if m.get("tag"):
                    link["tag"] = m["tag"]
                links.append(link)
        body = sp.payload(pc, tpl, name, description, None, links, goals or [])
        body["members"] = [{"username": who.username, "role": "project-admin"}]
        body["signoff"] = {"": [who.username]}
        if purpose:
            body["purpose"] = purpose
        if start or end:
            body["scope"].update(start=start or body["scope"]["start"], end=end or body["scope"]["end"])
        out = pj.create(pc, who, body)
        for c in out.get("copies") or []:
            mo.run_copy(core, c["source"], c["target"], who.username)
        note = ""
        if out.get("copies"):
            note = pw.write_pending_goals(pc, out["project"]["id"], who)
        return {"project": out["project"]["id"], "name": name, "link": f"/#/projects/{out['project']['id']}",
                "models_copied": len(out.get("copies") or []), "note": " ".join(x for x in (out.get("note"), note) if x),
                "repository": "built in Documents by the background job within a minute or two"}
    return await _proj(run, write=True)


@mcp.tool()
async def add_project_step(project: str, phase: str, name: str, due_date: str = "") -> Any:
    """Add a step of the project's own to an ADM phase (P, A, B, C-D, C-A, D, E, F, G, H, RM), at any time."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.add_step(pc, _project_id(pc, project), who, {"phase": phase, "name": name, "due_date": due_date or None}), write=True)


@mcp.tool()
async def complete_project_step(project: str, step: int, done: bool = True, note: str = "") -> Any:
    """Mark a step done (who and when are kept as a sub step under it), or not done (done=false). Step ids are in
    get_project(part="steps")."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.mark_step(pc, _project_id(pc, project), who, int(step), done, note), write=True)


@mcp.tool()
async def save_key_question(project: str, question: str, asked_by: str = "", approach: str = "", viewpoints: list[str] | None = None,
                            question_id: str = "") -> Any:
    """Add a key question to a project (question_id empty) or change one (its id from get_project part "questions"):
    the stakeholder question the work answers, who asks it, the answer we expect or the approach, and the codes of the
    viewpoints that answer it (VP-, PV- or a placeholder's PH-; a library viewpoint is chosen for the project). A question
    may need several viewpoints and a viewpoint may answer several questions. Ask the person before saving."""
    from . import key_questions as kq
    body = {"question": question, "asked_by": asked_by, "approach": approach}
    if viewpoints is not None:
        body["viewpoints"] = viewpoints
    if question_id:
        return await _proj(lambda pc, who: kq.change_question(pc, _project_id(pc, project), who, question_id, body), write=True)
    return await _proj(lambda pc, who: kq.add_question(pc, _project_id(pc, project), who, body), write=True)


@mcp.tool()
async def answer_key_question(project: str, question_id: str, answer: str, documents: list[str] | None = None,
                              links: list[dict] | None = None, viewpoints: list[str] | None = None) -> Any:
    """Answer a key question (contributors): answer is a short summary of the answer, pointing to what holds it:
    documents (ids of the project's documents, from get_project part "documents"), links [{url, label}] and/or the
    viewpoints mapped to it (codes). At least one of them is needed. The question is then waiting for the stakeholder
    to accept it. Ask the person before saving."""
    from . import key_questions as kq
    body: dict = {"answer": answer}
    for k, v in (("documents", documents), ("links", links), ("viewpoints", viewpoints)):
        if v is not None:
            body[k] = v
    return await _proj(lambda pc, who: kq.answer(pc, _project_id(pc, project), who, question_id, body), write=True)


@mcp.tool()
async def key_question_decision(project: str, question_id: str, decision: str, note: str = "", stakeholder: str = "",
                                on: str = "") -> Any:
    """The stakeholder's decision on an answered key question: decision "accepted" or "rejected" (a rejection needs a
    note and opens the question again), or "reopen" (a contributor, with a note). With stakeholder empty the signed-in
    person decides as a project stakeholder; with stakeholder named, a contributor records a decision given outside
    the application (on: YYYY-MM-DD). Ask the person before saving."""
    from . import key_questions as kq

    def run(pc, who):
        pid = _project_id(pc, project)
        if decision == "reopen":
            return kq.reopen(pc, pid, who, question_id, note)
        if stakeholder:
            return kq.record(pc, pid, who, question_id, {"by": stakeholder, "on": on, "decision": decision, "note": note})
        return kq.decide(pc, pid, who, question_id, decision, note)
    return await _proj(run, write=True)


@mcp.tool()
async def business_model_canvas(project: str, canvas: str = "", compare_with: str = "") -> Any:
    """A project's Business Model Canvases: with canvas empty, the list (name, kind current | target | working |
    scenario, status); with a canvas id, its items block by block (a working copy's marks: added, changed with the old
    text, removed); with compare_with too, what changed from canvas to compare_with in each block."""
    from . import canvases as cv

    def run(pc, who):
        pid = _project_id(pc, project)
        if canvas and compare_with:
            return cv.compare(pc, pid, who, canvas, compare_with)
        return cv.get(pc, pid, who, canvas) if canvas else cv.listing(pc, pid, who)
    return await _proj(run)


@mcp.tool()
async def change_business_model_canvas(project: str, action: str, canvas: str = "", item: str = "", block: str = "",
                                       text: str = "", note: str = "", name: str = "", kind: str = "") -> Any:
    """Change a project's Business Model Canvases (contributors; ask the person first). action: "new" (name, kind),
    "add" (canvas, block, text, note), "change" (item, text, note, block), "remove" (item; crossed out in a working
    copy), "working-copy" (canvas, name), "clean" (canvas, name, kind: a clean canvas from a working copy). Blocks:
    key_partners, key_activities, key_resources, value_propositions, customer_relationships, channels,
    customer_segments, cost_structure, revenue_streams."""
    from . import canvases as cv

    def run(pc, who):
        pid = _project_id(pc, project)
        body = {k: v for k, v in {"name": name, "kind": kind, "block": block, "text": text, "note": note}.items() if v}
        if action == "new":
            return cv.create(pc, pid, who, body)
        if action == "add":
            return cv.add_item(pc, pid, who, canvas, body)
        if action == "change":
            return cv.change_item(pc, pid, who, item, body)
        if action == "remove":
            return cv.remove_item(pc, pid, who, item)
        if action == "working-copy":
            return cv.copy(pc, pid, who, canvas, {**body, "kind": "working"})
        if action == "clean":
            return cv.clean_up(pc, pid, who, canvas, body)
        raise EditError("action: new, add, change, remove, working-copy or clean")
    return await _proj(run, write=True)


@mcp.tool()
async def add_placeholder_viewpoint(project: str, name: str, kind: str = "text", file_type: str = "", description: str = "",
                                    questions: list[str] | None = None) -> Any:
    """A placeholder viewpoint where no viewpoint fits a key question: kind "text" (a name and what it will show) or
    "file" with file_type docx | pptx | xlsx | pdf | drawio | md | txt (an empty file is made in the project's files).
    questions: the ids of the key questions it answers. It stays in the project (code PH-<n>)."""
    from . import key_questions as kq

    def run(pc, who):
        pid = _project_id(pc, project)
        out = kq.add_placeholder(pc, pid, who, {"name": name, "kind": kind, "file_type": file_type, "description": description,
                                                "questions": questions or []})
        if out.get("kind") == "file":
            out["file"] = kq.make_files(pc, pid, who)["message"]
        return out
    return await _proj(run, write=True)


@mcp.tool()
async def list_stakeholders(project: str) -> Any:
    """A project's stakeholder matrix (TOGAF stakeholder management, D294): each stakeholder's category, power and
    interest (H/M/L), class (key players, keep satisfied, keep informed, minimal effort), position (ability to disrupt,
    understanding and commitment now and needed, support needed), concerns, engagement and last/next contact."""
    from . import stakeholders as sh
    return await _proj(lambda pc, who: sh.listing(pc, _project_id(pc, project), who))


@mcp.tool()
async def save_stakeholder(project: str, name: str, stakeholder: str = "", fields: dict | None = None) -> Any:
    """Add a stakeholder to a project (stakeholder empty) or change one (its id from list_stakeholders). fields:
    organisation, role_title, category (corporate | end-user | operations | project | outside), power and interest
    (H | M | L), class (only to override the grid: key | satisfied | informed | minimal), disrupt, understanding_now,
    understanding_needed, commitment_now, commitment_needed, support_needed (H | M | L), concerns, viewpoints [codes],
    approach, frequency, channel, owner, email, phone, next_contact (YYYY-MM-DD), notes_html. Ask the person before
    saving."""
    from . import stakeholders as sh
    body = {**(fields or {}), "name": name}
    if stakeholder:
        return await _proj(lambda pc, who: sh.update(pc, _project_id(pc, project), who, stakeholder, body), write=True)
    return await _proj(lambda pc, who: sh.add(pc, _project_id(pc, project), who, body), write=True)


@mcp.tool()
async def note_stakeholder_discussion(project: str, stakeholder: str, html: str, held_on: str = "", title: str = "") -> Any:
    """Note a discussion with a stakeholder (rich text html; held_on YYYY-MM-DD, today when empty). It becomes their
    last contact."""
    from . import stakeholders as sh
    return await _proj(lambda pc, who: sh.add_note(pc, _project_id(pc, project), who, stakeholder,
                                                   {"html": html, "held_on": held_on, "title": title}), write=True)


@mcp.tool()
async def repeat_project_step(project: str, step: int, due_date: str = "", note: str = "") -> Any:
    """The step is to be done again: opens a sub step under it, to complete later (complete_project_step on it)."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.add_substep(pc, _project_id(pc, project), who, int(step), {"due_date": due_date or None, "note": note}), write=True)


@mcp.tool()
async def add_document_class(project: str, phase: str, name: str, kind: str = "Artifact") -> Any:
    """A new class of document (a deliverable or artifact) in a phase of the project, e.g. "Capability heat map"."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.add_item(pc, _project_id(pc, project), who, {"phase": phase, "name": name, "kind": kind}), write=True)


@mcp.tool()
async def set_document_class_needed(project: str, item: str, needed: bool, reason: str = "") -> Any:
    """Mark a document class "won't need this" (needed=false, with a reason) or needed again. Ids from
    get_project(part="classes")."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.not_needed(pc, _project_id(pc, project), who, item, reason, undo=needed), write=True)


@mcp.tool()
async def set_document_tags(project: str, document: str, tags: list[str]) -> Any:
    """Set a project document's tags (replaces them). Document ids from get_project(part="documents")."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.set_tags(pc, _project_id(pc, project), who, document, tags), write=True)


@mcp.tool()
async def accept_document(project: str, document: str, evidence: str) -> Any:
    """Mark a document Accepted now, with the evidence (why: e.g. "agreed at the architecture forum on 6 Nov")."""
    from . import projects as pj
    return await _proj(lambda pc, who: pj.accept(pc, _project_id(pc, project), who, document, evidence), write=True)


@mcp.tool()
async def send_document_for_approval(project: str, document: str, note: str = "") -> Any:
    """Ask the phase's sign-off people to approve a document: approved when the quorum approves; any rejection
    rejects it."""
    from . import project_work as pw
    return await _proj(lambda pc, who: pw.raise_signoff(pc, _project_id(pc, project), who, document, note), write=True)

