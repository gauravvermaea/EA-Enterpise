"""Architecture projects (phase 13, D258 to D262).

GET    /projects                                   the projects you are on (a Super Admin: all)
POST   /projects                                   create one from the wizard's choices (any user with a global role)
GET    /projects/library                           what the wizard offers: purposes, phases, steps, deliverables and
                                                   artifacts, folders, templates, principles, viewpoints, roles
GET    /projects/<p>                               the project: people, sign-off, models, viewpoints, principles, steps,
                                                   items, documents, repository state
PUT    /projects/<p>/people                        {members: [{username, role}], signoff: {phase: [usernames]}}
POST   /projects/<p>/items/<i>/choose              {chosen: true|false}: bring a not_for_use item in, or put one out
POST   /projects/<p>/repository                    build the repository in Documents again
POST   /projects/<p>/items/<i>/documents           upload a document (multipart "file")
GET    /projects/<p>/documents/<d>                 download its latest version
GET    /projects/<p>/documents/<d>/history         who did what to it
GET    /projects/<p>/templates/<t>                 a template of the project's libraries, straight from the library
POST   /projects/<p>/steps/<s>/done                {done: true|false}: mark a step done or take the last completion back (contributors)
POST   /projects/<p>/documents/<d>/checkout        check it out to yourself
POST   /projects/<p>/documents/<d>/checkin         check in the new file (multipart "file", "comment" (required), "user_version")
POST   /projects/<p>/documents/<d>/undo-checkout   end a check-out without a new version
POST   /projects/library/templates/<id>/file       a TOGAF template's file (Super Admins; multipart "file")
POST   /projects/library/templates/load            store every matching file of the TOGAF folder (Super Admins)
POST   /projects/library/setup                     {shared: [library ids]}: the template library setup (Super Admins, D264)
POST   /projects/library/libraries                 a new template library from a zip (multipart "file", "name", "description")
GET    /projects/library/libraries/<l>/zip         the library as one zip in its folder layout
POST   /projects/library/libraries/<l>/share       {shared: true|false} (Super Admins)
POST   /projects/library/libraries/<l>/zip         the TOGAF templates as one zip, the I094 download as it is (Super Admins)

Phase 13.0.1 (D274 to D279):
PUT    /projects/<p>                               the edit workflow: the wizard's choices for a live project (background task)
POST   /projects/<p>/files                         a file of the project's own (a contract...; multipart "file")
POST   /projects/<p>/documents/<d>/kind            {kind: Deliverable|Artifact}
POST   /projects/<p>/documents/<d>/signoff         {note}: ask its signers to sign the current version off
POST   /projects/<p>/signoffs/<r>/decide           {decision: approved|rejected, comment}: a signer's own decision
POST   /projects/<p>/signoffs/<r>/record           a signer's decision given outside, with the evidence (multipart)
POST   /projects/<p>/viewpoints                    {name, purpose, concerns, stakeholders, element_types}: one of its own
POST   /projects/<p>/finish                        {mode: freeze|merge, target, models: {guid: keep|merge}, note} (background)

Phase 13.0.3 (D281, D282):
GET    /projects/templates                         the project templates (?all=true with retired ones)
POST   /projects/templates                         a new one; PUT /projects/templates/<code> changes or retires one
POST   /projects/<p>/as-template                   {name, description}: save a project's decisions as a template

The content framework (D299):
GET    /projects/<p>/content-framework             the areas and their numbers; GET .../<area> one area as a tree
GET    /repository/summary|governance/<kind>|people|model-levels   the organisation's repository views (D318)
GET    /projects/library/template-setup            the defaults: deliverables and artifacts, templates, their areas (D317)
GET    /projects/<p>/cf-tags                       tag items: rows of one kind with their areas; PUT places several at once
PUT    /projects/<p>/items/<i>/content-area        {area}: where a document type sits; .../documents/<d>/content-area: a document
PUT    /projects/library/items/<n>/content-area    {area}: a library document type (Super and Library Admins)

Phase 13.1 (D303-D307):
GET    /projects/bases                             the project hierarchy (bases, library projects, projects below each)
GET    /projects/<p>/base                          its bases and what its base offers; POST {kind, id, take} | {base}
GET    /projects/<p>/standards                     standards by area; POST adds; PUT/DELETE /standards/<s>
GET    /projects/<p>/governance                    the governance log; POST a record | {new_kind} | {remove_kind}; PUT/DELETE /governance/<r>
POST   /projects/<p>/governance/<r>/approval|evidence   send for approval, decide; approve with evidence (D321); GET .../history
GET    /projects/<p>/charter                       the architecture charter; PUT {sections, approve}

The project's organisation (D302): flat, no hierarchy
GET    /projects/<p>/organisation                  people and their role on the project; POST {name, role, username} | {members: true}
PUT    /projects/<p>/organisation/<id>             change one; DELETE takes one out

The organisation's reference library (phase 13.0.8, D300): everyone reads, Super Admins change
GET    /reference-library                          folders, tags, entries (?folder, q searches inside documents, tag, kind)
POST   /reference-library/folders | /links | /files  add; GET/PUT/DELETE /reference-library/<e>; POST .../versions; GET .../file

Tasks (D298): a scratchpad, no dates
GET    /projects/<p>/tasks                         tasks, statuses, people, steps; POST {title, notes_html, status, assigned_to, step_id}
PUT    /projects/<p>/tasks/<t>                     change one; DELETE deletes it
POST   /projects/<p>/task-statuses                 {name}: a status of the project's own; DELETE ?name= removes it

The stakeholder matrix (D294):
GET    /projects/<p>/stakeholders                  the matrix (?format=csv); POST adds one; POST .../order reorders
PUT    /projects/<p>/stakeholders/<s>              change one (the fields sent); DELETE takes it out
GET    /projects/<p>/stakeholders/<s>/notes        its discussion notes; POST {held_on, title, html} adds one
PUT    /projects/<p>/stakeholder-notes/<n>         change a discussion note; DELETE removes it
"""

from __future__ import annotations

import logging

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit
from .. import model_ops as mo
from .. import permissions as perms
from .. import project_work as pw
from .. import projects as pj
from .. import repository as repo
from ..auth import require_auth
from ..db import get_projects_engine
from ..mayan import MayanError
from ..metamodel_edit import EditError
from .models import Free, FreeIn

log = logging.getLogger(__name__)
blp = Blueprint("projects", __name__, url_prefix="/api/v1", description="Architecture projects")
SECURITY = [{"bearerAuth": []}]
MAX_UPLOAD = 200 * 1024 * 1024


def _run(fn, write=False, action: str | None = None, obj: str | None = None):
    """fn gets the projects' connection; the repository's is beside it in conn.info["core"] (the same connection while
    proj is in the repository's database, D266)."""
    try:
        with pj.connections(write) as conn:
            out = fn(conn)
            if action:
                audit.record(pj.core(conn), actor=g.user.username, action=action, object_type="project", object_id=str(obj or ""))
            return out
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404) if isinstance(exc, EditError) else 404, message=str(exc))
    except MayanError as exc:
        abort(exc.status, message=str(exc))


def _file():
    f = request.files.get("file")
    if not f:
        abort(400, message="Send the file as multipart \"file\".")
    data = f.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        abort(413, message="The file is larger than 200 MB.")
    return f.filename or "document", data


def _queue_repository(project_guid: str) -> None:
    """The repository is built in the background (the minute job also picks it up)."""
    try:
        with get_projects_engine().connect() as conn:
            pid = pj.project_row(conn, project_guid)["id"]
        from ..jobs import app as jobs_app
        from ..jobs import project_repository
        with jobs_app.open():
            project_repository.defer(project_id=pid)
    except Exception as exc:  # noqa: BLE001 - no job runner, or one already queued: the minute job builds it
        log.info("project repository not queued now (%s); the minute job builds it", exc)


@blp.route("/projects")
class Projects(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The architecture projects you are on (a Super Admin sees all)"""
        return _run(lambda c: {"projects": pj.listing(c, g.user), "may_create": pj.may_create(g.user), "setup": pj.setup_state(c),
                               "may_manage": perms.allowed(g.user.roles, "projects.library")})

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """Create a project from the wizard: name, purpose, description, parent (a rerun), libraries [template library
        ids, in order; default: every library offered to projects], models [{how: added|derived|
        created, model | from, name, copy}], viewpoints, principles [{library_id} | {name, statement, rationale,
        implications}], removed_steps [{library_id, reason}], own_steps [{phase, name}], items [library ids chosen; the
        rest come in as not_for_use], kinds {library id: Deliverable|Artifact}, own_items [{phase, name, kind}], members
        [{username, role}], signoff {phase or "": [usernames]}"""
        from .tasks import start, waiting
        if not waiting():   # D273, D267: the project, its model copies and its repository in the background
            def check(c):   # the quick checks now, so the wizard says at once what is wrong
                if not pj.may_create(g.user):
                    raise EditError("Creating a project needs a global role (User, Model Creator or Super Admin).", 403)
                if not pj.setup_state(c)["done"]:
                    raise EditError("A Super Admin finishes the template library setup first (Administration > Project library).", 409)
                pj._check_payload(c, data or {})
            _run(check)
            return start("project.created", None, f"Create the project '{(data or {}).get('name')}'", {"data": data or {}},
                         "#/project-admin")
        out = _run(lambda c: pj.create(c, g.user, data or {}), write=True, action="project.created", obj=(data or {}).get("name"))
        roles = list(g.user.roles)
        for c in out.pop("copies", []):          # model content copies, as for a new model
            try:
                from ..jobs import app as jobs_app
                from ..jobs import copy_model
                with jobs_app.open():
                    copy_model.defer(source=c["source"], target=c["target"], actor=g.user.username, roles=roles, publish=False)
            except Exception:  # noqa: BLE001 - no job runner: copy now
                _run(lambda conn, c=c: mo.run_copy(conn, c["source"], c["target"], g.user.username), write=True)
        _queue_repository(out["project"]["id"])
        return out


@blp.route("/projects/library")
class Library(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The project library: what the wizard offers"""
        def read(c):
            out = pj.library(c)
            out["libraries"] = pj.libraries(c, g.user)
            out["setup"] = pj.setup_state(c)
            return out
        out = _run(read)
        out["may_manage"] = perms.allowed(g.user.roles, "projects.library")
        out["folder_files"] = [str(p.relative_to(pj.LIBRARY_DIR)) for p in pj.templates_in_folder()]
        out["download"] = {"togaf": "https://publications.opengroup.org/i094",
                           "togaf_title": "The TOGAF Standard, 10th Edition: Template Deliverables (The Open Group I094)"}
        return out


@blp.route("/projects/library/templates/<int:template_id>/file")
class TemplateFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, template_id):
        """Download a library template's file (anyone the library is offered to)"""
        data, ctype, name = _run(lambda c: pj.library_template_file(c, g.user, template_id))
        from urllib.parse import quote
        return Response(data, mimetype=ctype or "application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, template_id):
        """Store a library template's file in Documents (Super Admins); TOGAF's: your licensed copy, unchanged"""
        name, data = _file()
        return _run(lambda c: pj.upload_template(c, g.user, template_id, name, data), write=True,
                    action="project.library.template", obj=template_id)


@blp.route("/repository/summary")
class OrgRepository(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The organisation's Architecture Repository map (D318): the Organisation base its links open"""
        from .. import org_repository as orp
        return _run(lambda c: orp.summary(c, g.user))


@blp.route("/repository/governance/<string:kind>")
class OrgGovernance(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, kind):
        """Read only, across the projects you are on: decisions, compliance or capability assessments (changed in each project)"""
        from .. import org_repository as orp
        return _run(lambda c: orp.governance(c, g.user, kind))


@blp.route("/repository/people")
class OrgPeople(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Read only, across the projects you are on: who works on them, their roles and skills"""
        from .. import org_repository as orp
        return _run(lambda c: orp.people(c, g.user))


@blp.route("/repository/model-levels")
class OrgModelLevels(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Each model's landscape level from its project's depth (Strategic, Segment, Capability) and its role there"""
        from .. import org_repository as orp
        return _run(lambda c: orp.model_levels(c, g.user))


@blp.route("/projects/library/template-setup")
class TemplateSetup(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Project admin › Template setup (D317): the deliverables and artifacts with their content framework areas, and one
        library's templates with their own areas (?library=guid). Super Admins and Library Admins"""
        from .. import content_framework as cf
        return _run(lambda c: cf.template_setup(c, g.user, request.args.get("library") or ""))


@blp.route("/projects/library/items/<int:item>/repository-area")
class LibraryItemRepositoryArea(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, item):
        """A deliverable's or artifact's Repository Area: {repository_area} ('' = built in; Super and Library Admins)"""
        from .. import content_framework as cf
        return _run(lambda c: cf.place_library_repo(c, g.user, item, (data or {}).get("repository_area") or ""), write=True,
                    action="project.library.repository_area", obj=str(item))


@blp.route("/projects/library/templates/<int:template_id>/content-area")
class TemplateContentArea(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, template_id):
        """A template's own content framework areas, over its deliverable's or artifact's: {areas} (Super and Library Admins)"""
        from .. import content_framework as cf
        return _run(lambda c: cf.place_library_template(c, g.user, template_id, _areas_in(data)), write=True,
                    action="project.library.content_area", obj=str(template_id))


@blp.route("/projects/library/libraries/<string:library>/templates")
class LibraryTemplateAdd(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, library):
        """Upload a new template into a library, tagged as it is uploaded: multipart file, item (the deliverable or artifact),
        areas (its own, codes with commas), class_areas (the deliverable's or artifact's, for every project; optional)"""
        from .. import content_framework as cf
        name, data = _file()
        f = request.form
        return _run(lambda c: cf.add_template(c, g.user, library, f.get("item") or None, name, data, f.get("areas") or "",
                                              f.get("class_areas") if "class_areas" in f else None),
                    write=True, action="project.library.template", obj=library)


@blp.route("/projects/library/templates/load")
class TemplatesLoad(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self):
        """Store every file of the library folder (library/templates) that matches a library template (Super Admins)"""
        return _run(lambda c: pj.load_templates_from_folder(c, g.user), write=True, action="project.library.load")


def _queue_library(library_id: int) -> None:
    try:
        from ..jobs import app as jobs_app
        from ..jobs import template_library_load
        with jobs_app.open():
            template_library_load.defer(library_id=library_id)
    except Exception as exc:  # noqa: BLE001 - the minute job stores it
        log.info("template library not queued now (%s); the minute job stores it", exc)


@blp.route("/projects/library/setup")
class Setup(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Finish the template library setup: the libraries offered to projects (Super Admins; before the first project)"""
        return _run(lambda c: pj.finish_setup(c, g.user, (data or {}).get("shared") or []), write=True, action="project.library.setup")


@blp.route("/projects/library/libraries")
class Libraries(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self):
        """A new template library from a zip in the library's folder layout; private until a Super Admin shares it"""
        f = request.files.get("file")
        if not f:
            abort(400, message="Send the zip as multipart \"file\".")
        data = f.read(pj.MAX_LIBRARY_ZIP + 1)
        out = _run(lambda c: pj.add_library(c, g.user, request.form.get("name", ""), data, request.form.get("description", "")),
                   write=True, action="project.library.add", obj=request.form.get("name", ""))
        _queue_library(out.pop("library_id"))
        return out


@blp.route("/projects/library/libraries/<string:library>/zip")
class LibraryZip(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, library):
        """The whole template library as one zip in its folder layout (to rebrand and upload as your own).
        ?background=true: made in the background (D273), downloaded from the task"""
        if request.args.get("background") == "true":
            from .tasks import start
            return start("project.library_zip", None, "Download a template library (zip)", {"library": library},
                         "#/project-admin/library")
        data, name = _run(lambda c: pj.library_zip(c, g.user, library))
        return Response(data, mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, library):
        """Upload the TOGAF template deliverables as one zip (the I094 download as it is; Super Admins)"""
        f = request.files.get("file")
        if not f:
            abort(400, message="Send the zip as multipart \"file\".")
        data = f.read(pj.MAX_LIBRARY_ZIP + 1)
        out = _run(lambda c: pj.add_library_zip(c, g.user, library, data), write=True, action="project.library.togaf", obj=library)
        _queue_library(out.pop("library_id"))
        return out


@blp.route("/projects/library/libraries/<string:library>/templates")
class LibraryTemplates(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, library):
        """A template library's files by folder, to look through (read only)"""
        return _run(lambda c: pj.library_templates(c, g.user, library))


@blp.route("/projects/library/libraries/<string:library>/share")
class LibraryShare(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, library):
        """Offer a template library to every project, or stop offering it (Super Admins)"""
        return _run(lambda c: pj.share_library(c, g.user, library, bool((data or {}).get("shared"))), write=True,
                    action="project.library.share", obj=library)


@blp.route("/projects/<string:project>")
class Project(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """One project (its people, Super Admins)"""
        return _run(lambda c: pj.detail(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project):
        """The edit workflow (D275): the project as it should be, from the wizard (Project Admin, Lead Architect). In the
        background (its new model copies and repository folders); ?wait=true in the request"""
        from .tasks import start, waiting
        if not waiting():
            p = _run(lambda c: pw.need(c, pj.project_row(c, project), g.user, "admin") and pj.project_row(c, project))
            return start("project.updated", None, f"Change the project '{p['name']}'", {"project": str(p["guid"]), "data": data or {}},
                         f"#/projects/{p['guid']}")
        return _run(lambda c: pw.update(c, g.user, project, data or {}), write=True, action="project.updated", obj=project)


@blp.route("/projects/templates")
class ProjectTemplates(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The project templates (D282); ?all=true with the retired ones"""
        from .. import project_templates as pt
        return {"templates": _run(lambda c: pt.listing(c, request.args.get("all") == "true")), "roles": __import__("eax.project_templates", fromlist=["x"]).ROLES}

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """A new project template (Super Admins, Library Admins)"""
        from .. import project_templates as pt
        return _run(lambda c: pt.save(c, g.user, None, data or {}), write=True, action="project.template.add", obj=(data or {}).get("name"))


@blp.route("/projects/templates/<string:code>")
class ProjectTemplate(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, code):
        """Change a project template, or retire it ({retired: true})"""
        from .. import project_templates as pt
        return _run(lambda c: pt.save(c, g.user, code, data or {}), write=True, action="project.template.change", obj=code)


@blp.route("/projects/<string:project>/as-template")
class AsTemplate(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Save the project's decisions as a new project template (Super Admins, Library Admins)"""
        from .. import project_templates as pt
        return _run(lambda c: pt.from_project(c, g.user, project, data or {}), write=True, action="project.template.add", obj=project)


@blp.route("/projects/<string:project>/files")
class ProjectFiles(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self, project):
        """A file of the project's own: a contract, a statement of work... (00_Project/Project files)"""
        name, data = _file()
        return _run(lambda c: pw.upload_project_file(c, project, g.user, name, data), write=True, action="project.file", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>/kind")
class DocKind(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, doc):
        """Mark a document a deliverable (signed off) or an artifact"""
        return _run(lambda c: pw.set_document_kind(c, project, g.user, doc, (data or {}).get("kind")), write=True,
                    action="project.document.kind", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/accept")
class DocAccept(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def post(self, project, doc):
        """Accept a document directly (D290), multipart: note (the evidence, required) and an optional evidence file"""
        f = request.files.get("evidence")
        data = f.read(MAX_UPLOAD + 1) if f else b""
        if len(data) > MAX_UPLOAD:
            abort(413, message="The file is larger than 200 MB.")
        return _run(lambda c: pj.accept(c, project, g.user, doc, request.form.get("note", ""), f.filename if f else "", data),
                    write=True, action="project.document.accept", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/<any(archive,delete):how>")
class DocHide(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, doc, how):
        """Archive or delete a document with all its versions; {undo: true} restores it (D290)"""
        return _run(lambda c: pj.set_hidden(c, project, g.user, doc, how, bool((data or {}).get("undo"))), write=True,
                    action=f"project.document.{how}", obj=doc)


@blp.route("/projects/<string:project>/documents")
class DocList(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project):
        """The project's documents; ?show=archived,deleted adds those (they are not loaded otherwise)"""
        show = tuple(x for x in (request.args.get("show") or "").split(",") if x in ("archived", "deleted"))

        def run(c):
            from .. import references as rf
            p = pj.project_row(c, project)
            pj._need(c, p, g.user, "read")
            docs = pj.documents(c, p, show)
            rf.targets(c, g.user, docs)          # links to other projects' documents keep their target (review)
            return {"documents": docs}
        return _run(run)


@blp.route("/projects/<string:project>/documents/<string:doc>/tags")
class DocTags(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, doc):
        """Set a document's tags (D290): {tags: [..]}, anyone who contributes to the project"""
        return _run(lambda c: pj.set_tags(c, project, g.user, doc, (data or {}).get("tags") or []), write=True,
                    action="project.document.tags", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/signoff")
class RaiseSignoff(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project, doc):
        """Ask the signers to sign off the document's current version (they are told in the application)"""
        return _run(lambda c: pw.raise_signoff(c, project, g.user, doc, (data or {}).get("note", "")), write=True,
                    action="project.signoff.raised", obj=doc)


@blp.route("/projects/<string:project>/signoffs/<string:request_id>/decide")
class DecideSignoff(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, request_id):
        """A signer approves or rejects (a comment is needed to reject)"""
        d = data or {}
        return _run(lambda c: pw.decide_signoff(c, project, g.user, request_id, d.get("decision"), d.get("comment", "")), write=True,
                    action="project.signoff.decided", obj=request_id)


@blp.route("/projects/<string:project>/signoffs/<string:request_id>/record")
class RecordSignoff(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, request_id):
        """Record a signer's decision given outside the application, with the evidence (multipart: signer, decision,
        comment, file)"""
        name, data = _file()
        f = request.form
        return _run(lambda c: pw.record_signoff(c, project, g.user, request_id, f.get("signer", ""), f.get("decision", ""),
                                                f.get("comment", ""), name, data), write=True, action="project.signoff.recorded", obj=request_id)


@blp.route("/projects/<string:project>/viewpoints")
class ProjectViewpoints(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """A viewpoint made for the project (contributors): code PV-<n>"""
        return _run(lambda c: pw.add_viewpoint(c, project, g.user, data or {}), write=True, action="project.viewpoint", obj=project)


@blp.route("/projects/<string:project>/viewpoints/<string:code>/phase")
class ProjectViewpointPhase(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, code):
        """The phase the project shows a viewpoint with: {phase} (empty: its usual one)"""
        return _run(lambda c: pw.set_viewpoint_phase(c, project, g.user, code, (data or {}).get("phase") or ""), write=True,
                    action="project.viewpoint.phase", obj=project)


@blp.route("/projects/<string:project>/finish")
class Finish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """Finish the project (Project Admin, Lead Architect): freeze it (read only), or merge it into another project
        (documents copied into its repository); each model kept as it is or merged into its parent model. In the
        background; ?wait=true in the request"""
        from .tasks import start, waiting
        d = data or {}
        if not waiting():
            p = _run(lambda c: pw.finish_check(c, project, g.user, d))
            return start("project.finished", None, f"{'Merge' if d.get('mode') == 'merge' else 'Freeze'} the project '{p['name']}'",
                         {"project": str(p["guid"]), "data": d}, f"#/projects/{p['guid']}")
        return _run(lambda c: pw.finish(c, project, g.user, d), write=True, action="project.finished", obj=project)


@blp.route("/projects/<string:project>/people")
class People(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project):
        """The people and who signs off (Project Admin, Lead Architect)"""
        return _run(lambda c: pj.set_people(c, project, g.user, (data or {}).get("members") or [], (data or {}).get("signoff") or {},
                                            (data or {}).get("signoff_quorum", "keep")),
                    write=True, action="project.people", obj=project)


@blp.route("/projects/<string:project>/items/<string:item>/choose")
class Choose(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, item):
        """Bring a not_for_use item into use, or put one out of use"""
        return _run(lambda c: pj.choose_item(c, project, g.user, item, bool((data or {}).get("chosen"))), write=True,
                    action="project.item", obj=project)


@blp.route("/projects/<string:project>/items")
class Items(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """A new document class in a phase: {phase, name, kind, type, note} (anyone on the project, D290)"""
        out = _run(lambda c: pj.add_item(c, project, g.user, data or {}), write=True, action="project.item.add", obj=project)
        _queue_repository(project)     # the folder is made in Documents (the minute job does it too)
        return out


@blp.route("/projects/<string:project>/items/<string:item>/not-needed")
class NotNeeded(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, item):
        """Mark a document class "won't need this" ({reason}), or bring it back ({undo: true})"""
        d = data or {}
        return _run(lambda c: pj.not_needed(c, project, g.user, item, d.get("reason", ""), bool(d.get("undo"))), write=True,
                    action="project.item.not_needed", obj=project)


@blp.route("/projects/<string:project>/repository")
class Repository(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, project):
        """Build the project's repository in Documents again: a background task (it shows in the task drawer)"""
        from .tasks import start, waiting
        out = _run(lambda c: pj.retry_repository(c, project, g.user), write=True)
        if not waiting():
            name = _run(lambda c: pj.project_row(c, project)["name"])
            return start("project.repository", None, f"Build the repository of '{name}'",
                         {"project": out["id"], "project_id": out["project_id"], "name": name}, f"#/projects/{out['id']}")
        _queue_repository(out["id"])
        return {"message": "The repository is being built in Documents."}


def _admin_project(c, project):
    """The project, when you look after its backups: its Project Admin or Lead Architect, IT or a Super Admin (a finished
    or frozen project too: backing it up changes nothing)."""
    from .. import project_backup as pb
    p = pj.project_row(c, project)
    pb.need_manage(c, p, g.user)
    return p


@blp.route("/projects/<string:project>/backups")
class ProjectBackups(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The project's backups (each with its models and documents)"""
        from .. import project_backup as pb
        return _run(lambda c: pb.list_backups(c, g.user, project))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, project):
        """Back up the project now, with its models and documents (Project Admin): a background task. {why}"""
        from .tasks import start
        p = _run(lambda c: _admin_project(c, project))
        return start("project.backup", None, f"Back up the project '{p['name']}'", {"project": str(p["guid"]), "why": (data or {}).get("why", "")},
                     f"#/projects/{p['guid']}/about")


@blp.route("/projects/<string:project>/backups/<string:file>")
class ProjectBackup(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, file):
        """Download a project backup file"""
        from .. import project_backup as pb
        p = _run(lambda c: _admin_project(c, project))
        f = pb.path_of(str(p["guid"]), file)
        return Response(f.read_bytes(), mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{file}"'})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, file):
        """Delete a project backup file (Project Admin)"""
        from .. import project_backup as pb
        return _run(lambda c: pb.delete_backup(c, g.user, project, file))


@blp.route("/projects/<string:project>/backups/<string:file>/restore")
class ProjectBackupRestore(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, project, file):
        """Restore a project backup as a NEW project (with its models and documents): a background task. {name}.
        {over: true} (Super Admin): the project, its own models and its documents put back over themselves instead"""
        from .. import project_backup as pb
        from .tasks import start
        p = _run(lambda c: _admin_project(c, project))
        over = bool((data or {}).get("over"))
        if over and perms.SUPER_ADMIN not in g.user.roles:
            abort(403, message="Putting a project back over itself needs the Super Admin role.")
        if not over and not pb.may_restore_new(g.user):
            abort(403, message="Restoring a project makes a new one: it needs the right to create projects (or IT).")
        return start("project.restore", None, f"Put '{p['name']}' back as it was" if over else f"Restore '{p['name']}' as a new project",
                     {"project": str(p["guid"]), "file": file, "name": (data or {}).get("name", ""), "over": over},
                     f"#/projects/{p['guid']}" if over else "#/work")


@blp.route("/projects/restore")
class ProjectRestoreUpload(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def post(self):
        """Restore a project backup file you upload (from this installation or another) as a new project. Multipart: file, name"""
        from .. import project_backup as pb
        from .tasks import start
        f = request.files.get("file")
        if not f or not f.filename.endswith(pb.SUFFIX):
            abort(400, message=f"Choose a project backup file ({pb.SUFFIX}).")
        if not pb.may_restore_new(g.user):
            abort(403, message="Restoring a project makes a new one: it needs the right to create projects (or IT).")
        up = pb.folder() / "_uploads"
        up.mkdir(parents=True, exist_ok=True)
        import uuid as _uuid
        name = f"{_uuid.uuid4().hex}{pb.SUFFIX}"
        f.save(up / name)
        return start("project.restore", None, f"Restore the project from {f.filename}", {"upload": name, "name": request.form.get("name", "")},
                     "#/work")


@blp.route("/projects/<string:project>/items/<string:item>/documents")
class Upload(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self, project, item):
        """Add a document to an item: multipart "file" (optional), "title" (its name, apart from the file's name), "kind"
        (Deliverable, Artifact or None; empty: the class's). With no file and a title it is planned: its file comes later"""
        f = request.files.get("file")
        if f:
            name, data = _file()
        else:
            name, data = "", b""
        return _run(lambda c: pj.upload(c, project, g.user, item, name, data, request.form.get("user_version", ""),
                                        request.form.get("title", ""), request.form.get("kind") or None), write=True,
                    action="project.document.upload", obj=project)


@blp.route("/projects/<string:project>/items/<string:item>/documents/from-templates")
class FromTemplates(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project, item):
        """Documents of a class made from templates: {documents: [{template: id, title: name}], kind}: any number, the same
        template more than once if wanted; a library not yet in the project joins it"""
        data = data or {}
        return _run(lambda c: pj.from_templates(c, project, g.user, item, data.get("documents") or [], data.get("kind") or None),
                    write=True, action="project.document.from_templates", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>/file")
class AddFile(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, doc):
        """The first file of a planned document (multipart "file", "user_version")"""
        name, data = _file()
        return _run(lambda c: pj.add_file(c, project, g.user, doc, name, data, request.form.get("user_version", "")), write=True,
                    action="project.document.file", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>/title")
class DocTitle(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, doc):
        """A document's name, apart from its file's name: {title}"""
        return _run(lambda c: pj.set_title(c, project, g.user, doc, (data or {}).get("title") or ""), write=True,
                    action="project.document.renamed", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>")
class Download(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, doc):
        """Download the document's latest version"""
        data, ctype, name = _run(lambda c: pj.download(c, project, g.user, doc))
        from urllib.parse import quote  # any name, in UTF-8 (review, 8 Nov 2026)
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@blp.route("/projects/<string:project>/templates/<int:template>")
class TemplateDownload(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, template):
        """Download a template of the project's libraries"""
        data, ctype, name = _run(lambda c: pj.template_download(c, project, g.user, template))
        from urllib.parse import quote  # any name, in UTF-8 (review, 8 Nov 2026)
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@blp.route("/projects/<string:project>/steps/<int:step>/done")
class StepDone(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, step):
        """Mark a step done, or reopen it"""
        return _run(lambda c: pj.mark_step(c, project, g.user, step, bool((data or {}).get("done")), (data or {}).get("note", "")), write=True,
                    action="project.step", obj=project)


@blp.route("/projects/<string:project>/steps")
class StepAdd(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """Add a step of the project's own at any time: {phase, name, due_date}"""
        return _run(lambda c: pj.add_step(c, project, g.user, data or {}), write=True, action="project.step.added", obj=project)


@blp.route("/projects/<string:project>/steps/<int:step>/sub")
class StepSub(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, step):
        """+ sub step: the step is to be done again, completed later: {due_date, note}"""
        return _run(lambda c: pj.add_substep(c, project, g.user, step, data or {}), write=True, action="project.step.sub", obj=project)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, step):
        """Take an open sub step away"""
        return _run(lambda c: pj.delete_substep(c, project, g.user, step), write=True, action="project.step.sub_deleted", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>/history")
class History(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, doc):
        """Who did what to the document"""
        return {"events": _run(lambda c: pj.history(c, project, g.user, doc))}


@blp.route("/projects/<string:project>/documents/<string:doc>/versions")
class Versions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, doc):
        """The document's versions only, newest first: number, your version, who, when, what changed (D312)"""
        return {"versions": _run(lambda c: pj.versions(c, project, g.user, doc))}


@blp.route("/projects/<string:project>/documents/<string:doc>/versions/<int:version>")
class VersionDownload(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, doc, version):
        """Download one version of the document (1 = the first)"""
        from urllib.parse import quote
        data, ctype, name = _run(lambda c: pj.download_version(c, project, g.user, doc, version))
        return Response(data, mimetype=ctype or "application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@blp.route("/projects/<string:project>/items/<string:item>/templates")
class ClassTemplates(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, item):
        """A template added to a document class to download: {template, remove} (its library joins the project)"""
        data = data or {}
        return _run(lambda c: pj.offer_template(c, project, g.user, item, int(data.get("template") or 0), bool(data.get("remove"))),
                    write=True, action="project.class.template", obj=project)


@blp.route("/projects/<string:project>/repo-tags")
class RepoTags(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The tags on the project's whole repository (D312)"""
        from .. import repo_tags as rt
        return _run(lambda c: rt.listing(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Tag the whole repository now: {name, note}: every document at its current version"""
        from .. import repo_tags as rt
        data = data or {}
        return _run(lambda c: rt.add(c, project, g.user, data.get("name") or "", data.get("note") or ""), write=True,
                    action="project.repo_tag", obj=project)


@blp.route("/projects/<string:project>/repo-tags/<string:tag>")
class RepoTag(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, tag):
        """The documents at the tag, their version then and now, and the documents added since"""
        from .. import repo_tags as rt
        return _run(lambda c: rt.detail(c, project, g.user, tag))

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, tag):
        """Remove a tag (the documents are not changed): a Project Admin or Lead Architect"""
        from .. import repo_tags as rt
        return _run(lambda c: rt.delete(c, project, g.user, tag), write=True, action="project.repo_tag.delete", obj=project)


@blp.route("/projects/<string:project>/repo-tags/<string:tag>/revert")
class RepoTagRevert(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, project, tag):
        """Bring the repository back to the tag (a background task): a tag "before application of tag <name>" first"""
        from .tasks import start

        def check(c):          # refused at once, not later in the task drawer (review, 8 Nov 2026)
            from .. import repo_tags as rt
            p = pj.project_row(c, project)
            pj._need(c, p, g.user, "admin")
            rt._tag(c, p, tag)
            return p["name"]
        name = _run(check)
        return start("project.repo_revert", None, f"Bring '{name}' back to a tag", {"project": project, "tag": tag},
                     f"#/projects/{project}/home")


@blp.route("/projects/<string:project>/repo-zip")
class RepoZip(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project):
        """Every document in one zip, a folder per class: ?tag= as at a tag, ?item= one class, neither: the whole repository
        as it is now. ?background=true: made in the background, downloaded from the task"""
        tag, item = request.args.get("tag", ""), request.args.get("item", "")
        if request.args.get("background") == "true":
            from .tasks import start
            return start("project.repo_zip", None, "Download documents (zip)", {"project": project, "tag": tag, "item": item},
                         f"#/projects/{project}/home")
        from .. import repo_tags as rt
        data, name = _run(lambda c: rt.zip_documents(c, project, g.user, tag, item))
        from urllib.parse import quote
        return Response(data, mimetype="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@blp.route("/projects/<string:project>/documents/<string:doc>/checkout")
class CheckOut(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, doc):
        """Check the document out to yourself: nothing is asked (D290)"""
        return _run(lambda c: pj.check_out(c, project, g.user, doc, (data or {}).get("user_version", "")), write=True,
                    action="project.document.checkout", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/checkin")
class CheckIn(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, doc):
        """Check in the new file as the next version"""
        name, data = _file()
        comment = request.form.get("comment", "")
        uv = request.form.get("user_version", "")
        return _run(lambda c: pj.check_in(c, project, g.user, doc, name, data, comment, uv), write=True,
                    action="project.document.checkin", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/undo-checkout")
class UndoCheckOut(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, doc):
        """End a check-out without a new version (who checked out; Lead Architect, Model Admin, Project Admin, Super Admin)"""
        return _run(lambda c: pj.undo_check_out(c, project, g.user, doc), write=True, action="project.document.undo_checkout", obj=doc)


# ---------------------------------------------------------------- the content framework (D299)
@blp.route("/projects/<string:project>/content-framework")
class ContentFramework(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The content framework's areas with, for each, the entity types and entities, document types and documents placed there"""
        from .. import content_framework as cf
        return _run(lambda c: cf.overview(c, project, g.user))


@blp.route("/projects/<string:project>/content-framework/<string:area>")
class ContentFrameworkArea(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, area):
        """One area as a tree: the project's models, their entity types placed here and their entities; the document types
        placed here and their documents. area _unplaced: what is not placed anywhere"""
        from .. import content_framework as cf
        return _run(lambda c: cf.area(c, project, g.user, area))


@blp.route("/projects/<string:project>/cf-tags")
class ContentFrameworkTags(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """Tag items: the project's deliverables and artifacts (kind=classes), documents, entity types (types) or entities with
        their content framework areas. q finds, phase and area (_none = not placed, _changed = changed from the default) filter"""
        from .. import content_framework as cf
        a = request.args
        try:
            off = max(0, int(a.get("offset") or 0))
        except ValueError:
            off = 0
        return _run(lambda c: cf.tag_list(c, project, g.user, a.get("kind") or "classes", a.get("q") or "", a.get("phase") or "",
                                          a.get("area") or "", off))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project):
        """Areas for several rows at once: {kind, ids, how: set|add|remove|reset, areas}"""
        from .. import content_framework as cf
        d = data or {}
        return _run(lambda c: cf.place(c, project, g.user, d.get("kind") or "", d.get("ids") or [], d.get("how") or "", d.get("areas")),
                    write=True, action="project.content_area", obj=project)


def _areas_in(data) -> object:
    """{areas: [...]} (several areas, D309) or {area: "code"}; empty = none chosen."""
    data = data or {}
    return data["areas"] if "areas" in data else (data.get("area") or "")


@blp.route("/projects/<string:project>/items/<string:item>/content-area")
class ItemContentArea(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, item):
        """Where a document type sits in the content framework: {area} ('' = its default)"""
        from .. import content_framework as cf
        return _run(lambda c: cf.place_item(c, project, g.user, item, _areas_in(data)), write=True,
                    action="project.content_area", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>/content-area")
class DocumentContentArea(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, doc):
        """A document placed in the content framework on its own: {area} ('' = under its document type only)"""
        from .. import content_framework as cf
        return _run(lambda c: cf.place_document(c, project, g.user, doc, _areas_in(data)), write=True,
                    action="project.content_area", obj=project)


@blp.route("/projects/library/items/<int:item>/content-area")
class LibraryItemContentArea(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, item):
        """Where a document type of the project library sits in the content framework: {area} (Super and Library Admins)"""
        from .. import content_framework as cf
        return _run(lambda c: cf.place_library_item(c, g.user, item, _areas_in(data)), write=True,
                    action="project.library.content_area", obj=str(item))


# ---------------------------------------------------------------- the project's organisation (D302)
@blp.route("/projects/<string:project>/organisation")
class ProjectOrg(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """Who works on the project and their role on it (flat: no hierarchy)"""
        from .. import project_org as po
        return _run(lambda c: po.listing(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a person: {name, role, username}; {members: true} adds the project's members not listed yet; {stakeholders: true
        or [ids]} adds stakeholders of the matrix;
        {order: [ids]} reorders"""
        from .. import project_org as po
        d = data or {}
        if d.get("members"):
            return _run(lambda c: po.add_members(c, project, g.user), write=True, action="project.org.changed", obj=project)
        if d.get("stakeholders"):           # true: all not listed yet; or a list of stakeholder ids
            ids = d["stakeholders"] if isinstance(d["stakeholders"], list) else None
            return _run(lambda c: po.add_stakeholders(c, project, g.user, ids), write=True, action="project.org.changed", obj=project)
        if "order" in d:
            return _run(lambda c: po.reorder(c, project, g.user, d.get("order") or []), write=True)
        return _run(lambda c: po.add(c, project, g.user, d), write=True, action="project.org.changed", obj=project)


@blp.route("/projects/<string:project>/organisation/<string:pid>")
class ProjectOrgPerson(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, pid):
        """Change a person (the fields sent)"""
        from .. import project_org as po
        return _run(lambda c: po.update(c, project, g.user, pid, data or {}), write=True, action="project.org.changed", obj=project)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, pid):
        """Take a person out"""
        from .. import project_org as po
        return _run(lambda c: po.delete(c, project, g.user, pid), write=True, action="project.org.changed", obj=project)


# ---------------------------------------------------------------- phase 13.1: bases, standards, governance log, charter (D303-D307)
@blp.route("/projects/bases")
class ProjectBases(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The project hierarchy: the bases (Empty, TOGAF 10, Organisation) and the library projects, with the projects below each"""
        from .. import project_bases as pb
        return _run(lambda c: pb.tree(c, g.user))


@blp.route("/projects/<string:project>/base")
class ProjectBase(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """What the project derives from (the chain of bases) and what its base offers it"""
        from .. import project_bases as pb
        return _run(lambda c: pb.view(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """{kind, id, take: true|false}: take or skip what the base offers (id '*': all); {base}: derive from another base
        or library project (Super Admins)"""
        from .. import project_bases as pb
        d = data or {}
        if d.get("base"):
            return _run(lambda c: pb.rebase(c, project, g.user, d["base"]), write=True, action="project.rebased", obj=project)
        return _run(lambda c: pb.decide(c, project, g.user, d.get("kind") or "*", d.get("id") or "*", bool(d.get("take", True))),
                    write=True, action="project.base.taken", obj=project)


@blp.route("/projects/<string:project>/standards")
class ProjectStandards(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The project's standards by area"""
        from .. import standards as st
        return _run(lambda c: st.listing(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a standard: {area, name, description, status, source}"""
        from .. import standards as st
        return _run(lambda c: st.add(c, project, g.user, data or {}), write=True, action="project.standard.added", obj=project)


@blp.route("/projects/<string:project>/standards/<string:sid>")
class ProjectStandard(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, sid):
        """Change a standard (not one mandatory from the base)"""
        from .. import standards as st
        return _run(lambda c: st.update(c, project, g.user, sid, data or {}), write=True, action="project.standard.changed", obj=project)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, sid):
        """Take a standard out (not one mandatory from the base)"""
        from .. import standards as st
        return _run(lambda c: st.delete(c, project, g.user, sid), write=True, action="project.standard.removed", obj=project)


@blp.route("/projects/<string:project>/governance")
class ProjectGovernance(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The governance log: records of every kind, the kinds (each a tab), principles and standards to point at"""
        from .. import governance as gv
        return _run(lambda c: gv.listing(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Log a record: {kind, title, html, status, owner, raised_on, expires_on, principle, standard, related}; or a new kind:
        {new_kind: {name, prefix, statuses[]}}; or remove a kind of one's own: {remove_kind: name}"""
        from .. import governance as gv
        d = data or {}
        if d.get("new_kind"):
            return _run(lambda c: gv.add_kind(c, project, g.user, d["new_kind"]), write=True, action="project.governance.kind", obj=project)
        if d.get("remove_kind"):
            return _run(lambda c: gv.delete_kind(c, project, g.user, d["remove_kind"]), write=True, action="project.governance.kind", obj=project)
        return _run(lambda c: gv.add(c, project, g.user, d), write=True, action="project.governance.logged", obj=project)


@blp.route("/projects/<string:project>/governance/<string:rid>")
class ProjectGovernanceRecord(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, rid):
        """Change a record of the governance log"""
        from .. import governance as gv
        return _run(lambda c: gv.update(c, project, g.user, rid, data or {}), write=True, action="project.governance.changed", obj=project)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, rid):
        """Take a record out (Project Admin, Lead Architect)"""
        from .. import governance as gv
        return _run(lambda c: gv.delete(c, project, g.user, rid), write=True, action="project.governance.removed", obj=project)


@blp.route("/projects/<string:project>/governance/<string:rid>/approval")
class ProjectGovernanceApproval(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, rid):
        """Approval of a record (D321): {action: send, note} asks the project's sign-off people; {action: approve|reject,
        comment} is a sign-off person's decision (a rejection needs a comment)"""
        from .. import governance as gv
        d = data or {}
        if d.get("action") == "send":
            return _run(lambda c: gv.send_for_approval(c, project, g.user, rid, d.get("note") or ""), write=True,
                        action="project.governance.approval_asked", obj=project)
        if d.get("action") in ("approve", "reject"):
            return _run(lambda c: gv.decide(c, project, g.user, rid, "approved" if d["action"] == "approve" else "rejected", d.get("comment") or ""),
                        write=True, action="project.governance.approval_decided", obj=project)
        abort(400, message="action is send, approve or reject.")


@blp.route("/projects/<string:project>/governance/<string:rid>/evidence")
class ProjectGovernanceEvidence(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, rid):
        """Approve a record with evidence (anyone who contributes): multipart reason and/or file"""
        from .. import governance as gv
        f = request.files.get("file")
        name, data = (_file() if f else ("", b""))
        reason = request.form.get("reason") or ""
        return _run(lambda c: gv.approve_with_evidence(c, project, g.user, rid, reason, name, data), write=True,
                    action="project.governance.approved_evidence", obj=project)


@blp.route("/projects/<string:project>/governance/<string:rid>/history")
class ProjectGovernanceHistory(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, rid):
        """A record's history: logged, changed, sent for approval, decisions, approved; the record as it was each time"""
        from .. import governance as gv
        return _run(lambda c: gv.history(c, project, g.user, rid))


@blp.route("/projects/<string:project>/charter")
class ProjectCharter(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The architecture charter: its sections and state"""
        from .. import governance as gv
        return _run(lambda c: gv.charter(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project):
        """{sections: {key: html}} and/or {approve: true} (Project Admin, Lead Architect)"""
        from .. import governance as gv
        return _run(lambda c: gv.save_charter(c, project, g.user, data or {}), write=True, action="project.charter.saved", obj=project)


@blp.route("/projects/<string:project>/complete")
class ProjectComplete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """Mark the project complete ({complete: true}) or open again ({complete: false}); Project Admin, Lead Architect"""
        return _run(lambda c: pj.mark_project(c, project, g.user, bool((data or {}).get("complete", True))), write=True,
                    action="project.completed", obj=project)


@blp.route("/projects/<string:project>/phases/<string:phase>")
class ProjectPhase(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, phase):
        """Mark a phase complete ({complete: true, note}) or open it again ({complete: false})"""
        d = data or {}
        return _run(lambda c: pj.mark_phase(c, project, g.user, phase, bool(d.get("complete", True)), d.get("note") or ""), write=True,
                    action="project.phase", obj=project)


# ---------------------------------------------------------------- the organisation's reference library (phase 13.0.8, D300)
def _form(*keys):
    return {k: request.form.get(k) for k in keys if request.form.get(k) is not None}


@blp.route("/reference-library")
class RefLibrary(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The library: folders, tags and entries (?folder=&q=&tag=&kind=file|link&deep=true); q searches the text inside documents"""
        from .. import reference_library as rl
        a = request.args
        return _run(lambda c: rl.browse(c, g.user, a.get("folder", ""), a.get("q", ""), a.get("tag", ""), a.get("kind", ""), a.get("deep") == "true"))


@blp.route("/reference-library/pick")
class RefLibraryPick(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Entries a project may link to (?q=)"""
        from .. import reference_library as rl
        return {"entries": _run(lambda c: rl.pick_list(c, g.user, request.args.get("q", "")))}


@blp.route("/reference-library/folders")
class RefLibraryFolders(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """{path, description}: a folder (Super Admins); {path, delete: true}: an empty one removed"""
        from .. import reference_library as rl
        d = data or {}
        if d.get("delete"):
            return _run(lambda c: rl.delete_folder(c, g.user, d.get("path") or ""), write=True, action="reference_library.folder", obj="")
        return _run(lambda c: rl.add_folder(c, g.user, d.get("path") or "", d.get("description") or ""), write=True,
                    action="reference_library.folder", obj="")


@blp.route("/reference-library/links")
class RefLibraryLinks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """A link: {folder, title, url, description, source, tags} (Super Admins)"""
        from .. import reference_library as rl
        return _run(lambda c: rl.add_link(c, g.user, data or {}), write=True, action="reference_library.added", obj="")


@blp.route("/reference-library/files")
class RefLibraryFiles(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self):
        """A document: multipart "file" with folder, title, description, source, tags, note (Super Admins)"""
        from .. import reference_library as rl
        name, data = _file()
        return _run(lambda c: rl.add_file(c, g.user, _form("folder", "title", "description", "source", "tags", "note"), name, data),
                    write=True, action="reference_library.added", obj="")


@blp.route("/reference-library/<string:eid>")
class RefLibraryEntry(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, eid):
        """One entry with its versions"""
        from .. import reference_library as rl
        return _run(lambda c: rl.entry(c, g.user, eid))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, eid):
        """Change an entry: {title, description, source, tags, folder, url} (Super Admins)"""
        from .. import reference_library as rl
        return _run(lambda c: rl.update(c, g.user, eid, data or {}), write=True, action="reference_library.changed", obj=eid)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, eid):
        """Delete an entry (its files go to the document store's trash; Super Admins)"""
        from .. import reference_library as rl
        return _run(lambda c: rl.delete(c, g.user, eid), write=True, action="reference_library.deleted", obj=eid)


@blp.route("/reference-library/<string:eid>/versions")
class RefLibraryVersion(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self, eid):
        """A new version of a document: multipart "file", "note" (Super Admins); the earlier versions stay"""
        from .. import reference_library as rl
        name, data = _file()
        return _run(lambda c: rl.new_version(c, g.user, eid, name, data, request.form.get("note", "")), write=True,
                    action="reference_library.version", obj=eid)


@blp.route("/reference-library/<string:eid>/file")
class RefLibraryFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, eid):
        """Download a document (?version=n; the current one by default)"""
        from urllib.parse import quote

        from .. import reference_library as rl
        v = request.args.get("version")
        data, ctype, name = _run(lambda c: rl.file_of(c, g.user, eid, int(v) if v and v.isdigit() else None))
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ---------------------------------------------------------------- tasks (D298)
@blp.route("/projects/<string:project>/tasks")
class Tasks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The project's tasks (a scratchpad, no dates), its statuses, its people and its steps"""
        from .. import project_tasks as pt
        return _run(lambda c: pt.listing(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a task: {title, notes_html, status, assigned_to, step_id}"""
        from .. import project_tasks as pt
        return _run(lambda c: pt.add(c, project, g.user, data or {}), write=True, action="project.task.added", obj=project)


@blp.route("/projects/<string:project>/tasks/<string:tid>")
class Task(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, tid):
        """Change a task (the fields sent; the person it is assigned to may change its status and notes)"""
        from .. import project_tasks as pt
        return _run(lambda c: pt.update(c, project, g.user, tid, data or {}), write=True, action="project.task.changed", obj=project)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, tid):
        """Delete a task (who made it, a Project Admin or a Lead Architect)"""
        from .. import project_tasks as pt
        return _run(lambda c: pt.delete(c, project, g.user, tid), write=True, action="project.task.deleted", obj=project)


@blp.route("/projects/<string:project>/task-statuses")
class TaskStatuses(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a status of the project's own: {name}"""
        from .. import project_tasks as pt
        return _run(lambda c: pt.add_status(c, project, g.user, (data or {}).get("name") or ""), write=True)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project):
        """Remove a status of the project's own (?name=; not while a task has it)"""
        from .. import project_tasks as pt
        return _run(lambda c: pt.delete_status(c, project, g.user, request.args.get("name") or ""), write=True)


# ---------------------------------------------------------------- the stakeholder matrix (D294)
@blp.route("/projects/<string:project>/stakeholders")
class Stakeholders(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The project's stakeholders: category, power and interest, class, position, concerns and artifacts, engagement,
        contact, last and next contact. ?format=csv: as a CSV file for Excel"""
        from .. import stakeholders as sh
        if request.args.get("format") == "csv":
            name, data = _run(lambda c: sh.to_csv(c, project, g.user))
            return Response(data, mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})
        return _run(lambda c: sh.listing(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a stakeholder: {name, organisation, role_title, category, power, interest, class, disrupt, understanding_now,
        understanding_needed, commitment_now, commitment_needed, support_needed, concerns, viewpoints[], items[], approach,
        frequency, channel, owner, email, phone, next_contact, notes_html}"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.add(c, project, g.user, data or {}), write=True, action="project.stakeholder.added", obj=project)


@blp.route("/projects/<string:project>/stakeholders/to-model")
class StakeholdersToModel(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """Put stakeholders into one of the project's models as Stakeholder entities: {model (default: the project's
        model), ids (default: all)}; ones put there before are brought up to date"""
        from .. import stakeholders as sh
        d = data or {}
        return _run(lambda c: sh.to_model(c, project, g.user, d.get("model"), d.get("ids")), write=True,
                    action="project.stakeholders.to_model", obj=project)


@blp.route("/projects/<string:project>/stakeholders/order")
class StakeholderOrder(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """The stakeholders' order: {order: [ids]}"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.reorder(c, project, g.user, (data or {}).get("order") or []), write=True)


@blp.route("/projects/<string:project>/stakeholders/<string:sid>")
class Stakeholder(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, sid):
        """Change a stakeholder (the fields sent; the rest stay)"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.update(c, project, g.user, sid, data or {}), write=True, action="project.stakeholder.changed", obj=project)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, sid):
        """Take a stakeholder out (with its discussion notes)"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.delete(c, project, g.user, sid), write=True, action="project.stakeholder.removed", obj=project)


@blp.route("/projects/<string:project>/stakeholders/<string:sid>/notes")
class StakeholderNotes(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, sid):
        """A stakeholder's discussion notes, newest first"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.notes(c, project, g.user, sid))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project, sid):
        """Note a discussion: {held_on (date), title, html (rich text)}"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.add_note(c, project, g.user, sid, data or {}), write=True, action="project.stakeholder.note", obj=project)


@blp.route("/projects/<string:project>/stakeholder-notes/<string:nid>")
class StakeholderNote(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, nid):
        """Change a discussion note"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.update_note(c, project, g.user, nid, data or {}), write=True)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, nid):
        """Delete a discussion note"""
        from .. import stakeholders as sh
        return _run(lambda c: sh.delete_note(c, project, g.user, nid), write=True)


# ---------------------------------------------------------------- a project's principles, at any time (owner, 8 Nov 2026)
@blp.route("/projects/<string:project>/principles")
class ProjectPrinciples(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a principle of the project's own: {name, area, code, statement, rationale, implications} (the last three rich text)"""
        return _run(lambda c: pw.add_principle(c, project, g.user, data or {}), write=True, action="project.principle.added", obj=project)


@blp.route("/projects/<string:project>/principles/<int:pid>")
class ProjectPrinciple(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, pid):
        """Change a principle of the project's own (a library one: its area only)"""
        return _run(lambda c: pw.update_principle(c, project, g.user, pid, data or {}), write=True)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, pid):
        """Take a principle out of the project"""
        return _run(lambda c: pw.delete_principle(c, project, g.user, pid), write=True, action="project.principle.removed", obj=project)


# ---------------------------------------------------------------- links and the Reference area (D296)
@blp.route("/projects/<string:project>/links")
class ProjectLinks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """Add a link: {title, url | link_project (+ link_document | link_item), description, item (a document class) or
        folder (in the Reference area), kind, tags}"""
        from .. import references as rf
        return _run(lambda c: rf.add_link(c, project, g.user, data or {}), write=True, action="project.link.added", obj=project)


@blp.route("/projects/<string:project>/links/<string:doc>")
class ProjectLink(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project, doc):
        """Change a link: {title, url, link_project, link_document, link_item, description}"""
        from .. import references as rf
        return _run(lambda c: rf.update_link(c, project, g.user, doc, data or {}), write=True)


@blp.route("/projects/<string:project>/reference")
class ProjectReference(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The Reference area: its folders, documents and links"""
        from .. import references as rf
        return _run(lambda c: rf.reference(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self, project):
        """A file into a folder of the Reference area (multipart "file", "folder")"""
        from .. import references as rf
        name, data = _file()
        folder = request.form.get("folder") or ""
        return _run(lambda c: rf.upload(c, project, g.user, folder, name, data), write=True, action="project.reference.file", obj=project)


@blp.route("/projects/<string:project>/reference/folders")
class ProjectReferenceFolders(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, project):
        """A folder of the Reference area: {path} (under 05_Reference_Library); {path, delete: true} takes an empty one away"""
        from .. import references as rf
        d = data or {}
        if d.get("delete"):
            return _run(lambda c: rf.delete_folder(c, project, g.user, d.get("path") or ""), write=True)
        return _run(lambda c: rf.add_folder(c, project, g.user, d.get("path") or ""), write=True)


@blp.route("/projects/<string:project>/library")
class ProjectIsLibrary(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project):
        """{on: true|false}: a library project offers its reference material to new projects (Super Admins)"""
        from .. import references as rf
        return _run(lambda c: rf.set_library(c, project, g.user, bool((data or {}).get("on"))), write=True)


@blp.route("/projects/reference-sources")
class ReferenceSources(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """What a new project can copy into its Reference area: ?parent=<project>&template=<code>"""
        from .. import references as rf
        return _run(lambda c: rf.sources(c, g.user, request.args.get("parent") or None, request.args.get("template") or None))
