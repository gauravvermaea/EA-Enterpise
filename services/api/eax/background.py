"""Every slow button as a background task (build phase 13.0.2, D273).

The work of each kind, done by the job runner as the person who asked (eax/tasks.run). Each function gets the
repository's connection (one transaction: the work and its audit record commit together) and the task, and returns
(message in words, result). The result is what the screen that asked shows when the task is done; a file the task
makes is kept with it (tasks.add_file) for 24 hours. Special result keys: _action (the audit action, when it is not
the kind; "-" for none) and _details (more audit details).

    merge.analyse / merge.apply / merge.sample          eax/merge.py
    package.analyse / package.uploaded / model.downloaded   packages (eax/model_ops.py)
    compare.run / compare.download                      comparing two sides (eax/compare.py)
    gap.create / gap.refresh / gap.download / gap.runs_compare   gap analyses (eax/gaps.py)
    tag.download / tag.restore                          tags (eax/tags.py)
    model.framework_moved / library.promoted / draft.applied     metamodel and library moves
    pushdown.push / pushdown.decide                     metamodel push-down (eax/pushdown.py)
    quality.recheck_type                                every entity of a type rechecked (eax/quality.py)
    changelog.export                                    the change log as CSV or Excel (its own database)
    project.created / project.library_zip               architecture projects (eax/projects.py)
    project.repo_zip / project.repo_revert              repository tags and zips (eax/repo_tags.py, D312)
    project.updated / project.finished                  the edit workflow and finishing a project (eax/project_work.py)
    wizard.merge / wizard.split / wizard.extend         model wizards (eax/model_wizards.py, D283)
    common.create / refresh / suggestions / tag / make_model / download   common analysis (eax/commons.py, D286)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from sqlalchemy import text

from . import tasks as tk

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _safe(name: str, n: int = 120) -> str:
    return "".join(ch if ch.isalnum() or ch in " ._-" else "-" for ch in name)[:n].strip() or "download"


def _file(conn, t: dict, data: bytes, name: str, ctype: str, extra: dict | None = None) -> tuple[str, dict]:
    tk.add_file(conn, t["id"], data, name, ctype)
    return f"{name} is ready ({len(data) // 1024 + 1} KB).", {"file": name, "bytes": len(data), **(extra or {})}


def _plain(m: dict | None) -> dict | None:
    return None if m is None else {k: v for k, v in m.items() if not k.startswith("_")}


# ---------------------------------------------------------------- merges
def merge_analyse(conn, t: dict, user) -> tuple[str, dict]:
    from . import merge as mg
    p, model = t["params"], str(t["model_guid"])
    tk.progress(None, "Matching the entities")
    if p.get("source_model"):
        plan = mg.analyse_model(conn, model, p["source_model"], user, bool(p.get("with_data", True)))
    else:
        data, name = tk.input_of(conn, t)
        plan = mg.analyse(conn, model, data, name, user, bool(p.get("with_data", True)))
    c = plan.get("counts") or {}
    return (f"Merge plan ready: {c.get('create', 0)} new, {c.get('update', 0)} to fill, {c.get('conflicts', 0)} conflicts "
            f"to decide, {c.get('relationships', 0)} new relationships. Open the Merge tab to decide and apply.", plan)


def merge_apply(conn, t: dict, user) -> tuple[str, dict]:
    from . import merge as mg
    p = t["params"]
    tk.progress(None, "Recording and committing the merge")
    out = mg.apply(conn, str(t["model_guid"]), p["merge"], user, p.get("decisions"), p.get("all_conflicts", ""),
                   bool(p.get("add_metamodel", True)), p.get("exclude"))
    return out.get("note") or "Merged.", {**out, "_details": {"merge": p["merge"]}}


def merge_sample(conn, t: dict, user) -> tuple[str, dict]:
    from . import merge as mg
    p = t["params"]
    data, name, ctype = mg.sample_package(conn, str(t["model_guid"]), p.get("format") or "zip", user.username,
                                          bool(p.get("with_data", True)))
    return _file(conn, t, data, name, ctype, {"_action": "-"})


# ---------------------------------------------------------------- packages
def _package(conn, t: dict) -> dict:
    from . import model_ops as mo
    from .metamodel_edit import EditError
    data, name = tk.input_of(conn, t)
    try:
        return mo.read_package(data, name)
    except EditError:
        raise
    except Exception as exc:  # a damaged file
        raise EditError(f"The file could not be read as a package: {exc}", 400) from exc


def package_analyse(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    out = mo.analyse_package(conn, _package(conn, t))
    model = (out.get("manifest") or {}).get("model", {}).get("name") or "The package"
    return f"{model} checked: choose where it goes and upload it.", {**out, "_action": "-"}


def package_import(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    p = t["params"]
    pkg = _package(conn, t)
    tk.progress(None, "Loading the package")
    out = mo.import_package(conn, pkg, p.get("placement") or "root", user.username, p.get("name") or None,
                            p.get("as_kind") or None, p.get("root") or None, p.get("content") or None)
    m = _plain(out["model"])
    return (f"Uploaded as {m['name']}.", {"model": m, "root": _plain(out.get("root")), "counts": out["counts"],
                                          "_action": "package.uploaded",
                                          "_details": {"package": pkg["manifest"].get("model", {}).get("name"),
                                                       "placement": p.get("placement")}})


def package_export(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    p = t["params"]
    fmt = "xlsx" if p.get("format") == "xlsx" else "zip"
    data, name, ctype = mo.export_package(conn, str(t["model_guid"]), fmt, user.username, p.get("content"))
    return _file(conn, t, data, name, ctype, {"_details": {"format": fmt, "content": p.get("content")}})


# ---------------------------------------------------------------- comparing and gaps
def _compare(conn, p: dict) -> dict:
    from . import compare as cp
    tk.progress(None, "Reading both sides")
    left = cp.load_side(conn, p["left"])
    right = cp.load_side(conn, p["right"])
    tk.progress(None, "Comparing")
    return cp.compare(left, right, p.get("settings"))


def compare_run(conn, t: dict, user) -> tuple[str, dict]:
    res = _compare(conn, t["params"])
    return f"Compared {res['left']['label']} with {res['right']['label']}.", {**res, "_action": "-"}


def compare_download(conn, t: dict, user) -> tuple[str, dict]:
    from . import compare as cp
    res = _compare(conn, t["params"])
    name = f"Compare {res['left']['label']} with {res['right']['label']}"
    return _file(conn, t, cp.to_xlsx(res, name), f"{_safe(name)}.xlsx", XLSX, {"_action": "-"})


def gap_create(conn, t: dict, user) -> tuple[str, dict]:
    from . import gaps as gp
    p = t["params"]
    tk.progress(None, "Comparing the baseline and the target")
    out = gp.create(conn, p["store_in"], user, p["name"], p["baseline"], p["target"], p["template"], p.get("settings"),
                    p.get("description", ""))
    return f"Gap analysis '{p['name']}' made.", {**out, "_details": {"name": p["name"]}}


def gap_refresh(conn, t: dict, user) -> tuple[str, dict]:
    from . import gaps as gp
    p = t["params"]
    tk.progress(None, "Comparing the two sides again")
    m = gp.model_of(conn, p["analysis"])
    out = gp.refresh(conn, m, user, p["analysis"])
    return "Gap analysis compared again.", {**out, "_details": {"analysis": p["analysis"]}}


def gap_download(conn, t: dict, user) -> tuple[str, dict]:
    from . import gaps as gp
    p = t["params"]
    a = gp.get(conn, gp.model_of(conn, p["analysis"]), p["analysis"])
    safe = _safe(a["name"], 100) or "gap-analysis"
    if p.get("format") == "docx":
        return _file(conn, t, gp.to_docx(a), f"{safe}.docx", DOCX, {"_action": "-"})
    return _file(conn, t, gp.to_xlsx(a), f"{safe}.xlsx", XLSX, {"_action": "-"})


def gap_runs_compare(conn, t: dict, user) -> tuple[str, dict]:
    from . import gaps as gp
    p = t["params"]
    res = gp.compare_runs(conn, p["a"], p["b"])
    if p.get("format") == "csv":
        return _file(conn, t, gp.runs_to_csv(res), "gap-results-compared.csv", "text/csv; charset=utf-8", {"_action": "-"})
    return _file(conn, t, gp.runs_to_xlsx(res), "gap-results-compared.xlsx", XLSX, {"_action": "-"})


def tag_download(conn, t: dict, user) -> tuple[str, dict]:
    from . import tags as tg
    p = t["params"]
    data, name, ctype = tg.download_tag(conn, str(t["model_guid"]), p["tag"], p.get("format") or "xlsx", user.username)
    return _file(conn, t, data, name, ctype, {"_action": "-"})


def tag_restore(conn, t: dict, user) -> tuple[str, dict]:
    from . import tags as tg
    p = t["params"]
    tk.progress(None, "Tagging the current version, then restoring")
    out = tg.restore_tag(conn, str(t["model_guid"]), user, p["tag"], p.get("note", ""))
    return out.get("note") or out.get("message") or "Restored: the tag is now the latest.", {**out, "_details": {"tag": p["tag"]}}


# ---------------------------------------------------------------- metamodel and library moves
def framework_move(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    p = t["params"]
    tk.progress(None, "Mapping the content across")
    out = mo.framework_move(conn, str(t["model_guid"]), p["target"], p["mode"], user.username, p.get("map"), p.get("name"),
                            p.get("with_data", True))
    out["model"] = _plain(out["model"])
    return f"Moved: {out['model']['name']} ({p['mode']}).", out


def promote(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    p = t["params"]
    out = mo.promote(conn, str(t["model_guid"]), p, user.username)
    c = out.pop("_copy", None)
    if c:
        tk.progress(None, "Copying the content")
        out["copied"] = mo.run_copy(conn, c["source"], c["target"], user.username, bool(c.get("publish")))
    out["model"] = _plain(out["model"])
    return f"Promoted into the library as {out['model']['name']} (a draft until published).", out


def draft_apply(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    p = t["params"]
    out = mo.draft_apply(conn, user, p["draft"], user.username, p.get("data") or {})
    out["model"] = _plain(out["model"])
    if out.get("created"):
        out["created"] = _plain(out["created"])
    return f"Draft applied to {out['model']['name']}.", {**out, "_details": {"draft": p["draft"]}}


# ---------------------------------------------------------------- push-down
def pushdown_push(conn, t: dict, user) -> tuple[str, dict]:
    from . import pushdown
    p = t["params"]
    fn = pushdown.pass_on if p.get("pass_on") else pushdown.push
    out = fn(conn, str(t["model_guid"]), user.username, p.get("mode", ""), p.get("fill_defaults", True), p.get("note", ""))
    return (out.get("message") or "Pushed down.",
            {**out, "_details": {"versions": out.get("versions"), "mode": out.get("mode"), "note": p.get("note", "")}})


def pushdown_decide(conn, t: dict, user) -> tuple[str, dict]:
    from . import pushdown
    p = t["params"]
    accept = bool(p.get("accept"))
    out = pushdown.decide(conn, str(t["model_guid"]), int(p["target"]), user.username, accept, p.get("note", ""))
    return (out.get("message") or ("Accepted." if accept else "Rejected."),
            {**out, "_action": "pushdown.accepted" if accept else "pushdown.rejected",
             "_details": {"note": p.get("note", ""), "package": p["target"]}})


# ---------------------------------------------------------------- quality
def quality_recheck_type(conn, t: dict, user) -> tuple[str, dict]:
    from . import quality as q
    from . import repository as repo
    from .metamodel_edit import EditError
    m = repo.get_model(conn, str(t["model_guid"]))
    et = t["params"]["entity_type"]
    types = q._rows(conn, """SELECT id, name FROM core.entity_types WHERE model_id = :m AND NOT is_deleted
                              AND (guid::text = :t OR code = :t OR lower(name) = lower(:t))""", m=m["_id"], t=str(et))
    if not types:
        raise EditError(f"No entity type {et} in {m['name']}.", 404)
    guids = [r["g"] for r in q._rows(conn, """SELECT guid::text AS g FROM core.entities WHERE model_id = :m
                                                AND entity_type_id = :t AND NOT is_deleted""", m=m["_id"], t=types[0]["id"])]
    done, step = 0, 200
    for i in range(0, len(guids), step):
        tk.progress(int(100 * i / max(len(guids), 1)), f"{i} of {len(guids)} checked")
        done += q.refresh_entities(conn, m, guids[i:i + step])
    return f"{done} {types[0]['name']} entities rechecked.", {"rechecked": done, "_action": "-"}


# ---------------------------------------------------------------- the change log (its own database)
def changelog_export(conn, t: dict, user) -> tuple[str, dict]:
    from . import change_log as cl
    from .db import get_changelog_engine
    p = t["params"]
    try:
        cl.ship_now(limit=20_000)
    except Exception:  # noqa: BLE001 - exports what is there
        pass
    with get_changelog_engine().connect() as log:
        data, name, ctype = cl.export(conn, user, p.get("filters") or {}, p.get("format", "csv"), cl=log)
    return _file(conn, t, data, name, ctype, {"_action": "-"})


# ---------------------------------------------------------------- architecture projects (their own connection, D266)
def project_create(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_ops as mo
    from . import projects as pj
    p = t["params"]
    tk.progress(5, "Creating the project")
    with pj.connections(True) as pc:
        out = pj.create(pc, user, p.get("data") or {})
    copies = out.pop("copies", [])
    failed = []
    for n, c in enumerate(copies, 1):
        tk.progress(10 + int(80 * (n - 1) / max(len(copies), 1)), f"Copying model content {n} of {len(copies)}")
        # the project is made already: a copy that fails is marked on its model and the rest carry on, so the project
        # is never left half made with "a project called X exists already" when it is tried again
        try:
            with conn.begin_nested():
                mo.run_copy(conn, c["source"], c["target"], user.username)
        except Exception as exc:  # noqa: BLE001
            conn.execute(text("UPDATE core.models SET copy_state = 'failed', copy_note = :n WHERE guid = CAST(:g AS uuid)"),
                         {"n": f"The copy failed: {str(exc)[:400]}", "g": c["target"]})
            failed.append(str(exc)[:200])
    goals = ""
    if copies:     # D274: goals and outcomes waiting for the project's model's metamodel copy
        tk.progress(92, "Writing the goals and outcomes")
        with _projects_beside(conn) as pc:
            try:
                goals = pw_pending(pc, out["project"]["id"], user)
            except Exception as exc:  # noqa: BLE001 - the project is made; the goals are entered again on Edit
                goals = f"The goals were not written: {exc}"
    tk.progress(95, "Queueing the repository build")
    queued = _queue_repository(out["project"]["id"])
    name = out["project"].get("name") or p.get("data", {}).get("name") or "The project"
    note = " ".join(x for x in (out.get("note"), goals, f"{len(failed)} model copies failed ({failed[0]}): the models say so; "
                                "take them out and add them again in Edit › Models." if failed else "") if x)
    return (f"{name} created{f' with {len(copies)} model copies' if copies else ''}. Its repository (its folders and templates in "
            f"Documents) is {'being built now' if queued else 'built within a minute'}: the Repository column says when it is ready."
            f"{(' ' + note) if note else ''}",
            {**out, "_details": {"name": name}})


def pw_pending(pc, project: str, user) -> str:
    from . import project_work as pw
    return pw.write_pending_goals(pc, project, user)


@contextmanager
def _projects_beside(conn):
    """The projects' connection with this task's repository connection beside it (D266): the same connection while proj
    is in the repository's database, so what the task copied is seen."""
    from . import tasks as tasks_mod
    from .db import get_engine, get_projects_engine
    peng = get_projects_engine()
    if peng is get_engine():
        yield conn
        return
    pc = peng.connect()
    tx = pc.begin()
    pc.info["core"] = conn
    try:
        yield pc
    except BaseException:
        tx.rollback()
        pc.close()
        raise
    if not tasks_mod.defer_commit(tx, pc):    # inside a task: it commits after the repository's work
        tx.commit()
        pc.close()


def project_update(conn, t: dict, user) -> tuple[str, dict]:
    """D275: the edit workflow on a live project; new model copies, then the goals, then the repository again."""
    from . import model_ops as mo
    from . import project_work as pw
    p = t["params"]
    tk.progress(5, "Saving the changes")
    with _projects_beside(conn) as pc:
        out = pw.update(pc, user, p["project"], p.get("data") or {})
    copies = out.pop("copies", [])
    for n, c in enumerate(copies, 1):
        tk.progress(10 + int(70 * (n - 1) / max(len(copies), 1)), f"Copying model content {n} of {len(copies)}")
        mo.run_copy(conn, c["source"], c["target"], user.username)
    if copies:
        with _projects_beside(conn) as pc:
            g = pw.write_pending_goals(pc, p["project"], user)
            out["note"] = " ".join(x for x in (out.get("note"), g) if x)
    _queue_repository(out["project"]["id"])
    return (f"{out['project']['name']} changed.{(' ' + out['note']) if out.get('note') else ''} New folders and templates are "
            "added to its repository in the background.", {**out, "_details": {"name": out["project"]["name"]}})


def project_finish(conn, t: dict, user) -> tuple[str, dict]:
    """D277: freeze the project, or merge it into another (its documents copied, its models kept or merged)."""
    from . import project_work as pw
    p = t["params"]
    with _projects_beside(conn) as pc:
        out = pw.finish(pc, user=user, project=p["project"], d=p.get("data") or {})
    return out["note"], {**out, "_details": {"mode": (p.get("data") or {}).get("mode")}}


def _queue_repository(project_guid: str) -> bool:
    from . import projects as pj
    from .db import get_projects_engine
    try:
        with get_projects_engine().connect() as c:
            pid = pj.project_row(c, project_guid)["id"]
        from .jobs import app as jobs_app
        from .jobs import project_repository
        with jobs_app.open():
            project_repository.defer(project_id=pid)
        return True
    except Exception:  # noqa: BLE001 - the minute job builds it
        return False


def project_library_zip(conn, t: dict, user) -> tuple[str, dict]:
    from . import projects as pj
    with pj.connections(False) as pc:
        data, name = pj.library_zip(pc, user, t["params"]["library"])
    return _file(conn, t, data, name, "application/zip", {"_action": "-"})


# ---------------------------------------------------------------- common analysis (D286)
def common_create(conn, t: dict, user) -> tuple[str, dict]:
    from . import commons as co
    p = t["params"]
    tk.progress(None, "Matching the models")
    out = co.create(conn, p.get("store_in"), user, p.get("name") or "", p.get("sides") or [], p.get("settings"), p.get("description") or "")
    return f"Common analysis '{out['name']}' made: {out['totals'].get('common', 0)} common elements.", {**out, "_details": {"name": out["name"]}}


def common_refresh(conn, t: dict, user) -> tuple[str, dict]:
    from . import commons as co
    p = t["params"]
    tk.progress(None, "Matching the models again")
    out = co.refresh(conn, co.model_of(conn, p["analysis"]), user, p["analysis"], p.get("settings"))
    return f"Compared again: {out['totals'].get('common', 0)} common elements.", {**out, "_details": {"analysis": p["analysis"]}}


def common_suggestions(conn, t: dict, user) -> tuple[str, dict]:
    from . import commons as co
    p = t["params"]
    out = co.decide_suggestions(conn, co.model_of(conn, p["analysis"]), user, p["analysis"], p.get("confirm"), p.get("reject"))
    return f"Matches saved and compared again: {out['totals'].get('common', 0)} common elements.", {**out, "_details": {"analysis": p["analysis"]}}


def common_tag(conn, t: dict, user) -> tuple[str, dict]:
    from . import commons as co
    p = t["params"]
    out = co.tag_common(conn, co.model_of(conn, p["analysis"]), user, p["analysis"], p.get("items"))
    return out["message"], {**out, "_details": {"analysis": p["analysis"]}}


def common_make_model(conn, t: dict, user) -> tuple[str, dict]:
    from . import commons as co
    p = t["params"]
    out = co.make_model(conn, co.model_of(conn, p["analysis"]), user, p["analysis"], p)
    return out["message"], {**out, "_action": "model.created"}


def common_download(conn, t: dict, user) -> tuple[str, dict]:
    from . import commons as co
    p = t["params"]
    a = co.get(conn, co.model_of(conn, p["analysis"]), p["analysis"])
    safe = _safe(a["name"], 100) or "common-analysis"
    if p.get("format") == "docx":
        return _file(conn, t, co.to_docx(a), f"{safe}.docx", DOCX, {"_action": "-"})
    return _file(conn, t, co.to_xlsx(a), f"{safe}.xlsx", XLSX, {"_action": "-"})


# ---------------------------------------------------------------- model wizards (D283)
def wizard_merge(conn, t: dict, user) -> tuple[str, dict]:
    """Merge `source` into this model with what the person chose: tag first, apply, freeze the source after."""
    from . import merge as mg
    from . import model_wizards as mw
    p = t["params"]
    model = str(t["model_guid"])
    tag = None
    if p.get("tag_first", True):
        tk.progress(10, "Tagging the model first")
        tag = mw.tag_first(conn, model, user, p.get("why") or "a merge")
    tk.progress(30, "Merging what was chosen")
    out = mg.apply(conn, model, p["merge"], user, p.get("decisions"), p.get("all_conflicts", ""), True, p.get("exclude"))
    frozen = None
    if p.get("freeze_source") and p.get("source"):
        tk.progress(90, "Freezing the merged model")
        frozen = mw.freeze(conn, p["source"], user, p.get("freeze_note") or "Merged into its parent")["message"]
    msg = out.get("note") or "Merged."
    if tag:
        msg += f" Tagged first as '{tag['name']}'."
    if frozen:
        msg += f" {frozen}"
    return msg, {**out, "tag": tag, "frozen": bool(frozen), "_details": {"merge": p["merge"], "source": p.get("source")}}


def wizard_split(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_wizards as mw
    out = mw.split(conn, str(t["model_guid"]), user, t["params"])
    return out["message"], {**out, "_action": "model.split"}


def wizard_extend(conn, t: dict, user) -> tuple[str, dict]:
    from . import model_wizards as mw
    p = t["params"]
    out = mw.extend_metamodel(conn, str(t["model_guid"]), user, p.get("source"), p)
    return out["message"], {**out, "_action": "metamodel.extended"}


def project_backup(conn, t: dict, user) -> tuple[str, dict]:
    """A project with its models and documents, to one backup file (owner, 7 Nov 2026)."""
    from . import project_backup as pb
    p = t["params"]
    tk.progress(10, "Backing up the project, its models and documents")
    with _projects_beside(conn) as pc:
        return pb.backup(conn, pc, user, p["project"], p.get("why") or "")


def project_restore(conn, t: dict, user) -> tuple[str, dict]:
    """A project backup restored: its models and rows now; its repository is built and its documents put back by the
    minute job once this has committed (a build before the commit would not see the project)."""
    from . import permissions as perms
    from . import project_backup as pb
    from . import projects as pj
    from .metamodel_edit import EditError
    p = t["params"]
    over = bool(p.get("over"))
    if over and perms.SUPER_ADMIN not in user.roles:
        raise EditError("Putting a project back over itself needs the Super Admin role.", 403)
    if p.get("upload"):
        path = pb.folder() / "_uploads" / p["upload"]
    else:
        with _projects_beside(conn) as pc:
            pb.need_manage(pc, pj.project_row(pc, p["project"]), user)
        path = pb.path_of(p["project"], p["file"])
    tk.progress(10, "Putting the project and its models back as they were" if over else "Making the models and the project again")
    with _projects_beside(conn) as pc:
        msg, out = pb.restore(conn, pc, user, path, p.get("name") or "", over=over, models_over=over,
                              uploaded=bool(p.get("upload")))
    files = out.pop("files", {})
    msg += (f" Its repository is built again in Documents within a minute or two, and {len(files)} document files are put "
            "back then (the Repository tab shows when it is ready).")
    return msg, {"project": out["project"], "_details": {"name": out["project"]}}


def project_repository_now(conn, t: dict, user) -> tuple[str, dict]:
    """Build now (owner, 7 Nov 2026: a background task in the task drawer)."""
    from . import projects as pj
    from .db import get_projects_engine
    p = t["params"]
    tk.progress(5, "Building the repository in Documents")
    note = pj.build_repository(lambda: get_projects_engine().begin(), int(p["project_id"]))
    return f"{p.get('name') or 'The project'}: {note}", {"project": p.get("project")}


def project_repo_zip(conn, t: dict, user) -> tuple[str, dict]:
    """Documents in one zip: at a tag, one class, or the whole repository (D312)."""
    from . import projects as pj
    from . import repo_tags as rt
    p = t["params"]
    tk.progress(10, "Reading the documents from Documents")
    with pj.connections(False) as pc:
        data, name = rt.zip_documents(pc, p["project"], user, p.get("tag") or "", p.get("item") or "")
    return _file(conn, t, data, name, "application/zip", {"_action": "-"})


def project_repo_revert(conn, t: dict, user) -> tuple[str, dict]:
    """The repository back to a tag (D312): in one transaction of the projects' database."""
    from . import projects as pj
    from . import repo_tags as rt
    p = t["params"]
    tk.progress(10, "Tagging the repository as it is now, then bringing it back")
    with pj.connections() as pc:
        out = rt.revert(pc, p["project"], user, p["tag"])
    return out["message"], {"project": p["project"], "message": out["message"]}


WORK: dict[str, Any] = {
    "merge.analyse": merge_analyse, "merge.apply": merge_apply, "merge.sample": merge_sample,
    "package.analyse": package_analyse, "package.uploaded": package_import, "model.downloaded": package_export,
    "compare.run": compare_run, "compare.download": compare_download,
    "gap.create": gap_create, "gap.refresh": gap_refresh, "gap.download": gap_download, "gap.runs_compare": gap_runs_compare,
    "tag.download": tag_download, "tag.restore": tag_restore,
    "model.framework_moved": framework_move, "library.promoted": promote, "draft.applied": draft_apply,
    "pushdown.push": pushdown_push, "pushdown.decide": pushdown_decide,
    "quality.recheck_type": quality_recheck_type, "changelog.export": changelog_export,
    "project.created": project_create, "project.library_zip": project_library_zip,
    "project.repo_zip": project_repo_zip, "project.repo_revert": project_repo_revert,
    "project.updated": project_update, "project.finished": project_finish,
    "project.backup": project_backup, "project.restore": project_restore, "project.repository": project_repository_now,
    "wizard.merge": wizard_merge, "wizard.split": wizard_split, "wizard.extend": wizard_extend,
    "common.create": common_create, "common.refresh": common_refresh, "common.suggestions": common_suggestions,
    "common.tag": common_tag, "common.make_model": common_make_model, "common.download": common_download,
}
KINDS = {
    "merge.analyse": "Plan a merge", "merge.apply": "Apply a merge", "merge.sample": "Make a merge test file",
    "package.analyse": "Check a package", "package.uploaded": "Upload a package", "model.downloaded": "Download a model package",
    "compare.run": "Compare", "compare.download": "Download a comparison",
    "gap.create": "Make a gap analysis", "gap.refresh": "Compare a gap analysis again", "gap.download": "Download a gap analysis",
    "gap.runs_compare": "Compare two gap results",
    "tag.download": "Download a tag", "tag.restore": "Restore a tag",
    "model.framework_moved": "Move a model to another framework", "library.promoted": "Promote a model into the library",
    "draft.applied": "Apply a metamodel draft", "pushdown.push": "Push the metamodel down", "pushdown.decide": "Decide on a push-down",
    "quality.recheck_type": "Recheck data quality", "changelog.export": "Export the change log",
    "project.created": "Create a project", "project.library_zip": "Download a template library",
    "project.repo_zip": "Download documents", "project.repo_revert": "Bring a repository back to a tag",
    "project.updated": "Change a project", "project.finished": "Finish a project",
    "project.backup": "Back up a project", "project.restore": "Restore a project", "project.repository": "Build a project's repository",
    "wizard.merge": "Merge with the model wizard", "wizard.split": "Split a model", "wizard.extend": "Extend a metamodel",
    "common.create": "Make a common analysis", "common.refresh": "Compare a common analysis again",
    "common.suggestions": "Match close names", "common.tag": "Tag the common elements",
    "common.make_model": "Make a model of the common part", "common.download": "Download a common analysis",
}
tk.WORK.update(WORK)
tk.KINDS.update(KINDS)


# ---------------------------------------------------------------- merging a child into its parent (phases 19 and 20, D359)
def mergeback_send(conn, t: dict, user) -> tuple[str, dict]:
    """The child sent for merge: the changes worked out three-way and kept with the request."""
    from . import merge_back as mb
    tk.progress(20, "Comparing the child, its starting point and the parent")
    out = mb.send(conn, str(t["model_guid"]), user, t["params"].get("note", ""))
    return (f"Merge request {out['number']} sent: {out['counts']['total']} changes, {out['counts']['conflicts']} to decide.",
            {**out, "_action": "merge_request.sent", "_details": {"request": out["id"]}})


def mergeback_merge(conn, t: dict, user) -> tuple[str, dict]:
    """Everything accepted goes into the parent (tagged first): one commit and the merge report."""
    from . import merge_back as mb
    tk.progress(20, "Tagging the parent and merging what was accepted")
    out = mb.merge(conn, t["params"]["request"], user)
    return out["message"], {**out, "_action": "merge_request.merged", "_details": {"request": out["id"]}}


def mergeback_finish(conn, t: dict, user) -> tuple[str, dict]:
    """After the merge: the child frozen, or refreshed from the parent (tagged first, a new starting point)."""
    from . import merge_back as mb
    tk.progress(20, "Freezing the child" if t["params"].get("choice") == "freeze" else "Refreshing the child from its parent")
    out = mb.finish(conn, t["params"]["request"], user, t["params"].get("choice", ""), t["params"].get("note", ""))
    return out["message"], {**out, "_action": "merge_request.closed", "_details": {"request": out["id"], "after": out["after"]}}


tk.WORK.update({"mergeback.send": mergeback_send, "mergeback.merge": mergeback_merge, "mergeback.finish": mergeback_finish})
tk.KINDS.update({"mergeback.send": "Send a model for merge into its parent", "mergeback.merge": "Merge a child into its parent",
                 "mergeback.finish": "Freeze or refresh a merged child"})
