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
POST   /projects/<p>/steps/<s>/done                {done: true|false}: mark a step done (contributors) or reopen it (admins)
POST   /projects/<p>/documents/<d>/checkout        check it out to yourself
POST   /projects/<p>/documents/<d>/checkin         check in the new file (multipart "file", "comment")
POST   /projects/<p>/documents/<d>/undo-checkout   end a check-out without a new version
POST   /projects/library/templates/<id>/file       a TOGAF template's file (Super Admins; multipart "file")
POST   /projects/library/templates/load            store every matching file of the TOGAF folder (Super Admins)
POST   /projects/library/setup                     {shared: [library ids]}: the template library setup (Super Admins, D264)
POST   /projects/library/libraries                 a new template library from a zip (multipart "file", "name", "description")
GET    /projects/library/libraries/<l>/zip         the library as one zip in its folder layout
POST   /projects/library/libraries/<l>/share       {shared: true|false} (Super Admins)
POST   /projects/library/libraries/<l>/zip         the TOGAF templates as one zip, the I094 download as it is (Super Admins)
"""

from __future__ import annotations

import logging

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit
from .. import model_ops as mo
from .. import permissions as perms
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
    @blp.response(200, Free)
    @require_auth()
    def post(self, template_id):
        """Store a library template's file in Documents (Super Admins); TOGAF's: your licensed copy, unchanged"""
        name, data = _file()
        return _run(lambda c: pj.upload_template(c, g.user, template_id, name, data), write=True,
                    action="project.library.template", obj=template_id)


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
        """The whole template library as one zip in its folder layout (to rebrand and upload as your own)"""
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


@blp.route("/projects/<string:project>/people")
class People(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, project):
        """The people and who signs off (Project Admin, Lead Architect)"""
        return _run(lambda c: pj.set_people(c, project, g.user, (data or {}).get("members") or [], (data or {}).get("signoff") or {}),
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


@blp.route("/projects/<string:project>/repository")
class Repository(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, project):
        """Build the project's repository in Documents again"""
        out = _run(lambda c: pj.retry_repository(c, project, g.user), write=True)
        _queue_repository(out["id"])
        return {"message": "The repository is being built in Documents."}


@blp.route("/projects/<string:project>/items/<string:item>/documents")
class Upload(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self, project, item):
        """Upload a document into an item's folder"""
        name, data = _file()
        return _run(lambda c: pj.upload(c, project, g.user, item, name, data), write=True, action="project.document.upload", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>")
class Download(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, doc):
        """Download the document's latest version"""
        data, ctype, name = _run(lambda c: pj.download(c, project, g.user, doc))
        safe = name.replace('"', "'")
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@blp.route("/projects/<string:project>/templates/<int:template>")
class TemplateDownload(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, template):
        """Download a template of the project's libraries"""
        data, ctype, name = _run(lambda c: pj.template_download(c, project, g.user, template))
        safe = name.replace('"', "'")
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@blp.route("/projects/<string:project>/steps/<int:step>/done")
class StepDone(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, project, step):
        """Mark a step done, or reopen it"""
        return _run(lambda c: pj.mark_step(c, project, g.user, step, bool((data or {}).get("done"))), write=True,
                    action="project.step", obj=project)


@blp.route("/projects/<string:project>/documents/<string:doc>/history")
class History(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, doc):
        """Who did what to the document"""
        return {"events": _run(lambda c: pj.history(c, project, g.user, doc))}


@blp.route("/projects/<string:project>/documents/<string:doc>/checkout")
class CheckOut(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, doc):
        """Check the document out to yourself"""
        return _run(lambda c: pj.check_out(c, project, g.user, doc), write=True, action="project.document.checkout", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/checkin")
class CheckIn(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, doc):
        """Check in the new file as the next version"""
        name, data = _file()
        comment = request.form.get("comment", "")
        return _run(lambda c: pj.check_in(c, project, g.user, doc, name, data, comment), write=True,
                    action="project.document.checkin", obj=doc)


@blp.route("/projects/<string:project>/documents/<string:doc>/undo-checkout")
class UndoCheckOut(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, project, doc):
        """End a check-out without a new version (who checked out; Lead Architect, Model Admin, Project Admin, Super Admin)"""
        return _run(lambda c: pj.undo_check_out(c, project, g.user, doc), write=True, action="project.document.undo_checkout", obj=doc)
